"""
Host process for gator loop.

Owns: loop initialization (gator loop start) and the watch loop that
tails events.jsonl, renders log lines, and enforces turn timeouts.

The host is a READER during normal operation — submit commands are the
canonical writers. The one exception is timeout enforcement: only the
host can observe that nothing happened within a deadline.

Host Contract:
  Initialization:     writes session.json, events.jsonl, sketch.md, .tokens.json
  Normal operation:   reads events.jsonl (tail) + session.json (deadline check)
  Timeout enforcement: writes session.json + events.jsonl (inside session lock)
"""

import json as _json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_LOOP_DIR = str(Path(__file__).resolve().parent)
if _LOOP_DIR not in sys.path:
    sys.path.insert(0, _LOOP_DIR)

from session import (
    create_session, save_session, load_session, with_session_lock,
    make_token, save_tokens, make_loop_id,
    find_gator_root, ensure_loops_gitignore,
    _make_readonly,
)
from events import (
    emit_event, create_events_file, format_event, format_next_prompt,
    TERMINAL_EVENTS,
)
from state_machine import (
    is_active, is_paused, is_terminal,
    advance_turn_timed_out, ACTIVE_STAGES,
)


# ---------------------------------------------------------------------------
# Watch loop polling interval
# ---------------------------------------------------------------------------

POLL_INTERVAL = 2.0  # seconds

HOST_LOCK_FILENAME = "host.lock"
START_LOCK_FILENAME = "start.lock"


# ---------------------------------------------------------------------------
# Platform-aware non-blocking exclusive file lock
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    import msvcrt

    def _try_lock_exclusive_nb(fd):
        """Try non-blocking exclusive lock. Returns True on success."""
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except (OSError, IOError):
            return False

    def _unlock_fd(fd):
        """Release lock on raw fd (Windows)."""
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except (OSError, IOError):
            pass
else:
    import fcntl

    def _try_lock_exclusive_nb(fd):
        """Try non-blocking exclusive lock. Returns True on success."""
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, IOError):
            return False

    def _unlock_fd(fd):
        """Release lock on raw fd (POSIX)."""
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except (OSError, IOError):
            pass


def _try_host_lock(loop_dir):
    """One non-blocking host.lock attempt.

    Returns (fd, None) on success, (None, "held") when another holder has
    it, or (None, "open failed: <err>") when the lock file cannot be opened.
    """
    lock_path = Path(loop_dir) / HOST_LOCK_FILENAME
    try:
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    except OSError as exc:
        return None, f"open failed: {exc}"
    if _try_lock_exclusive_nb(fd):
        return fd, None
    os.close(fd)
    return None, "held"


def acquire_host_lock(loop_dir):
    """Open and acquire host.lock non-blocking. Returns fd or None."""
    fd, _ = _try_host_lock(loop_dir)
    return fd


HOST_ATTACHED = "attached"
HOST_ALREADY_HOSTED = "already_hosted"
HOST_FAILED = "failed"


def acquire_host_lock_with_retry(loop_dir, attempts=15, delay=0.2, sleep=None):
    """Acquire host.lock, retrying briefly while another holder releases it.

    Used when attaching a watcher to a loop that just became active again
    (#39): the watcher that saw the terminal event may still be releasing
    its lock. Returns (fd, state, detail):

      (fd,   "attached",       None)   lock acquired — caller owns the fd
      (None, "already_hosted", detail) still held after all attempts; a live
                                        process owns host.lock (the OS drops
                                        locks of dead processes), so the loop
                                        is hosted — never start a second one
      (None, "failed",         detail) the lock file could not be opened

    ``sleep`` is a test seam (default time.sleep).
    """
    sleep = sleep or time.sleep
    attempts = max(1, int(attempts))
    for i in range(attempts):
        fd, err = _try_host_lock(loop_dir)
        if fd is not None:
            return fd, HOST_ATTACHED, None
        if err != "held":
            return None, HOST_FAILED, err
        if i < attempts - 1:
            sleep(delay)
    meta = read_host_metadata(loop_dir)
    pid = meta.get("pid") if meta else None
    detail = (f"host.lock held by pid {pid}" if pid
              else "host.lock held by another process")
    return None, HOST_ALREADY_HOSTED, detail


