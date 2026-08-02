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


def resolve_token(token):
    """Decode a token and validate its nonce against .tokens.json.

    Returns (loop_id, role, loop_dir) on success.
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

    # Resolve loop directory
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
# Session CRUD
# ---------------------------------------------------------------------------

def create_session(feature, loop_id, max_rounds=3, turn_timeout=300):
    """Build the initial session dict.

    Does not write to disk — caller is responsible for saving.
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    deadline = _deadline_from_now(turn_timeout)

    return {
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
    """Ensure .tokens.json files are gitignored in the loops directory."""
    gitignore_path = Path(loops_dir) / ".gitignore"
    rules = [".tokens.json", "session.lock", "*.tmp"]
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8")
        missing = [r for r in rules if r not in existing]
        if not missing:
            return
        content = existing.rstrip("\n") + "\n" + "\n".join(missing) + "\n"
    else:
        content = "\n".join(rules) + "\n"
    gitignore_path.write_text(content, encoding="utf-8")
