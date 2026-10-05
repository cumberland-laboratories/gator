"""
Session management for gator loop.

Owns: session.json CRUD, token generation/resolution, turn tracking,
file locking (platform-aware), and atomic writes.

The session lock is the concurrency primitive — all writers acquire it
before reading or mutating session.json. See the implementation plan's
Concurrency Safety section for the full rationale.
"""

import base64
import json
import os
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_SCHEMA = "gator-loop-session-v1"
TOKENS_FILENAME = ".tokens.json"
SESSION_FILENAME = "session.json"
LOCK_FILENAME = "session.lock"
EVENTS_FILENAME = "events.jsonl"

TOKEN_PREFIX = "glp_"


# ---------------------------------------------------------------------------
# Platform-aware file locking
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    import msvcrt

    def _lock_exclusive(fd):
        """Acquire exclusive lock on file descriptor (Windows)."""
        msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(fd):
        """Release lock on file descriptor (Windows)."""
        try:
            msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass  # already unlocked or closed
else:
    import fcntl

    def _lock_exclusive(fd):
        """Acquire exclusive lock on file descriptor (POSIX)."""
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock(fd):
        """Release lock on file descriptor (POSIX)."""
        fcntl.flock(fd, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Gator root discovery
# ---------------------------------------------------------------------------

def find_gator_root(start_path=None):
    """Walk up from start_path looking for .gator/ directory.

    Returns the repo root (parent of .gator/), or raises if not found.
    """
    current = Path(start_path or os.getcwd()).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".gator").is_dir():
            return parent
    raise FileNotFoundError(
        "No .gator/ directory found. Are you inside a Gator-governed repo?"
    )


# ---------------------------------------------------------------------------
# Token generation and resolution
# ---------------------------------------------------------------------------

def make_token(loop_id, role):
    """Generate a role token with a secret nonce.

    Returns (token_string, nonce). The nonce is stored only in the
    gitignored .tokens.json — never in committed session state.
    """
    nonce = secrets.token_hex(4)  # 8 hex chars
    payload = f"{loop_id}:{role}:{nonce}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return f"{TOKEN_PREFIX}{encoded}", nonce


def resolve_token(token, loop_dir=None):
    """Decode a token and validate its nonce against .tokens.json.

    When ``loop_dir`` is provided the function skips ``find_gator_root()``
    and validates against the supplied directory directly.  It also
    verifies the decoded ``loop_id`` matches ``Path(loop_dir).name`` to
    preserve the one-token / one-loop binding.

    Returns (loop_id, role, resolved_loop_dir) on success.
    Raises ValueError on invalid or tampered tokens.
    """
    if not token.startswith(TOKEN_PREFIX):
        raise ValueError(f"Invalid token format: missing '{TOKEN_PREFIX}' prefix")

    raw = token[len(TOKEN_PREFIX):]
    padded = raw + "=" * (-len(raw) % 4)
    try:
        payload = base64.urlsafe_b64decode(padded).decode()
    except Exception as exc:
        raise ValueError(f"Invalid token encoding: {exc}") from exc

    parts = payload.rsplit(":", 2)
    if len(parts) != 3:
        raise ValueError("Invalid token payload structure")

    loop_id, role, nonce = parts

    if loop_dir is not None:
        loop_dir = Path(loop_dir)
        if loop_dir.name != loop_id:
            raise ValueError(
                f"Token loop_id '{loop_id}' does not match "
                f"loop_dir name '{loop_dir.name}'")
    else:
        repo_root = find_gator_root()
        loop_dir = repo_root / ".gator" / "loops" / loop_id

    if not loop_dir.is_dir():
        raise ValueError(f"Loop directory not found: {loop_dir}")

    # Validate nonce against stored secret
    tokens_file = loop_dir / TOKENS_FILENAME
    if not tokens_file.exists():
        raise ValueError("Token store not found — loop may have been cleaned up")

    stored = json.loads(tokens_file.read_text(encoding="utf-8"))
    if stored.get(role, {}).get("nonce") != nonce:
        raise ValueError("Invalid token — nonce mismatch")

    return loop_id, role, loop_dir