def read_host_metadata(loop_dir):
    """Best-effort, non-locking read of host.lock diagnostic metadata.

    Returns a dict (pid, nonce, started_at) or None. On Windows the held
    byte range is unreadable by other handles, so None is common there.
    """
    lock_path = Path(loop_dir) / HOST_LOCK_FILENAME
    try:
        text = lock_path.read_text(encoding="utf-8")
        data = _json.loads(text) if text.strip() else None
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def release_host_lock(fd):
    """Release and close a held host lock fd."""
    if fd is None:
        return
    try:
        _unlock_fd(fd)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def acquire_start_lock(loops_base):
    """Open and acquire start.lock non-blocking. Returns fd or None."""
    lock_path = Path(loops_base) / START_LOCK_FILENAME
    try:
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    except OSError:
        return None
    if _try_lock_exclusive_nb(fd):
        return fd
    os.close(fd)
    return None


def release_start_lock(fd):
    """Release and close a held start lock fd."""
    release_host_lock(fd)


def write_host_metadata(fd, nonce):
    """Write diagnostic metadata to the host lock file."""
    import secrets
    meta = _json.dumps({
        "pid": os.getpid(),
        "nonce": nonce,
        "started_at": datetime.now(tz=timezone.utc).isoformat(),
    })
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, meta.encode("utf-8"))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Initialization — extracted from start_loop for dashboard reuse
# ---------------------------------------------------------------------------

def init_loop(feature, sketch_path, max_rounds=3, turn_timeout=300,
              repo_root=None, mode="planning", from_loop=None):
    """Create a new loop session on disk.

    When ``repo_root`` is provided (dashboard path), it is used directly.
    When ``repo_root`` is None (CLI path), ``find_gator_root()`` discovers
    the repo from cwd — no behavioral change for CLI callers.

    ``mode="coding"`` (#41) creates a guarded successor of the approved
    planning loop ``from_loop`` instead of copying a sketch; see
    ``_init_coding_loop()``. Callers own ``start.lock`` (start_loop /
    Dashboard start), exactly as for planning loops.

    Returns ``(loop_id, loop_dir)`` without entering the watch loop.
    """
    if mode == "coding":
        if sketch_path is not None:
            raise ValueError(
                "A coding loop starts from --from-loop; --sketch is not used")
        if repo_root is None:
            repo_root = find_gator_root()
        return _init_coding_loop(feature, from_loop, max_rounds,
                                 turn_timeout, Path(repo_root))
    if mode != "planning":
        raise ValueError(f"Unknown loop mode: {mode!r}")
    if from_loop is not None:
        raise ValueError("--from-loop is only valid with --mode coding")
    if sketch_path is None:
        raise ValueError("A planning loop requires --sketch")

    sketch = Path(sketch_path)
    if not sketch.exists():
        raise FileNotFoundError(f"Sketch file not found: {sketch_path}")
    if sketch.stat().st_size == 0:
        raise ValueError(f"Sketch file is empty: {sketch_path}")

    if repo_root is None:
        repo_root = find_gator_root()
    else:
        repo_root = Path(repo_root)

    loop_id = make_loop_id(feature)
    loops_base = repo_root / ".gator" / "loops"
    loops_base.mkdir(parents=True, exist_ok=True)
    ensure_loops_gitignore(loops_base)

    loop_dir = loops_base / loop_id
    loop_dir.mkdir()

    sketch_dest = loop_dir / "sketch.md"
    shutil.copy2(str(sketch), str(sketch_dest))
    _make_readonly(sketch_dest)

    tok_d, nonce_d = make_token(loop_id, "draftor")
    tok_r, nonce_r = make_token(loop_id, "reviewer")
    tok_a, nonce_a = make_token(loop_id, "architect")
    save_tokens(loop_dir, {
        "draftor": {"nonce": nonce_d, "token": tok_d},
        "reviewer": {"nonce": nonce_r, "token": tok_r},
        "architect": {"nonce": nonce_a, "token": tok_a},
    })

    session = create_session(feature, loop_id, max_rounds, turn_timeout)
    save_session(loop_dir, session)

    create_events_file(loop_dir)
    emit_event(loop_dir, {
        "event": "loop_started",
        "detail": "Loop initialized",
    })

    return loop_id, loop_dir


