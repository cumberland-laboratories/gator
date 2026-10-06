"""
Participant liveness sidecar for gator loop (#36).

Owns: the private, per-worktree liveness store at
``$(git rev-parse --git-path gator-loop-liveness)/<loop_id>.json`` —
schema validation (strict allowlist), atomic persistence, the store's
leaf lock, and the pure helpers used by registration/projection:
``state_key()``, ``classify()``, ``prune()``, ``redact()``.

This store is operational liveness data only. It never holds role tokens,
nonces, prompts, artifacts, model/provider identity, or any
session-authoritative field. ``session.json`` plus the locked submit paths
remain the only loop authority.

LOCK ORDER (leaf lock): the liveness lock is never held while the session
lock is acquired, and no ``with_session_lock`` callback touches this store.
Callers snapshot session state first (unlocked ``load_session``), then take
the liveness lock.
"""

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_loop_dir = str(Path(__file__).resolve().parent)
if _loop_dir not in sys.path:
    sys.path.insert(0, _loop_dir)

from session import _lock_exclusive, _unlock  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
STORE_DIRNAME = "gator-loop-liveness"

MODEL_ROLES = ("draftor", "reviewer")
NOTIFICATION_KINDS = frozenset({"turn-ready", "architect-block", "terminal"})
REGISTRATION_STATES = frozenset({"active", "released", "closed"})
ADAPTER_KINDS = frozenset({"generic-watcher", "custom"})
ADAPTER_CAPABILITIES = frozenset({"poll", "ack"})
CREATED_BY = frozenset({"projection", "architect"})
EXPIRED_REASONS = frozenset({"state_changed", "ttl", "closed"})
RELEASED_REASONS = frozenset({"delivered", "still_waiting", "interrupted"})
AUDIT_ACTIONS = frozenset({"renotify"})
AUDIT_ACTORS = frozenset({"architect"})

DEFAULT_HEARTBEAT_SECONDS = 15
STALE_FACTOR = 3
REGISTRATION_EXPIRY = timedelta(hours=24)
TURN_READY_TTL = timedelta(hours=24)
TERMINAL_RETENTION = timedelta(days=7)
MAX_NOTIFICATIONS_PER_ROLE = 50
MAX_SUPERSEDED_PER_ROLE = 10
MAX_AUDIT_ENTRIES = 100
MAX_LABEL_LEN = 40
MAX_REASON_LEN = 200

TOKEN_PATTERN = re.compile(r"glp_[A-Za-z0-9_\-=]+")
_LOOP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_REG_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_STAGE_RE = re.compile(r"^[a-z_]{1,64}$")

_TOP_KEYS = frozenset({"schema", "loop_id", "roles", "audit",
                       "terminal_observed_at"})
_ROLE_KEYS = frozenset({"registration", "superseded", "next_seq",
                        "notifications"})
_REG_KEYS = frozenset({"registration_id", "generation", "adapter",
                       "registered_at", "last_seen_at", "heartbeat_seconds",
                       "state", "released_reason"})
_ADAPTER_KEYS = frozenset({"kind", "capabilities", "label"})
_SUPERSEDED_KEYS = frozenset({"generation", "superseded_at"})
_NOTIF_KEYS = frozenset({"seq", "kind", "state_key", "stage", "round",
                         "created_at", "created_by", "delivered_at",
                         "delivered_generation", "acked_at",
                         "acked_generation", "expired_at", "expired_reason"})
_AUDIT_KEYS = frozenset({"at", "action", "role", "seq", "actor", "reason"})


class LivenessSchemaError(ValueError):
    """The liveness state violates the schema allowlist."""


class LivenessUnavailableError(OSError):
    """The liveness file cannot be read, or a corrupt file cannot be
    preserved; callers treat delivery as degraded (loop unaffected)."""


# ---------------------------------------------------------------------------
# Text hygiene
# ---------------------------------------------------------------------------

def redact(text):
    """Replace any role-token-shaped substring with a redaction marker."""
    return TOKEN_PATTERN.sub("glp_[REDACTED]", str(text))


def sanitize_text(text, max_len):
    """Redact tokens, keep printable ASCII only, shorten to max_len."""
    cleaned = redact(text)
    cleaned = "".join(ch for ch in cleaned if 32 <= ord(ch) < 127)
    return cleaned[:max_len]


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value):
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------

def empty_role():
    return {"registration": None, "superseded": [], "next_seq": 1,
            "notifications": []}


def empty_state(loop_id):
    return {
        "schema": SCHEMA_VERSION,
        "loop_id": loop_id,
        "roles": {role: empty_role() for role in MODEL_ROLES},
        "audit": [],
        "terminal_observed_at": None,
    }


def validate_loop_id(loop_id):
    if (not isinstance(loop_id, str) or not _LOOP_ID_RE.match(loop_id)
            or ".." in loop_id):
        raise ValueError("invalid loop id for liveness store")
    return loop_id


# ---------------------------------------------------------------------------
# Schema validation (strict allowlist)
# ---------------------------------------------------------------------------

def _fail(path, msg):
    raise LivenessSchemaError(f"{path}: {msg}")


def _check_keys(obj, allowed, path, required=None):
    if not isinstance(obj, dict):
        _fail(path, "must be an object")
    extra = set(obj) - allowed
    if extra:
        _fail(path, f"unexpected keys {sorted(extra)}")
    missing = set(required if required is not None else allowed) - set(obj)
    if missing:
        _fail(path, f"missing keys {sorted(missing)}")


def _check_ts(value, path, nullable=True):
    if value is None:
        if not nullable:
            _fail(path, "timestamp required")
        return
    if not isinstance(value, str):
        _fail(path, "timestamp must be a string")
    try:
        parse_iso(value)
    except (ValueError, TypeError):
        _fail(path, "invalid timestamp")