# ---------------------------------------------------------------------------
# Bounded-integer validation (shared by CLI and Dashboard loop inputs)
# ---------------------------------------------------------------------------

TURN_TIMEOUT_MIN = 30
TURN_TIMEOUT_MAX = 3600

ROUNDS_MIN = 1
ROUNDS_MAX = 20


def _validate_bounded_int(value, low, high, what, kind):
    """Return value as an int in low..high, or raise ValueError.

    Only integral values are accepted: bool and non-integral numbers are
    rejected; strings are accepted only when they spell a plain integer
    (CLI input). ``what`` names the field and ``kind`` describes the unit
    in error messages, e.g. ("turn timeout", "number of seconds").
    """
    if isinstance(value, bool):
        raise ValueError(f"{what} must be an integer {kind}")
    if isinstance(value, str):
        text = value.strip()
        if not text.lstrip("-").isdigit():
            raise ValueError(f"{what} must be an integer {kind}, got {value!r}")
        value = int(text)
    if not isinstance(value, int):
        raise ValueError(f"{what} must be an integer {kind}, got {value!r}")
    if value < low or value > high:
        unit = " seconds" if kind == "number of seconds" else ""
        raise ValueError(
            f"{what} must be between {low} and {high}{unit}, got {value}")
    return value


def validate_turn_timeout(value):
    """Return value as an int turn timeout (TURN_TIMEOUT_MIN..MAX s), or raise ValueError."""
    return _validate_bounded_int(value, TURN_TIMEOUT_MIN, TURN_TIMEOUT_MAX,
                                 "turn timeout", "number of seconds")