def find_active_loop(loops_base):
    """Scan loops_base for any non-terminal session. Returns loop_id or None."""
    loops_base = Path(loops_base)
    if not loops_base.is_dir():
        return None
    for entry in sorted(loops_base.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        session_file = entry / "session.json"
        if not session_file.is_file():
            continue
        try:
            session = _json.loads(session_file.read_text(encoding="utf-8"))
            if not is_terminal(session):
                return entry.name
        except (OSError, _json.JSONDecodeError, KeyError, ValueError):
            continue
    return None


# ---------------------------------------------------------------------------
# Coding loop start — guarded successor of an approved planning loop (#41)
# ---------------------------------------------------------------------------

# Canonical loop-id shape: starts AND ends with an alphanumeric (generated
# ids end in "Z"), so Windows path aliases such as a trailing "." are
# rejected before any filesystem lookup.
_SOURCE_LOOP_ID_RE = __import__("re").compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
APPROVED_PLAN_FILENAME = "approved-plan.md"


def _read_approved_source(source_dir, from_loop):
    """Validate the source planning loop and return its approved plan bytes.

    Reads under the source's session lock (read-only callback: nothing is
    written), so the identity, stage, and plan checks observe one
    consistent state. The requested id must equal the source session's own
    ``loop_id`` exactly — a filesystem alias (Windows trailing dot or case
    variant) that resolves to the same directory is rejected, so only the
    canonical id is ever persisted. Raises ValueError on any failure.
    """
    from session import with_session_lock, loop_mode

    captured = {}

    def _check(session):
        if session.get("loop_id") != from_loop:
            raise ValueError(
                f"Source loop id {from_loop!r} is not canonical "
                "(it does not match the source session's loop_id)")
        try:
            mode = loop_mode(session)
        except ValueError as exc:
            raise ValueError(f"Source loop has an unknown mode: {exc}")
        if mode != "planning":
            raise ValueError(
                "Source loop must be a planning loop (got a coding loop)")
        stage = session.get("status", {}).get("stage")
        if stage != "plan_approved":
            raise ValueError(
                f"Source loop's plan is not approved (stage: {stage})")
        plan = source_dir / "plan.current.md"
        if plan.is_symlink() or not plan.is_file():
            raise ValueError("Source loop has no plan.current.md")
        data = plan.read_bytes()
        if not data.strip():
            raise ValueError("Source loop's plan.current.md is empty")
        captured["plan"] = data
        return None  # read-only: never write the source session

    with_session_lock(source_dir, _check)
    return captured["plan"]


def _init_coding_loop(feature, from_loop, max_rounds, turn_timeout,
                      repo_root):
    """Create a coding loop as a guarded successor (#41, approved plan).

    Order (fail atomically — any failure removes the partial directory and
    raises one clear error before a session is published):
      1. canonical source loop id shape (no separators/traversal; starts
         and ends alphanumeric, so no Windows trailing-dot alias);
      2. under the source session lock: the requested id equals the
         session's own ``loop_id`` (rejects case/trailing-dot aliases),
         the source is planning-mode, ``plan_approved``, with a non-empty
         ``plan.current.md``;
      3. the Git base is snapshotted (must be ok: not unborn/conflicted);
      4. new loop dir; ``approved-plan.md`` written, then re-read and its
         SHA-256 compared with the source bytes' digest;
      5. only then tokens, ``session.json``, and events.
    """
    import hashlib
    import gitsnap
    from session import MODE_CODING

    if (not isinstance(from_loop, str) or not from_loop
            or not _SOURCE_LOOP_ID_RE.match(from_loop) or ".." in from_loop):
        raise ValueError(f"Invalid source loop id: {from_loop!r}")

    loops_base = repo_root / ".gator" / "loops"
    source_dir = loops_base / from_loop
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise ValueError(f"Source loop not found: {from_loop}")
    if not (source_dir / "session.json").is_file():
        raise ValueError(f"Source loop has no session: {from_loop}")

    plan_bytes = _read_approved_source(source_dir, from_loop)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()

    snap = gitsnap.snapshot(repo_root)
    if not snap.get("ok"):
        raise ValueError(
            "Cannot capture the Git base for a coding loop: "
            f"{snap.get('error')} ({snap.get('detail', '')})")

    loops_base.mkdir(parents=True, exist_ok=True)
    ensure_loops_gitignore(loops_base)
    loop_id = make_loop_id(feature)
    loop_dir = loops_base / loop_id
    loop_dir.mkdir()
    try:
        dest = loop_dir / APPROVED_PLAN_FILENAME
        with open(dest, "wb") as f:
            f.write(plan_bytes)
        copied = hashlib.sha256(dest.read_bytes()).hexdigest()
        if copied != plan_sha:
            raise ValueError("Approved plan copy failed its digest check")
        _make_readonly(dest)

        coding = {
            "source_loop_id": from_loop,
            "plan_sha256": plan_sha,
            "base_head": snap["current_head"],
            "base_tree": snap["head_tree"],
            "generations": [],
            "approval": None,
        }

        tok_d, nonce_d = make_token(loop_id, "draftor")
        tok_r, nonce_r = make_token(loop_id, "reviewer")
        tok_a, nonce_a = make_token(loop_id, "architect")
        save_tokens(loop_dir, {
            "draftor": {"nonce": nonce_d, "token": tok_d},
            "reviewer": {"nonce": nonce_r, "token": tok_r},
            "architect": {"nonce": nonce_a, "token": tok_a},
        })

        session = create_session(feature, loop_id, max_rounds, turn_timeout,
                                 mode=MODE_CODING, coding=coding)
        save_session(loop_dir, session)

        create_events_file(loop_dir)
        emit_event(loop_dir, {
            "event": "loop_started",
            "mode": "coding",
            "source_loop_id": from_loop,
            "detail": (f"Coding loop initialized from {from_loop} "
                       f"(plan sha256 {plan_sha[:12]}, base "
                       f"{snap['current_head'][:12]})"),
        })
    except BaseException:
        _remove_partial_loop(loop_dir)
        raise
    return loop_id, loop_dir


def _remove_partial_loop(loop_dir):
    """Best-effort removal of a half-created loop dir (read-only files ok)."""
    def _retry_writable(func, path, _exc):
        try:
            os.chmod(path, 0o666)
            func(path)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(str(loop_dir), onexc=_retry_writable)
    else:  # Python 3.9-3.11 (CI floor is 3.9)
        shutil.rmtree(str(loop_dir), onerror=_retry_writable)


# ---------------------------------------------------------------------------
# Reopen — return an approved coding loop to review (#41)
# ---------------------------------------------------------------------------

def reopen_loop(token, message, loop_dir=None):
    """Reopen an approved coding loop with the single-active guarantee.

    A reopen revives a terminal loop, so it is guarded exactly like
    ``extend_loop()``: hold ``start.lock``, refuse if any OTHER loop is
    active, run the locked session transition (``submit.handle_reopen``),
    release ``start.lock``. Watcher attachment is the caller's next step
    (CLI foreground watch or Dashboard daemon watcher). Every rejection
    leaves the session and events unchanged. Returns (loop_id, loop_dir).
    """
    from session import resolve_token
    from submit import handle_reopen

    loop_id, _role, loop_dir = resolve_token(token, loop_dir=loop_dir)
    loops_base = Path(loop_dir).parent

    start_fd = acquire_start_lock(loops_base)
    if start_fd is None:
        raise RuntimeError("Another loop start, extension, or reopen is in progress")
    try:
        existing = find_active_loop(loops_base)
        if existing and existing != loop_id:
            raise RuntimeError(f"An active loop already exists: {existing}")
        return handle_reopen(token, message, loop_dir=loop_dir)
    finally:
        release_start_lock(start_fd)


# ---------------------------------------------------------------------------
# Extension — continue a loop after its round limit (#39)
# ---------------------------------------------------------------------------

def extend_loop(token, rounds, message, loop_dir=None):
    """Continue a max_rounds_exceeded loop with the single-active guarantee.

    An extension revives a terminal loop, so it is guarded exactly like a
    start: hold ``start.lock`` on the loops base, refuse if any OTHER loop
    is active, then run the session transaction (``submit.handle_extend``),
    and release ``start.lock``. Watcher attachment is the caller's next
    step (CLI foreground watch or Dashboard daemon watcher).

    Raises RuntimeError (start/extension in progress, or another active
    loop), plus the handler's ValueError / PermissionError. Every
    rejection leaves the target loop's session and events unchanged.
    Returns (loop_id, loop_dir, previous_max_rounds, new_max_rounds).
    """
    from session import resolve_token
    from submit import handle_extend

    loop_id, _role, loop_dir = resolve_token(token, loop_dir=loop_dir)
    loops_base = Path(loop_dir).parent

    start_fd = acquire_start_lock(loops_base)
    if start_fd is None:
        raise RuntimeError("Another loop start or extension is in progress")
    try:
        existing = find_active_loop(loops_base)
        if existing and existing != loop_id:
            raise RuntimeError(f"An active loop already exists: {existing}")
        return handle_extend(token, rounds, message, loop_dir=loop_dir)
    finally:
        release_start_lock(start_fd)


# ---------------------------------------------------------------------------
# Initialization — gator loop start (CLI entry point)
# ---------------------------------------------------------------------------

def start_loop(feature, sketch_path, max_rounds=3, turn_timeout=300,
               mode="planning", from_loop=None):
    """Initialize a new loop session and enter the watch loop.

    Acquires ``start.lock`` to enforce one-active-loop-per-repo, then
    ``host.lock`` for exclusive host ownership. Delegates initialization
    to ``init_loop()`` and watch to ``watch_loop()``.

    Returns the loop_id (after the watch loop exits).
    """
    repo_root = find_gator_root()
    loops_base = repo_root / ".gator" / "loops"
    loops_base.mkdir(parents=True, exist_ok=True)

    start_fd = acquire_start_lock(loops_base)
    if start_fd is None:
        raise RuntimeError("Another loop start is in progress")

    try:
        existing = find_active_loop(loops_base)
        if existing:
            raise RuntimeError(
                f"An active loop already exists: {existing}")

        loop_id, loop_dir = init_loop(
            feature, sketch_path, max_rounds, turn_timeout,
            repo_root=repo_root, mode=mode, from_loop=from_loop)

        host_fd = acquire_host_lock(loop_dir)
        if host_fd is None:
            raise RuntimeError("Failed to acquire host lock")
    finally:
        release_start_lock(start_fd)

    from session import load_tokens
    tokens = load_tokens(loop_dir)

    _print_banner(
        loop_id, feature, max_rounds, turn_timeout,
        tokens["draftor"]["token"],
        tokens["reviewer"]["token"],
        tokens["architect"]["token"],
    )

    try:
        watch_loop(loop_dir, host_lock_fd=host_fd)
    finally:
        release_host_lock(host_fd)

    return loop_id


# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------

def _print_banner(loop_id, feature, max_rounds, turn_timeout, tok_d, tok_r, tok_a):
    """Print the startup display with tokens and join instructions."""
    timeout_str = _format_timeout(turn_timeout)
    print(f"""
  gator loop

  Loop: {loop_id}
  Feature: {feature}
  Max rounds: {max_rounds}
  Turn timeout: {timeout_str}

  -- Tokens (model) ----------------------------------------

  DRAFTOR:
    gator loop status --token {tok_d}

  REVIEWER:
    gator loop status --token {tok_r}

  -- Token (architect) -------------------------------------

  ARCHITECT:
    gator loop status --token {tok_a}
    gator loop pause --token {tok_a} --message "..."
    gator loop interject --token {tok_a} --message "..."
    gator loop end --token {tok_a} --reason "..."
    gator loop unblock --token {tok_a} --message "..."
    gator loop extend --token {tok_a} --rounds <N> --message "..."   (after max rounds)

  -- Watching -----------------------------------------------
""")
    sys.stdout.flush()


def _format_timeout(seconds):
    """Format timeout seconds as a human-readable string."""
    if seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


# ---------------------------------------------------------------------------
# Watch loop
# ---------------------------------------------------------------------------

def watch_loop(loop_dir, host_lock_fd=None):
    """Tail events.jsonl, render log lines, enforce turn timeouts.

    Runs until a terminal state is reached. During paused states
    (blocked_on_architect), the host stays alive but suspends timeout
    enforcement — it continues rendering events (e.g., loop_unblocked).

    ``host_lock_fd`` is the already-held host.lock file descriptor.
    This function writes diagnostic metadata to it but never closes
    or releases it — the caller owns the fd.
    """
    loop_dir = Path(loop_dir)

    if host_lock_fd is not None:
        import secrets
        write_host_metadata(host_lock_fd, secrets.token_hex(4))
    events_path = loop_dir / "events.jsonl"

    # Participant liveness (#36): best-effort, never raises, never touches
    # session/event state. Projection runs AFTER each durable event batch,
    # outside the session lock (liveness lock is a leaf).
    liveness_store = _open_liveness_store(loop_dir)
    liveness_retry = False  # a torn read / failed write retries next tick

    # Start from current end of file (initial event already printed
    # conceptually by the banner — but we read it to show the log line)
    last_pos = 0

    while True:
        # --- Phase 1: check for new events ---
        try:
            current_size = events_path.stat().st_size
        except OSError:
            time.sleep(POLL_INTERVAL)
            continue

        if current_size > last_pos:
            with open(events_path, "r", encoding="utf-8") as f:
                f.seek(last_pos)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = _parse_event(line)
                    except ValueError:
                        continue

                    print(format_event(event))
                    sys.stdout.flush()

                    # A terminal event ends the watch only if the session is
                    # still terminal. max_rounds_exceeded is resumable (#39):
                    # a watcher attached after an extension replays the old
                    # terminal event from offset 0 and must keep hosting.
                    if (event.get("event") in TERMINAL_EVENTS
                            and _session_is_terminal(loop_dir)):
                        _project_liveness(loop_dir, liveness_store)
                        _print_terminal_summary(loop_dir)
                        return

                last_pos = f.tell()

            liveness_retry = _project_liveness(
                loop_dir, liveness_store) in ("retry", "error")

            # After rendering events, show the next-step prompt
            try:
                session = load_session(loop_dir)
                if not is_terminal(session):
                    print(format_next_prompt(session))
                    print("  waiting...")
                    sys.stdout.flush()
            except (FileNotFoundError, KeyError):
                pass

        elif liveness_retry:
            liveness_retry = _project_liveness(
                loop_dir, liveness_store) in ("retry", "error")

        # --- Phase 2: timeout enforcement (active states only) ---
        try:
            session = load_session(loop_dir)
        except (FileNotFoundError, KeyError):
            time.sleep(POLL_INTERVAL)
            continue

        try:
            active = is_active(session)
        except ValueError:  # unknown loop mode: never enforce blind
            active = False
        if active:
            deadline_str = session["status"].get("turn_deadline")
            if deadline_str:
                try:
                    deadline = datetime.fromisoformat(deadline_str)
                    if datetime.now(tz=timezone.utc) > deadline:
                        _try_enforce_timeout(loop_dir)
                except (ValueError, TypeError):
                    pass

        time.sleep(POLL_INTERVAL)


def _open_liveness_store(loop_dir):
    """Liveness store for this loop, or None (unavailable / import error)."""
    try:
        import liveness
        return liveness.open_host_store(loop_dir)
    except Exception:
        return None


def _project_liveness(loop_dir, store):
    """Guarded liveness projection; a failure never affects hosting."""
    if store is None:
        return None
    try:
        import liveness
        return liveness.project_for_host(loop_dir, store)
    except Exception:
        return None


def _session_is_terminal(loop_dir):
    """True if session.json is currently terminal.

    Fails safe toward the historical behavior: an unreadable session is
    treated as terminal so the watcher exits rather than hosting blind.
    """
    try:
        return is_terminal(load_session(loop_dir))
    except (FileNotFoundError, KeyError, ValueError, OSError):
        return True


# ---------------------------------------------------------------------------
# Timeout enforcement — the one host write path
# ---------------------------------------------------------------------------

def _try_enforce_timeout(loop_dir):
    """Acquire the session lock and enforce timeout if still expired.

    Re-reads session inside the lock. If a submit landed in the meantime
    (state advanced or deadline reset), the timeout is silently skipped.
    """
    def _enforce(session):
        # Re-check inside lock — state may have changed
        if is_terminal(session) or is_paused(session):
            return None

        deadline_str = session["status"].get("turn_deadline")
        if not deadline_str:
            return None

        try:
            deadline = datetime.fromisoformat(deadline_str)
        except (ValueError, TypeError):
            return None

        if datetime.now(tz=timezone.utc) <= deadline:
            return None  # deadline was reset by a submit

        timed_out_role = session["status"]["next_role"]
        advance_turn_timed_out(session, timed_out_role)

        timeout_secs = session["status"].get("turn_timeout_seconds", 300)
        event = {
            "event": "turn_timed_out",
            "role": timed_out_role,
            "round": session["status"].get("round", 0),
            "detail": (
                f"{timed_out_role} did not submit within "
                f"{_format_timeout(timeout_secs)}"
            ),
        }
        return session, event

    with_session_lock(loop_dir, _enforce)


# ---------------------------------------------------------------------------
# Terminal summary
# ---------------------------------------------------------------------------

def _print_terminal_summary(loop_dir):
    """Print a summary when the loop reaches a terminal state."""
    try:
        session = load_session(loop_dir)
    except (FileNotFoundError, KeyError):
        print("\n  Loop ended.")
        return

    stage = session["status"]["stage"]
    feature = session.get("feature", "unknown")
    rounds = session["status"].get("round", 0)
    max_rounds = session["status"].get("max_rounds", 0)
    total_turns = len(session.get("turns", []))

    print(f"""
  -- Summary ------------------------------------------------

  Feature: {feature}
  Result: {stage}
  Rounds: {rounds}/{max_rounds}
  Turns: {total_turns}
  Residue: {loop_dir}

  Session files remain for inspection. No Git commit was made.
  -----------------------------------------------------------
""")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_event(line):
    """Parse a JSON event line. Raises ValueError on bad input."""
    import json
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Bad event line: {exc}") from exc