def _check_int(value, path, minimum=0, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        _fail(path, f"must be an integer >= {minimum}")


def _check_enum(value, allowed, path, nullable=False):
    if value is None and nullable:
        return
    if value not in allowed:
        _fail(path, f"value {value!r} not allowed")


def _check_text(value, max_len, path):
    if not isinstance(value, str):
        _fail(path, "must be a string")
    if len(value) > max_len or value != sanitize_text(value, max_len):
        _fail(path, "text is not sanitized")


def _check_no_tokens(obj, path="$"):
    """Defense in depth: no string anywhere may look like a role token."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            _check_no_tokens(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _check_no_tokens(v, f"{path}[{i}]")
    elif isinstance(obj, str) and TOKEN_PATTERN.search(obj):
        _fail(path, "token-shaped value is forbidden")


def _validate_registration(reg, path):
    _check_keys(reg, _REG_KEYS, path,
                required=_REG_KEYS - {"released_reason"})
    if not isinstance(reg["registration_id"], str) or \
            not _REG_ID_RE.match(reg["registration_id"]):
        _fail(f"{path}.registration_id", "must be 32 lowercase hex chars")
    _check_int(reg["generation"], f"{path}.generation", minimum=1)
    _check_keys(reg["adapter"], _ADAPTER_KEYS, f"{path}.adapter",
                required={"kind", "capabilities"})
    _check_enum(reg["adapter"]["kind"], ADAPTER_KINDS, f"{path}.adapter.kind")
    caps = reg["adapter"]["capabilities"]
    if not isinstance(caps, list) or not set(caps) <= ADAPTER_CAPABILITIES:
        _fail(f"{path}.adapter.capabilities", "unsupported capability")
    if "label" in reg["adapter"]:
        _check_text(reg["adapter"]["label"], MAX_LABEL_LEN,
                    f"{path}.adapter.label")
    _check_ts(reg["registered_at"], f"{path}.registered_at", nullable=False)
    _check_ts(reg["last_seen_at"], f"{path}.last_seen_at", nullable=False)
    _check_int(reg["heartbeat_seconds"], f"{path}.heartbeat_seconds",
               minimum=1)
    _check_enum(reg["state"], REGISTRATION_STATES, f"{path}.state")
    if "released_reason" in reg:
        _check_enum(reg["released_reason"], RELEASED_REASONS,
                    f"{path}.released_reason", nullable=True)


def _validate_notification(n, path):
    _check_keys(n, _NOTIF_KEYS, path)
    _check_int(n["seq"], f"{path}.seq", minimum=1)
    _check_enum(n["kind"], NOTIFICATION_KINDS, f"{path}.kind")
    if not isinstance(n["state_key"], str) or \
            not re.match(r"^[0-9a-f]{64}$", n["state_key"]):
        _fail(f"{path}.state_key", "must be a sha256 hex digest")
    if not isinstance(n["stage"], str) or not _STAGE_RE.match(n["stage"]):
        _fail(f"{path}.stage", "invalid stage")
    _check_int(n["round"], f"{path}.round")
    _check_ts(n["created_at"], f"{path}.created_at", nullable=False)
    _check_enum(n["created_by"], CREATED_BY, f"{path}.created_by")
    _check_ts(n["delivered_at"], f"{path}.delivered_at")
    _check_int(n["delivered_generation"], f"{path}.delivered_generation",
               minimum=1, nullable=True)
    _check_ts(n["acked_at"], f"{path}.acked_at")
    _check_int(n["acked_generation"], f"{path}.acked_generation",
               minimum=1, nullable=True)
    _check_ts(n["expired_at"], f"{path}.expired_at")
    _check_enum(n["expired_reason"], EXPIRED_REASONS,
                f"{path}.expired_reason", nullable=True)


def validate_state(state, loop_id=None):
    """Raise LivenessSchemaError unless ``state`` matches the schema exactly."""
    _check_keys(state, _TOP_KEYS, "$")
    if state["schema"] != SCHEMA_VERSION:
        _fail("$.schema", f"unsupported schema {state['schema']!r}")
    try:
        validate_loop_id(state["loop_id"])
    except ValueError:
        _fail("$.loop_id", "invalid loop id")
    if loop_id is not None and state["loop_id"] != loop_id:
        _fail("$.loop_id", "does not match store loop id")
    _check_ts(state["terminal_observed_at"], "$.terminal_observed_at")

    roles = state["roles"]
    _check_keys(roles, frozenset(MODEL_ROLES), "$.roles")
    for role in MODEL_ROLES:
        rp = f"$.roles.{role}"
        rec = roles[role]
        _check_keys(rec, _ROLE_KEYS, rp)
        if rec["registration"] is not None:
            _validate_registration(rec["registration"], f"{rp}.registration")
        if not isinstance(rec["superseded"], list):
            _fail(f"{rp}.superseded", "must be a list")
        for i, s in enumerate(rec["superseded"]):
            _check_keys(s, _SUPERSEDED_KEYS, f"{rp}.superseded[{i}]")
            _check_int(s["generation"], f"{rp}.superseded[{i}].generation",
                       minimum=1)
            _check_ts(s["superseded_at"],
                      f"{rp}.superseded[{i}].superseded_at", nullable=False)
        _check_int(rec["next_seq"], f"{rp}.next_seq", minimum=1)
        if not isinstance(rec["notifications"], list):
            _fail(f"{rp}.notifications", "must be a list")
        seen = set()
        for i, n in enumerate(rec["notifications"]):
            _validate_notification(n, f"{rp}.notifications[{i}]")
            if n["seq"] in seen or n["seq"] >= rec["next_seq"]:
                _fail(f"{rp}.notifications[{i}].seq",
                      "duplicate or beyond next_seq")
            seen.add(n["seq"])

    if not isinstance(state["audit"], list):
        _fail("$.audit", "must be a list")
    for i, a in enumerate(state["audit"]):
        ap = f"$.audit[{i}]"
        _check_keys(a, _AUDIT_KEYS, ap)
        _check_ts(a["at"], f"{ap}.at", nullable=False)
        _check_enum(a["action"], AUDIT_ACTIONS, f"{ap}.action")
        _check_enum(a["role"], frozenset(MODEL_ROLES), f"{ap}.role")
        _check_int(a["seq"], f"{ap}.seq", minimum=1)
        _check_enum(a["actor"], AUDIT_ACTORS, f"{ap}.actor")
        _check_text(a["reason"], MAX_REASON_LEN, f"{ap}.reason")

    _check_no_tokens(state)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def state_key(session):
    """Idempotency key for one durable loop-state generation (D4).

    Every durable transition changes at least one input: submits append a
    turn and move stage/role, timeouts change stage, unblock/extend append
    a turn and reset the deadline. Rereading unchanged state reproduces it.
    """
    status = session.get("status", {})
    material = {
        "round": status.get("round"),
        "stage": status.get("stage"),
        "next_role": status.get("next_role"),
        "turns": len(session.get("turns", [])),
        "turn_deadline": status.get("turn_deadline"),
    }
    # #47: attention-mode turns have no deadline; their turn identity is
    # turn_started_at. Added only when the key exists, so legacy keys hash
    # exactly as before. attention_notified_turn is deliberately NOT an
    # input: recording attention must never notify or wake a participant.
    if "turn_started_at" in status:
        material["turn_started_at"] = status.get("turn_started_at")
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def classify(role_rec, now):
    """Liveness classification for one role record.

    Returns one of: not_registered, connected, stale, released, closed,
    expired. ``stale`` applies only to ``active`` registrations (D2a); any
    registration unseen for REGISTRATION_EXPIRY is ``expired``.
    """
    reg = role_rec.get("registration") if role_rec else None
    if reg is None:
        return "not_registered"
    age = now - parse_iso(reg["last_seen_at"])
    if age > REGISTRATION_EXPIRY:
        return "expired"
    if reg["state"] == "released":
        return "released"
    if reg["state"] == "closed":
        return "closed"
    if age > timedelta(seconds=STALE_FACTOR * reg["heartbeat_seconds"]):
        return "stale"
    return "connected"


def is_pending(notification):
    """Not yet acknowledged and not expired."""
    return (notification["acked_at"] is None
            and notification["expired_at"] is None)


def prune(state, now, loop_exists=True):
    """Apply retention (D6). Returns (state, delete_file).

    Mutates ``state`` in place. ``delete_file`` is True when the loop
    directory is gone or the loop has been terminal for TERMINAL_RETENTION.
    Pending notifications are never dropped by the size cap, so a role
    whose records are all pending may exceed MAX_NOTIFICATIONS_PER_ROLE
    (delivery safety over the size bound; pending records still TTL-expire).
    """
    if not loop_exists:
        return state, True
    term = parse_iso(state.get("terminal_observed_at"))
    if term is not None and now - term > TERMINAL_RETENTION:
        return state, True

    for role in MODEL_ROLES:
        rec = state["roles"][role]
        if classify(rec, now) == "expired":
            rec["registration"] = None
        rec["superseded"] = rec["superseded"][-MAX_SUPERSEDED_PER_ROLE:]

        for n in rec["notifications"]:
            if (n["kind"] == "turn-ready" and is_pending(n)
                    and now - parse_iso(n["created_at"]) > TURN_READY_TTL):
                n["expired_at"] = iso(now)
                n["expired_reason"] = "ttl"

        notes = rec["notifications"]
        overflow = len(notes) - MAX_NOTIFICATIONS_PER_ROLE
        if overflow > 0:
            drop = set()
            for n in notes:  # oldest first
                if len(drop) >= overflow:
                    break
                if not is_pending(n):
                    drop.add(n["seq"])
            rec["notifications"] = [n for n in notes if n["seq"] not in drop]

    state["audit"] = state["audit"][-MAX_AUDIT_ENTRIES:]
    return state, False


# ---------------------------------------------------------------------------
# Store location
# ---------------------------------------------------------------------------

def resolve_store_dir(repo_root, runner=None):
    """Return the per-worktree store directory, or None when unavailable.

    Uses ``git rev-parse --git-path gator-loop-liveness`` so the store sits
    beside #34's ``gator-override`` state: never staged, never served.
    """
    runner = runner or subprocess.run
    repo_root = Path(repo_root)
    try:
        proc = runner(
            ["git", "-C", str(repo_root), "rev-parse", "--git-path",
             STORE_DIRNAME],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class LivenessStore:
    """One loop's liveness file plus its leaf lock.

    ``read()`` is lock-free and side-effect free (Dashboard observer).
    ``with_lock(fn)`` is the only mutation path: it loads (quarantining a
    corrupt file), calls ``fn(state)``, and saves when fn returns
    ``(new_state, value)`` with a non-None new_state.
    """

    REPLACE_ATTEMPTS = 5
    REPLACE_DELAY = 0.02

    def __init__(self, store_dir, loop_id):
        self.store_dir = Path(store_dir)
        self.loop_id = validate_loop_id(loop_id)
        self.path = self.store_dir / f"{loop_id}.json"
        self.lock_path = self.store_dir / f"{loop_id}.lock"
        self.last_error = None

    # -- reading ----------------------------------------------------------

    def _load(self, quarantine):
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return empty_state(self.loop_id)
        except OSError as exc:
            raise LivenessUnavailableError(
                f"liveness file unreadable: {type(exc).__name__}") from exc
        try:
            state = json.loads(raw)
            validate_state(state, loop_id=self.loop_id)
        except (ValueError, LivenessSchemaError):
            self.last_error = "corrupt"
            if quarantine and not self._quarantine():
                # Never let a mutation replace the only copy of a corrupt
                # file: refuse until the original has been preserved.
                self.last_error = "quarantine_failed"
                raise LivenessUnavailableError(
                    "corrupt liveness file could not be preserved")
            return empty_state(self.loop_id)
        return state

    def read(self):
        """Lock-free snapshot for observers.

        A corrupt file reads as empty and is left untouched. A transient
        read error (e.g. Windows sharing violation) is retried briefly, then
        returns None with ``last_error = "unavailable"`` — callers treat
        that as retry/degraded.
        """
        for attempt in range(self.REPLACE_ATTEMPTS):
            try:
                return self._load(quarantine=False)
            except LivenessUnavailableError:
                # Windows: a writer's os.replace can briefly deny reads.
                if attempt < self.REPLACE_ATTEMPTS - 1:
                    time.sleep(self.REPLACE_DELAY)
        self.last_error = "unavailable"
        return None

    def _quarantine(self):
        """Rename the corrupt file aside. Returns True only if the original
        is preserved (renamed) or already gone."""
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        for attempt in range(self.REPLACE_ATTEMPTS):
            try:
                os.replace(str(self.path), str(target))
                return True
            except FileNotFoundError:
                return True
            except OSError:
                if attempt < self.REPLACE_ATTEMPTS - 1:
                    time.sleep(self.REPLACE_DELAY)
        return False

    # -- writing ----------------------------------------------------------

    def _save(self, state):
        validate_state(state, loop_id=self.loop_id)
        fd, tmp = tempfile.mkstemp(dir=str(self.store_dir),
                                   prefix=f".{self.loop_id}-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(state, f, indent=2, sort_keys=True)
                f.write("\n")
            for attempt in range(self.REPLACE_ATTEMPTS):
                try:
                    os.replace(tmp, str(self.path))
                    break
                except PermissionError:
                    # Windows: a lock-free reader may hold the file open.
                    if attempt == self.REPLACE_ATTEMPTS - 1:
                        raise
                    time.sleep(self.REPLACE_DELAY)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def with_lock(self, fn):
        """Run ``fn(state)`` under the leaf lock; persist if it asks to.

        ``fn`` returns ``(new_state_or_None, value)``; returns ``value``.
        Raises LivenessUnavailableError (without calling ``fn``) when the
        file is unreadable or a corrupt file could not be quarantined.
        Must never be called while holding the session lock's callback, and
        ``fn`` must never acquire the session lock (leaf-lock invariant).
        """
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path.touch(exist_ok=True)
        with open(self.lock_path, "r+") as lock_fd:
            _lock_exclusive(lock_fd)
            try:
                state = self._load(quarantine=True)
                new_state, value = fn(state)
                if new_state is not None:
                    self._save(new_state)
                return value
            finally:
                _unlock(lock_fd)

    def delete(self):
        """Remove the loop's liveness file (retention). Lock file is kept
        only while held; removed best-effort afterwards."""
        def _rm(_state):
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            return None, True
        if not self.store_dir.exists():
            return False
        self.with_lock(_rm)
        try:
            self.lock_path.unlink()
        except OSError:
            pass
        return True


# ---------------------------------------------------------------------------
# Participant API (M2): register / heartbeat / poll / ack / release
# ---------------------------------------------------------------------------
#
# Every call re-authenticates with the role token (resolve_token against the
# gitignored .tokens.json) AND presents the opaque registration_id. The token
# is resolved immediately and never stored, echoed, or logged; the
# registration_id is returned only to the calling process and never exposed
# by any observer view.

PARTICIPANT_SCHEMA = "gator-loop-participant-v1"

WATCH_EXIT_ACT = 0
WATCH_EXIT_ERROR = 1
WATCH_EXIT_PAUSED_OR_ENDED = 2
WATCH_EXIT_STILL_WAITING = 3
WATCH_EXIT_SUPERSEDED = 4
WATCH_EXIT_INTERRUPTED = 130

# kind -> (exit code, wake_reason, registration state after delivery).
# #53: ``architect-block`` is deliberately absent: a paused or blocked loop
# is not a reason to stop. The watcher acks it and keeps watching, staying
# registered, until turn-ready, terminal, or its own deadline. (Older
# watchers exited ``2 architect_block``; the protocol says relaunch.)
_DELIVERY_OUTCOME = {
    "turn-ready": (WATCH_EXIT_ACT, "turn_ready", "released"),
    "terminal": (WATCH_EXIT_PAUSED_OR_ENDED, "terminal", "closed"),
}


class SupersededError(Exception):
    """The presented registration is no longer the role's current one."""


class RegistrationClosedError(Exception):
    """The presented registration is current but ``closed`` (terminal).

    ``closed`` is one-way: heartbeat/poll/ack/release never revive it. Only
    a fresh ``register()`` (a newly launched watcher) supersedes it.
    """


def _now(now=None):
    return now or datetime.now(tz=timezone.utc)


def authenticate(token, loop_dir=None):
    """Resolve a participant token. Returns (loop_id, role, loop_dir).

    Raises ValueError (redacted) for invalid tokens and PermissionError for
    the architect token — participant liveness is for model roles only.
    """
    from session import resolve_token
    try:
        loop_id, role, resolved = resolve_token(token, loop_dir)
    except ValueError as exc:
        raise ValueError(redact(exc)) from None
    if role not in MODEL_ROLES:
        raise PermissionError(
            "participant liveness is for draftor/reviewer tokens only")
    return loop_id, role, Path(resolved)


def open_store(loop_dir, store_dir=None):
    """Store for a loop directory (<repo>/.gator/loops/<id>).

    Raises LivenessUnavailableError when no Git-private store path exists.
    ``store_dir`` is a test seam.
    """
    loop_dir = Path(loop_dir)
    if store_dir is None:
        store_dir = resolve_store_dir(loop_dir.parent.parent.parent)
    if store_dir is None:
        raise LivenessUnavailableError(
            "liveness delivery unavailable (not a Git worktree)")
    return LivenessStore(store_dir, loop_dir.name)


PROJECT_UNCHANGED = "unchanged"
PROJECT_UPDATED = "updated"
PROJECT_RETRY = "retry"
PROJECT_DELETED = "deleted"


def _has_record(rec, kind, key):
    return any(n["kind"] == kind and n["state_key"] == key
               for n in rec["notifications"])


def _append_record(rec, kind, key, stage, rnd, ts, created_by="projection"):
    seq = rec["next_seq"]
    rec["notifications"].append({
        "seq": seq, "kind": kind, "state_key": key, "stage": stage,
        "round": rnd, "created_at": ts, "created_by": created_by,
        "delivered_at": None, "delivered_generation": None,
        "acked_at": None, "acked_generation": None,
        "expired_at": None, "expired_reason": None,
    })
    rec["next_seq"] = seq + 1
    return seq


def _apply_projection(state, session, now):
    """Pure D5 rules. Mutates ``state``; returns nothing.

    - Any pending record from an older state generation expires
      (``state_changed``) — only the current generation is actionable.
    - Active: one ``turn-ready`` per (next_role, state_key), recorded even
      for an unregistered role so a later watcher catches the current turn.
    - Paused: one ``architect-block`` per registered, non-closed role.
    - Terminal: one ``terminal`` per registered, non-closed role that has
      never been told for this generation; a registration whose terminal
      record was already delivered/acked (or that never needs one) is
      closed so a late watcher exits at once. ``terminal_observed_at`` set.
    - Non-terminal (e.g. after a #39 extension): ``terminal_observed_at``
      cleared.

    Never reopens a ``closed`` registration and never touches session or
    event state.
    """
    from state_machine import is_active, is_paused, is_terminal

    status = session["status"]
    stage = status["stage"]
    rnd = int(status.get("round") or 0)
    key = state_key(session)
    ts = iso(now)

    for role in MODEL_ROLES:
        for n in state["roles"][role]["notifications"]:
            if is_pending(n) and n["state_key"] != key:
                n["expired_at"] = ts
                n["expired_reason"] = "state_changed"

    def _open_registration(role):
        reg = state["roles"][role]["registration"]
        return reg is not None and reg["state"] != "closed"

    if is_active(session):
        state["terminal_observed_at"] = None
        role = status.get("next_role")
        if role in MODEL_ROLES:
            rec = state["roles"][role]
            if not _has_record(rec, "turn-ready", key):
                _append_record(rec, "turn-ready", key, stage, rnd, ts)
    elif is_paused(session):
        state["terminal_observed_at"] = None
        for role in MODEL_ROLES:
            rec = state["roles"][role]
            if _open_registration(role) and \
                    not _has_record(rec, "architect-block", key):
                _append_record(rec, "architect-block", key, stage, rnd, ts)
    elif is_terminal(session):
        if state["terminal_observed_at"] is None:
            state["terminal_observed_at"] = ts
        for role in MODEL_ROLES:
            rec = state["roles"][role]
            if not _open_registration(role):
                continue
            if not _has_record(rec, "terminal", key):
                _append_record(rec, "terminal", key, stage, rnd, ts)
            elif not any(n["kind"] == "terminal" and n["state_key"] == key
                         and is_pending(n) for n in rec["notifications"]):
                # Already told (acked) for this generation: close so a late
                # watcher exits immediately instead of waiting it out.
                rec["registration"]["state"] = "closed"
                rec["registration"].setdefault("released_reason",
                                               "delivered")


def project(loop_dir, store, now=None):
    """Project the durable loop state into notifications (D5).

    Lock order: snapshot ``session.json`` WITHOUT the session lock, then
    take only the liveness (leaf) lock. A torn/locked read (Windows rename
    race) returns ``retry``; the next tick tries again. A vanished loop
    directory deletes the sidecar file. Idempotent: rereading unchanged
    state writes nothing. Returns unchanged / updated / retry / deleted.
    """
    import copy
    from session import load_session

    now = _now(now)
    loop_dir = Path(loop_dir)
    if not loop_dir.is_dir():
        if store.path.exists():
            store.delete()
        return PROJECT_DELETED
    try:
        session = load_session(loop_dir)
        session["status"]["stage"]
    except (OSError, ValueError, KeyError, TypeError):
        return PROJECT_RETRY

    def _fn(state):
        before = copy.deepcopy(state)
        _apply_projection(state, session, now)
        state, delete = prune(state, now, loop_exists=True)
        if delete:
            return None, PROJECT_DELETED
        if state == before:
            return None, PROJECT_UNCHANGED
        return state, PROJECT_UPDATED

    result = store.with_lock(_fn)
    if result == PROJECT_DELETED:
        store.delete()
    return result


def renotify_eligibility(state, session, role, now=None):
    """Pure D7 eligibility for an Architect Re-notify. Returns
    (eligible, reason_code) with reason_code None when eligible, else
    ``terminal`` / ``already_acknowledged`` / ``not_actionable``.

    Eligible when the role owns the current active turn, or when it has a
    pending (unacked, unexpired) record and no live watcher (stale /
    released / not registered / expired). Rate limiting is endpoint-level.
    """
    from state_machine import is_active, is_terminal
    if role not in MODEL_ROLES:
        return False, "not_actionable"
    status = session["status"]
    if is_terminal(session):
        return False, "terminal"
    if is_active(session) and status.get("next_role") == role:
        return True, None
    rec = state["roles"][role]
    notes = rec["notifications"]
    if any(is_pending(n) for n in notes):
        if classify(rec, _now(now)) != "connected":
            return True, None
        return False, "not_actionable"
    if notes and notes[-1]["acked_at"] is not None:
        return False, "already_acknowledged"
    return False, "not_actionable"


OBSERVER_SCHEMA = "gator-loop-liveness-view-v1"

# Dashboard-facing role states (``expired`` is shown as not registered).
_OBSERVER_STATE = {"expired": "not_registered"}


def observer_view(state, session, now=None):
    """Explicit allowlist serializer for the Architect Dashboard (D8).

    Never includes registration ids, seq lists, state keys, raw queue
    records, adapter labels, or audit reasons — the audit trail is only a
    count plus the last actor/time. ``session`` may be None (unreadable):
    Re-notify eligibility is then reported false with ``session_unreadable``.
    """
    now = _now(now)
    roles = {}
    for role in MODEL_ROLES:
        rec = state["roles"][role]
        reg = rec["registration"]
        notes = rec["notifications"]
        last = notes[-1] if notes else None
        if session is not None:
            eligible, code = renotify_eligibility(state, session, role, now)
        else:
            eligible, code = False, "session_unreadable"
        cls = classify(rec, now)
        roles[role] = {
            "state": _OBSERVER_STATE.get(cls, cls),
            "adapter_kind": reg["adapter"]["kind"] if reg else None,
            "last_seen_at": reg["last_seen_at"] if reg else None,
            "pending": sum(1 for n in notes if is_pending(n)),
            "last_notification": ({
                "kind": last["kind"],
                "created_at": last["created_at"],
                "created_by": last["created_by"],
                "delivered_at": last["delivered_at"],
                "acked_at": last["acked_at"],
                "expired_reason": last["expired_reason"],
            } if last else None),
            "renotify_eligible": eligible,
            "renotify_reason_code": code,
        }
    audit = state["audit"]
    return {
        "schema": OBSERVER_SCHEMA,
        "roles": roles,
        "audit": {
            "renotify_count": len(audit),
            "last_at": audit[-1]["at"] if audit else None,
            "last_actor": audit[-1]["actor"] if audit else None,
        },
    }


def renotify(loop_dir, store, role, reason, now=None):
    """Architect Re-notify (D7): append one notification + audit entry.

    Snapshots the session WITHOUT the session lock, then decides and writes
    under the liveness leaf lock only. Never touches session.json,
    events.jsonl, deadlines, or next_role. Returns
    (ok, reason_code, kind): the new record repeats the current turn's
    ``turn-ready`` for the turn owner, otherwise the kind of the role's
    newest pending record, with the same state_key.
    """
    from session import load_session
    from state_machine import is_active

    now = _now(now)
    ts = iso(now)
    if role not in MODEL_ROLES:
        return False, "not_actionable", None
    session = load_session(loop_dir)
    reason = sanitize_text(reason or "", MAX_REASON_LEN).strip() or \
        "Architect re-notify"

    def _fn(state):
        eligible, code = renotify_eligibility(state, session, role, now)
        if not eligible:
            return None, (False, code, None)
        rec = state["roles"][role]
        status = session["status"]
        if is_active(session) and \
                status.get("next_role") == role:
            kind, key = "turn-ready", state_key(session)
            stage, rnd = status["stage"], int(status.get("round") or 0)
        else:
            src = [n for n in rec["notifications"] if is_pending(n)][-1]
            kind, key, stage, rnd = (src["kind"], src["state_key"],
                                     src["stage"], src["round"])
        seq = _append_record(rec, kind, key, stage, rnd, ts,
                             created_by="architect")
        state["audit"].append({"at": ts, "action": "renotify", "role": role,
                               "seq": seq, "actor": "architect",
                               "reason": reason})
        state["audit"] = state["audit"][-MAX_AUDIT_ENTRIES:]
        return state, (True, None, kind)

    return store.with_lock(_fn)


def sweep(repo_root, now=None):
    """Retention sweep over every sidecar file of one worktree (D6).

    Projects each loop that still exists (applying prune/terminal retention)
    and deletes files whose loop directory is gone. Best-effort: never
    raises. Returns {loop_id: result}.
    """
    results = {}
    try:
        store_dir = resolve_store_dir(repo_root)
        if store_dir is None or not store_dir.is_dir():
            return results
        loops_root = Path(repo_root) / ".gator" / "loops"
        for f in sorted(store_dir.glob("*.json")):
            loop_id = f.stem
            try:
                validate_loop_id(loop_id)
                store = LivenessStore(store_dir, loop_id)
                results[loop_id] = project(loops_root / loop_id, store,
                                           now=now)
            except Exception:
                results[loop_id] = "error"
    except Exception:
        pass
    return results


def open_host_store(loop_dir):
    """Best-effort store for a hosting watcher; None when unavailable."""
    try:
        return open_store(loop_dir)
    except Exception:
        return None


def project_for_host(loop_dir, store):
    """Guarded projection for ``watch_loop``: never raises.

    Records a sanitized ``last_error`` on the store object on failure so an
    in-process observer can show degraded delivery; loop state is never
    touched either way.
    """
    if store is None:
        return None
    try:
        result = project(loop_dir, store)
        if result in (PROJECT_UPDATED, PROJECT_UNCHANGED):
            store.last_error = None
        return result
    except Exception as exc:
        store.last_error = "projection_failed"
        if os.environ.get("GATOR_DASHBOARD_DEBUG") == "1":
            print(f"[liveness] projection failed: "
                  f"{sanitize_text(exc, 200)}", file=sys.stderr, flush=True)
        return "error"


def _safe_project(loop_dir, store, now=None):
    try:
        return project(loop_dir, store, now=now)
    except Exception:
        store.last_error = "projection_failed"
        return "error"


def _current_registration(state, role, registration_id):
    reg = state["roles"][role]["registration"]
    if reg is None or not hmac.compare_digest(
            reg["registration_id"], str(registration_id)):
        raise SupersededError("registration superseded or expired")
    if reg["state"] == "closed":
        raise RegistrationClosedError("registration closed (loop ended)")
    return reg


def public_notification(n):
    """Participant-facing view of a record (no state_key/audit internals)."""
    return {"seq": n["seq"], "kind": n["kind"], "stage": n["stage"],
            "round": n["round"], "created_at": n["created_at"],
            "created_by": n["created_by"]}


def register(token, adapter_label=None, heartbeat_seconds=None,
             loop_dir=None, store_dir=None, now=None):
    """Register a receiver for the token's role; supersede any prior one.

    Returns {"registration_id", "generation", "role", "loop_id",
    "loop_dir"} — the registration_id stays in the caller's memory only.
    """
    loop_id, role, loop_dir = authenticate(token, loop_dir)
    store = open_store(loop_dir, store_dir)
    ts = iso(_now(now))
    hb = int(heartbeat_seconds or DEFAULT_HEARTBEAT_SECONDS)
    adapter = {"kind": "generic-watcher", "capabilities": ["poll", "ack"]}
    label = sanitize_text(adapter_label, MAX_LABEL_LEN) if adapter_label \
        else ""
    if label:
        adapter["label"] = label
    reg_id = secrets.token_hex(16)

    def _fn(state):
        rec = state["roles"][role]
        prior = rec["registration"]
        # Generation is monotonic over ALL history (current, superseded,
        # and any generation a record was delivered/acked to), so a
        # registration dropped by retention can never be reissued and a
        # new receiver always gets pending records redelivered.
        seen = [s["generation"] for s in rec["superseded"]]
        for n in rec["notifications"]:
            seen.extend(g for g in (n["delivered_generation"],
                                    n["acked_generation"]) if g)
        if prior is not None:
            seen.append(prior["generation"])
            rec["superseded"].append({"generation": prior["generation"],
                                      "superseded_at": ts})
        generation = max(seen, default=0) + 1
        rec["registration"] = {
            "registration_id": reg_id, "generation": generation,
            "adapter": adapter, "registered_at": ts, "last_seen_at": ts,
            "heartbeat_seconds": hb, "state": "active",
        }
        rec["superseded"] = rec["superseded"][-MAX_SUPERSEDED_PER_ROLE:]
        return state, generation

    generation = store.with_lock(_fn)
    _safe_project(loop_dir, store, now=now)
    return {"registration_id": reg_id, "generation": generation,
            "role": role, "loop_id": loop_id, "loop_dir": loop_dir}


def heartbeat(token, registration_id, loop_dir=None, store_dir=None,
              now=None):
    """Refresh last_seen_at for the current registration (re-activates)."""
    loop_id, role, loop_dir = authenticate(token, loop_dir)
    store = open_store(loop_dir, store_dir)
    ts = iso(_now(now))

    def _fn(state):
        reg = _current_registration(state, role, registration_id)
        reg["last_seen_at"] = ts
        reg["state"] = "active"
        reg.pop("released_reason", None)
        return state, None

    store.with_lock(_fn)


def poll(token, registration_id, loop_dir=None, store_dir=None, now=None):
    """Heartbeat + fetch this receiver's deliverable notifications.

    Deliverable = pending (unacked, unexpired) and not yet delivered to this
    generation, so a new receiver picks up records an old one never acked.
    Stamps delivered_at/delivered_generation. Returns public views.
    """
    loop_id, role, loop_dir = authenticate(token, loop_dir)
    store = open_store(loop_dir, store_dir)
    _safe_project(loop_dir, store, now=now)
    ts = iso(_now(now))

    def _fn(state):
        reg = _current_registration(state, role, registration_id)
        reg["last_seen_at"] = ts
        gen = reg["generation"]
        out = []
        for n in state["roles"][role]["notifications"]:
            if is_pending(n) and n["delivered_generation"] != gen:
                n["delivered_at"] = ts
                n["delivered_generation"] = gen
                out.append(public_notification(n))
        return state, out

    return store.with_lock(_fn)


def ack(token, registration_id, seq, loop_dir=None, store_dir=None,
        now=None):
    """Acknowledge one record: received, NOT read/complied/submitted.

    Only the current generation may ack, and only its own role's records
    that were delivered to it. Returns True if newly acked, False if it was
    already acked or has expired.
    """
    loop_id, role, loop_dir = authenticate(token, loop_dir)
    store = open_store(loop_dir, store_dir)
    ts = iso(_now(now))

    def _fn(state):
        reg = _current_registration(state, role, registration_id)
        gen = reg["generation"]
        for n in state["roles"][role]["notifications"]:
            if n["seq"] == seq:
                if n["delivered_generation"] != gen:
                    raise SupersededError(
                        "record was not delivered to this registration")
                if not is_pending(n):
                    return None, False
                n["acked_at"] = ts
                n["acked_generation"] = gen
                return state, True
        raise KeyError(f"no notification {seq} for this role")

    return store.with_lock(_fn)


def release(token, registration_id, reason, closed=False, loop_dir=None,
            store_dir=None, now=None):
    """Mark the receiver released (normal exit) or closed (terminal)."""
    if reason not in RELEASED_REASONS:
        raise ValueError("invalid release reason")
    loop_id, role, loop_dir = authenticate(token, loop_dir)
    store = open_store(loop_dir, store_dir)
    ts = iso(_now(now))

    def _fn(state):
        reg = _current_registration(state, role, registration_id)
        reg["state"] = "closed" if closed else "released"
        reg["released_reason"] = reason
        reg["last_seen_at"] = ts
        return state, None

    store.with_lock(_fn)


def own_status(token, loop_dir=None, store_dir=None, now=None):
    """Read-only summary of the caller's own role (never the other role)."""
    loop_id, role, loop_dir = authenticate(token, loop_dir)
    base = {"schema": PARTICIPANT_SCHEMA, "loop_id": loop_id, "role": role}
    try:
        store = open_store(loop_dir, store_dir)
    except LivenessUnavailableError:
        return dict(base, available=False, state="unavailable")
    state = store.read()
    if state is None:
        return dict(base, available=False, state="unavailable")
    rec = state["roles"][role]
    reg = rec["registration"]
    notes = rec["notifications"]
    last = notes[-1] if notes else None
    return dict(
        base, available=True,
        state=classify(rec, _now(now)),
        generation=reg["generation"] if reg else None,
        last_seen_at=reg["last_seen_at"] if reg else None,
        pending=sum(1 for n in notes if is_pending(n)),
        last_notification=(dict(public_notification(last),
                                delivered_at=last["delivered_at"],
                                acked_at=last["acked_at"],
                                expired_reason=last["expired_reason"])
                           if last else None),
    )


# ---------------------------------------------------------------------------
# Watcher (D2a receiver contract)
# ---------------------------------------------------------------------------

def _suspension_fields(loop_dir):
    """Additive ``still_waiting`` fields (#53): ``suspended: True`` and the
    paused ``stage`` when the loop is suspended. One unlocked session read;
    any failure (torn read, missing file) omits the fields."""
    try:
        from session import load_session
        from state_machine import is_paused
        session = load_session(Path(loop_dir))
        if is_paused(session):
            return {"suspended": True, "stage": session["status"]["stage"]}
    except Exception:
        pass
    return {}


def run_watch(token, max_seconds, poll_seconds=5.0, adapter_label=None,
              loop_dir=None, store_dir=None, clock=None, sleep=None):
    """Register, poll, ack; return (exit_code, payload) for one delivery.

    Delivers the newest actionable record (state is linear, so it reflects
    the current loop state) and acks every record received in that poll.
    #53: an ``architect-block`` (paused or blocked loop) is acked and the
    watch continues with the registration still active -- suspension is not
    departure. Registration state afterwards: released on turn-ready /
    still-waiting, closed on terminal, untouched when superseded. KeyboardInterrupt releases best-effort ("interrupted").
    Never loops forever and never relaunches itself.
    """
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    base = {"schema": PARTICIPANT_SCHEMA}
    try:
        hb = max(DEFAULT_HEARTBEAT_SECONDS, int(math.ceil(poll_seconds)))
        reg = register(token, adapter_label=adapter_label,
                       heartbeat_seconds=hb, loop_dir=loop_dir,
                       store_dir=store_dir)
    except (ValueError, PermissionError, OSError,
            LivenessSchemaError) as exc:
        return WATCH_EXIT_ERROR, dict(base, wake_reason="error",
                                      error=redact(exc))
    base.update(loop_id=reg["loop_id"], role=reg["role"])
    rid = reg["registration_id"]
    kw = {"loop_dir": reg["loop_dir"], "store_dir": store_dir}
    deadline = clock() + max_seconds

    try:
        while True:
            notes = poll(token, rid, **kw)
            if notes:
                for n in notes:
                    ack(token, rid, n["seq"], **kw)
                actionable = [n for n in notes
                              if n["kind"] in _DELIVERY_OUTCOME]
                if actionable:
                    chosen = max(actionable, key=lambda n: n["seq"])
                    code, wake, reg_state = _DELIVERY_OUTCOME[chosen["kind"]]
                    release(token, rid, "delivered",
                            closed=(reg_state == "closed"), **kw)
                    return code, dict(base, wake_reason=wake, acked=True,
                                      kind=chosen["kind"], seq=chosen["seq"],
                                      stage=chosen["stage"],
                                      round=chosen["round"])
                # Only architect-block records: received (acked) and the
                # watch continues; the registration stays active (#53).
            remaining = deadline - clock()
            if remaining <= 0:
                release(token, rid, "still_waiting", **kw)
                return WATCH_EXIT_STILL_WAITING, dict(
                    base, wake_reason="still_waiting",
                    max_seconds=max_seconds,
                    **_suspension_fields(reg["loop_dir"]))
            sleep(min(poll_seconds, remaining))
    except SupersededError:
        return WATCH_EXIT_SUPERSEDED, dict(base, wake_reason="superseded")
    except RegistrationClosedError:
        # Closed by the terminal path (e.g. M3 projection): report terminal
        # without writing — closed is one-way.
        return WATCH_EXIT_PAUSED_OR_ENDED, dict(base, wake_reason="terminal")
    except KeyboardInterrupt:
        try:
            release(token, rid, "interrupted", **kw)
        except Exception:
            pass
        return WATCH_EXIT_INTERRUPTED, dict(base, wake_reason="interrupted")
    except (ValueError, PermissionError, KeyError, OSError,
            LivenessSchemaError) as exc:
        return WATCH_EXIT_ERROR, dict(base, wake_reason="error",
                                      error=redact(exc))