def validate_round_count(value):
    """Return value as an int round count (ROUNDS_MIN..ROUNDS_MAX), or raise ValueError.

    Used for loop-start `max_rounds` (Dashboard) and for the per-extension
    round increment (#39). No total-ceiling cap is applied here.
    """
    return _validate_bounded_int(value, ROUNDS_MIN, ROUNDS_MAX,
                                 "rounds", "number of rounds")


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Loop mode (#41)
# ---------------------------------------------------------------------------

MODE_PLANNING = "planning"
MODE_CODING = "coding"
# Values written before #41 that mean planning: absent (very old sessions)
# and "planning-only" (what create_session() has always written for
# planning loops, and still writes so planning residue is unchanged).
_PLANNING_MODE_VALUES = frozenset({None, "planning", "planning-only"})


def loop_mode(session):
    """Normalized loop mode: ``"planning"`` or ``"coding"``.

    The ONLY way loop mode may be read. A missing ``mode`` or the legacy
    ``"planning-only"`` value is planning. An unknown value raises
    ValueError (fail closed rather than guess a state machine).
    """
    raw = session.get("mode")
    if raw in _PLANNING_MODE_VALUES:
        return MODE_PLANNING
    if raw == MODE_CODING:
        return MODE_CODING
    raise ValueError(f"Unknown loop mode: {raw!r}")


# ---------------------------------------------------------------------------
# Architect brief (#43)
# ---------------------------------------------------------------------------
#
# Optional, immutable Markdown guidance supplied at loop creation. Stored as
# ordinary loop residue; the session records only metadata
# {artifact, sha256, bytes}. Every read of it goes through the fixed-name,
# containment-checked verify_brief() — never through a path from session data.

BRIEF_FILENAME = "architect-brief.md"
SOURCE_BRIEF_FILENAME = "source-architect-brief.md"
MAX_BRIEF_BYTES = 32 * 1024  # 32,768 UTF-8 bytes (Architect decision)
BRIEF_NAMES = frozenset({BRIEF_FILENAME, SOURCE_BRIEF_FILENAME})

# Coding-successor carry-forward decision (#43 D1)
SOURCE_BRIEF_DECISIONS = frozenset({"kept", "dropped", "none_available"})

# verify_brief() results
BRIEF_ABSENT = "absent"            # optional brief never supplied (neutral)
BRIEF_OK = "ok"
BRIEF_MISSING = "missing"
BRIEF_MISMATCH = "mismatch"
BRIEF_UNREADABLE = "unreadable"
BRIEF_INVALID_REF = "invalid_ref"
BRIEF_UNSAFE = "unsafe"

# Contract flags recorded on NEW sessions (#46 migration boundary).
CONTEXT_EVIDENCE_CONTRACT = 1
# #47: new planning AND coding sessions use an Architect attention
# interval instead of a participant-facing hard turn timeout.
ATTENTION_INTERVAL_CONTRACT = 1
# #55: new planning sessions require a '## Coding Checkpoints' section.
CHECKPOINT_CONTRACT = 1
# Default interval; stored in status.turn_timeout_seconds (#47 Decision 2).
DEFAULT_ATTENTION_INTERVAL = 300


def attention_mode(session):
    """True when the session uses #47 attention-interval semantics.

    The ONLY gate: ``contract.attention_interval`` must be an int >= 1
    (never a bool). Nothing is inferred from dates, versions, or field
    presence; legacy sessions keep their recorded hard-timeout behavior.
    """
    contract = session.get("contract") if isinstance(session, dict) else None
    if not isinstance(contract, dict):
        return False
    level = contract.get("attention_interval")
    return isinstance(level, int) and not isinstance(level, bool) and level >= 1


def validate_brief_bytes(data):
    """Validate brief content bytes. Returns the bytes; raises ValueError.

    UTF-8 text, non-blank, no NUL, at most MAX_BRIEF_BYTES bytes.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("Architect brief must be text")
    data = bytes(data)
    if len(data) > MAX_BRIEF_BYTES:
        raise ValueError(
            f"Architect brief is {len(data)} bytes; the limit is "
            f"{MAX_BRIEF_BYTES} bytes")
    if b"\x00" in data:
        raise ValueError("Architect brief must not contain NUL bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Architect brief must be UTF-8 text")
    if not text.strip():
        raise ValueError("Architect brief is empty")
    return data


def brief_bytes_from_text(text):
    """Dashboard textarea text -> validated LF-normalized UTF-8 bytes.

    Returns None for an empty/whitespace string ("no brief").
    """
    if not isinstance(text, str):
        raise ValueError("Architect brief must be a string")
    if not text.strip():
        return None
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return validate_brief_bytes(text.encode("utf-8"))


def read_brief_file(path):
    """Read and validate a brief file supplied by the Architect (CLI).

    Must be a regular file (not a symlink or directory); the size is
    checked before reading so an oversized file is never loaded.
    """
    p = Path(path)
    # Same trust boundary as verify_brief: never follow a filesystem
    # indirection (symlink or Windows reparse point / junction) — checked
    # BEFORE exists()/is_file()/stat()/open().
    if p.is_symlink() or _is_reparse_point(p):
        raise ValueError(
            f"Architect brief must not be a symlink or reparse point: {path}")
    if not p.exists():
        raise FileNotFoundError(f"Architect brief not found: {path}")
    if not p.is_file():
        raise ValueError(f"Architect brief is not a regular file: {path}")
    size = p.stat().st_size
    if size > MAX_BRIEF_BYTES:
        raise ValueError(
            f"Architect brief is {size} bytes; the limit is "
            f"{MAX_BRIEF_BYTES} bytes")
    with open(p, "rb") as f:
        data = f.read(MAX_BRIEF_BYTES + 1)
    return validate_brief_bytes(data)


def brief_meta(data, artifact):
    import hashlib
    return {"artifact": artifact,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


def _valid_brief_ref(ref, expected_name):
    import re as _re
    return (isinstance(ref, dict)
            and ref.get("artifact") == expected_name
            and isinstance(ref.get("sha256"), str)
            and _re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]) is not None
            and isinstance(ref.get("bytes"), int)
            and not isinstance(ref.get("bytes"), bool)
            and ref["bytes"] >= 0)


def _is_reparse_point(path):
    try:
        st = os.lstat(str(path))
    except OSError:
        return False
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


def verify_brief(loop_dir, ref, expected_name):
    """Integrity of one brief position. Returns a result string; never
    returns content and never opens a path taken from session data.

    absent       ref is None (the optional brief was never supplied)
    invalid_ref  ref present but malformed, wrong-typed, or names a file
                 other than ``expected_name`` (positional binding)
    unsafe       the fixed path is a symlink/reparse point or escapes the
                 loop directory
    missing      no regular file at the fixed path
    unreadable   OSError while reading
    mismatch     size or SHA-256 differs from the recorded metadata
    ok           matches
    """
    import hashlib
    if ref is None:
        return BRIEF_ABSENT
    if expected_name not in BRIEF_NAMES or not _valid_brief_ref(ref, expected_name):
        return BRIEF_INVALID_REF
    loop_dir = Path(loop_dir)
    path = loop_dir / expected_name
    if path.is_symlink() or _is_reparse_point(path):
        return BRIEF_UNSAFE
    try:
        if path.resolve().parent != loop_dir.resolve():
            return BRIEF_UNSAFE
    except OSError:
        return BRIEF_UNSAFE
    if not path.is_file():
        return BRIEF_MISSING
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_BRIEF_BYTES + 1)
    except OSError:
        return BRIEF_UNREADABLE
    if len(data) != ref["bytes"] or \
            hashlib.sha256(data).hexdigest() != ref["sha256"]:
        return BRIEF_MISMATCH
    return BRIEF_OK


def read_verified_brief(loop_dir, ref, expected_name):
    """(result, bytes_or_None): the verified brief bytes when result is ok.

    Used only to carry a source brief forward; reads once and returns the
    exact bytes that passed verification.
    """
    import hashlib
    state = verify_brief(loop_dir, ref, expected_name)
    if state != BRIEF_OK:
        return state, None
    with open(Path(loop_dir) / expected_name, "rb") as f:
        data = f.read(MAX_BRIEF_BYTES + 1)
    if len(data) != ref["bytes"] or \
            hashlib.sha256(data).hexdigest() != ref["sha256"]:
        return BRIEF_MISMATCH, None
    return BRIEF_OK, data


def brief_status_view(ref, expected_name):
    """Strict, positionally bound metadata view for status surfaces.

    Returns {artifact, sha256, bytes} only when ``ref`` is well-formed AND
    names exactly ``expected_name``; otherwise None. Unknown keys are always
    dropped — brief content can never pass through status.
    """
    if not _valid_brief_ref(ref, expected_name):
        return None
    return {"artifact": ref["artifact"], "sha256": ref["sha256"],
            "bytes": ref["bytes"]}


def create_session(feature, loop_id, max_rounds=3, turn_timeout=300,
                   mode=MODE_PLANNING, coding=None, brief=None):
    """Build the initial session dict.

    Does not write to disk — caller is responsible for saving.

    Planning sessions keep ``"mode": "planning-only"`` (#41) and, since
    #46, carry ``"contract": {"context_evidence": 1}`` — the migration
    boundary for Context Checked enforcement. Coding sessions carry
    ``"mode": "coding"``, start at ``implementation_drafting``, and require
    the ``coding`` binding block (source loop, plan digest, base commit).
    ``brief`` (#43) is the Architect-brief metadata
    ``{artifact, sha256, bytes}`` when one was supplied; the key is absent
    otherwise.
    """
    if mode not in (MODE_PLANNING, MODE_CODING):
        raise ValueError(f"Unknown loop mode: {mode!r}")
    if mode == MODE_CODING and not coding:
        raise ValueError("A coding session requires its coding binding")
    now = datetime.now(tz=timezone.utc).isoformat()
    # #47: new sessions record when the turn started instead of a deadline.
    deadline = None

    session = {
        "schema": SESSION_SCHEMA,
        "loop_id": loop_id,
        "feature": feature,
        "mode": "planning-only",
        "created_at": now,
        "roles": {
            "draftor": {"role": "draftor", "joined": False},
            "reviewer": {"role": "reviewer", "joined": False},
            "architect": {"role": "architect"},
        },
        "status": {
            "stage": "plan_drafting",
            "next_role": "draftor",
            "plan_status": "draft",
            "architect_action_required": False,
            "blocked": False,
            "round": 0,
            "max_rounds": max_rounds,
            "unresolved_findings": 0,
            "turn_deadline": deadline,
            "turn_timeout_seconds": turn_timeout,
            "resume_stage": None,
            "resume_next_role": None,
            "last_updated": now,
        },
        "current": {
            "draft": None,
            "findings": None,
        },
        "turns": [],
        "decisions": [],
    }
    if brief is not None:
        session["brief"] = dict(brief)  # metadata only: artifact/sha256/bytes
    # #47 migration boundary: every new session (both modes) uses an
    # Architect attention interval; turn_timeout_seconds stores it.
    session["contract"] = {"attention_interval": ATTENTION_INTERVAL_CONTRACT}
    session["status"]["turn_started_at"] = now
    session["status"]["attention_notified_turn"] = None
    if mode == MODE_PLANNING:
        # #46 migration boundary: only sessions created with this flag get
        # Context Checked enforcement; existing sessions never do.
        session["contract"]["context_evidence"] = CONTEXT_EVIDENCE_CONTRACT
        # #55 migration boundary: plans from flagged planning sessions must
        # declare '## Coding Checkpoints'; legacy plans never are.
        session["contract"]["coding_checkpoints"] = CHECKPOINT_CONTRACT
    if mode == MODE_CODING:
        session["mode"] = MODE_CODING
        session["status"]["stage"] = "implementation_drafting"
        session["status"]["plan_status"] = "implementation"
        session["current"]["implementation"] = None
        session["coding"] = dict(coding)
        session["coding"].setdefault("generations", [])
        session["coding"].setdefault("approval", None)
    return session


def checkpoint_manifest(session):
    """The frozen ``coding.checkpoints`` manifest (#55), or None.

    The single gate for checkpoint behaviour: pre-#55 coding sessions and
    planning sessions have no manifest and keep today's transitions.
    """
    coding = session.get("coding") if isinstance(session, dict) else None
    if not isinstance(coding, dict):
        return None
    manifest = coding.get("checkpoints")
    if (isinstance(manifest, dict)
            and manifest.get("contract") == CHECKPOINT_CONTRACT
            and isinstance(manifest.get("items"), list)
            and manifest["items"]
            and isinstance(manifest.get("current"), int)
            and 0 <= manifest["current"] < len(manifest["items"])):
        return manifest
    return None


def active_checkpoint(session):
    """``(index, item, count)`` for the active checkpoint, or None."""
    manifest = checkpoint_manifest(session)
    if manifest is None:
        return None
    i = manifest["current"]
    return i, manifest["items"][i], len(manifest["items"])


def declared_checkpoint(session):
    """``active_checkpoint`` for a DECLARED manifest only, else None.

    An implicit manifest (one ``Full implementation`` checkpoint for a
    pre-#55 plan) tracks state but keeps the legacy participant surface:
    ``--checkpoint`` optional and the pre-#55 Commit State / Reviewed
    Candidate rendering (its checkpoint base is the loop base, so the
    checkpoint diff IS the loop diff).
    """
    manifest = checkpoint_manifest(session)
    if manifest is None or manifest.get("source") != "declared":
        return None
    return active_checkpoint(session)


def checkpoint_summary(session):
    """Compact counters for a DECLARED checkpoint loop, else None (#55).

    ``{index, count, id, title, state, findings_round, findings_budget,
    generation}`` built from validated primitives only: ``index`` is
    1-based, ``findings_round`` is the active item's ``findings_rounds``,
    ``findings_budget`` is ``max_rounds`` (the per-checkpoint budget) and
    ``generation`` is the latest submission index, or None before the
    first. Display surfaces use this INSTEAD of ``Round X/Y``, which is
    informational only for checkpoint loops. Implicit (legacy-plan)
    manifests return None and keep the Round display.
    """
    active = declared_checkpoint(session)
    if active is None:
        return None
    idx, item, count = active
    gens = session.get("coding", {}).get("generations")
    n_gens = len(gens) if isinstance(gens, list) else 0
    rounds = item.get("findings_rounds")
    budget = session.get("status", {}).get("max_rounds")
    title = item.get("title")
    return {
        "index": idx + 1,
        "count": count,
        "id": item.get("id") if isinstance(item.get("id"), str) else None,
        "title": title if isinstance(title, str) else "",
        "state": item.get("state") if isinstance(item.get("state"), str)
        else None,
        "findings_round": rounds if isinstance(rounds, int)
        and not isinstance(rounds, bool) else 0,
        "findings_budget": budget if isinstance(budget, int)
        and not isinstance(budget, bool) else 0,
        "generation": n_gens - 1 if n_gens else None,
    }


def build_checkpoint_manifest(items, source, base_tree):
    """A fresh manifest from parsed ``items`` (``{id, title, scope,
    verify}``); the first item is active on ``base_tree``."""
    out = []
    for i, it in enumerate(items):
        out.append({
            "id": it["id"], "title": it["title"],
            "scope": it["scope"], "verify": it["verify"],
            "state": "active" if i == 0 else "pending",
            "base_tree": base_tree if i == 0 else None,
            "findings_rounds": 0, "accepted": None,
        })
    return {"contract": CHECKPOINT_CONTRACT, "source": source,
            "current": 0, "items": out}


IMPLICIT_CHECKPOINT = {
    "id": "cp1", "title": "Full implementation",
    "scope": "The whole approved plan.",
    "verify": "As stated in the approved plan.",
}


def load_session(loop_dir):
    """Read session.json from the loop directory.

    Returns the parsed session dict. Raises on missing or corrupt files.
    """
    session_path = Path(loop_dir) / SESSION_FILENAME
    if not session_path.exists():
        raise FileNotFoundError(f"Session file not found: {session_path}")
    return json.loads(session_path.read_text(encoding="utf-8"))


def save_session(loop_dir, session):
    """Atomically write session.json via temp file + rename.

    On POSIX, also sets read-only permissions (444) after write.
    On Windows, the CLI validation layer is the enforcement boundary.
    """
    target = Path(loop_dir) / SESSION_FILENAME
    # Temporarily make writable if read-only
    _make_writable(target)

    # Atomic write: temp file in same directory, then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(loop_dir), suffix=".tmp", prefix="session-"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
            f.write("\n")
        Path(tmp_path).replace(target)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    _make_readonly(target)


def _make_readonly(path):
    """Set file to read-only on POSIX. No-op on Windows."""
    path = Path(path)
    if not path.exists():
        return
    if sys.platform != "win32":
        os.chmod(path, 0o444)


def _make_writable(path):
    """Restore write permission on POSIX. No-op on Windows."""
    path = Path(path)
    if not path.exists():
        return
    if sys.platform != "win32":
        os.chmod(path, 0o644)


# ---------------------------------------------------------------------------
# Session locking
# ---------------------------------------------------------------------------

def with_session_lock(loop_dir, fn):
    """Acquire exclusive lock, load session, call fn(session), save + emit.

    fn(session) should return (mutated_session, event_dict) to trigger a
    write, or None to skip (e.g., timeout check finds state already advanced).

    Write ordering: session.json is saved BEFORE the event is appended to
    events.jsonl, both inside the lock. This guarantees the host's event-tail
    loop never observes an event whose session state isn't yet durable.
    """
    # Deferred sys.path-based import — avoids circular dependency and
    # works with the repo's script-as-data dispatch model (no relative imports).
    _loop_dir = str(Path(__file__).resolve().parent)
    if _loop_dir not in sys.path:
        sys.path.insert(0, _loop_dir)
    import events as events_mod

    loop_dir = Path(loop_dir)
    lock_path = loop_dir / LOCK_FILENAME
    lock_path.touch(exist_ok=True)

    with open(lock_path, "r+") as lock_fd:
        _lock_exclusive(lock_fd)
        try:
            session = load_session(loop_dir)
            result = fn(session)
            if result is not None:
                mutated_session, event = result
                save_session(loop_dir, mutated_session)
                if event:
                    events_mod.emit_event(loop_dir, event)
            return result
        finally:
            _unlock(lock_fd)


# ---------------------------------------------------------------------------
# Turn tracking
# ---------------------------------------------------------------------------

def get_turn_count(session, role):
    """Count how many turns a role has taken. Used for turn_id sequencing."""
    return sum(1 for t in session.get("turns", []) if t.get("role") == role)


def append_turn(session, role, turn_type, summary, artifact_path=None):
    """Append a turn entry to the session's turns list.

    Returns the turn dict for reference.
    """
    seq = get_turn_count(session, role) + 1
    turn_id = f"{role}-{seq:03d}"
    now = datetime.now(tz=timezone.utc).isoformat()

    turn = {
        "turn_id": turn_id,
        "role": role,
        "type": turn_type,
        "ts": now,
        "round": session["status"]["round"],
        "summary": summary,
    }
    if artifact_path:
        turn["artifact_path"] = artifact_path

    session.setdefault("turns", []).append(turn)
    return turn


# ---------------------------------------------------------------------------
# Token file I/O
# ---------------------------------------------------------------------------

def save_tokens(loop_dir, tokens_data):
    """Write .tokens.json (gitignored, never committed)."""
    tokens_path = Path(loop_dir) / TOKENS_FILENAME
    tokens_path.write_text(
        json.dumps(tokens_data, indent=2) + "\n", encoding="utf-8"
    )


def load_tokens(loop_dir):
    """Read .tokens.json."""
    tokens_path = Path(loop_dir) / TOKENS_FILENAME
    if not tokens_path.exists():
        raise FileNotFoundError(f"Token file not found: {tokens_path}")
    return json.loads(tokens_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Loop ID generation
# ---------------------------------------------------------------------------

def make_loop_id(feature):
    """Generate a loop ID from feature slug + compact ISO timestamp.

    Format: <feature-slug>-<YYYY-MM-DDTHH-MM-SSZ>
    """
    now = datetime.now(tz=timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{feature}-{ts}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deadline_from_now(timeout_seconds):
    """Return an ISO timestamp `timeout_seconds` in the future."""
    from datetime import timedelta
    deadline = datetime.now(tz=timezone.utc) + timedelta(seconds=timeout_seconds)
    return deadline.isoformat()


def ensure_loops_gitignore(loops_dir):
    """Ensure operational files are gitignored in the loops directory."""
    gitignore_path = Path(loops_dir) / ".gitignore"
    rules = [".tokens.json", "session.lock", "host.lock", "start.lock", "*.tmp"]
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8")
        missing = [r for r in rules if r not in existing]
        if not missing:
            return
        content = existing.rstrip("\n") + "\n" + "\n".join(missing) + "\n"
    else:
        content = "\n".join(rules) + "\n"
    gitignore_path.write_text(content, encoding="utf-8")
