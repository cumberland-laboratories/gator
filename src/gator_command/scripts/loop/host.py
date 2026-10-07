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
from datetime import datetime, timedelta, timezone
from pathlib import Path

_LOOP_DIR = str(Path(__file__).resolve().parent)
if _LOOP_DIR not in sys.path:
    sys.path.insert(0, _LOOP_DIR)

from session import (
    create_session, save_session, load_session, with_session_lock,
    make_token, save_tokens, make_loop_id,
    find_gator_root, ensure_loops_gitignore,
    _make_readonly, _make_writable, attention_mode,
    BRIEF_FILENAME, SOURCE_BRIEF_FILENAME, brief_meta, read_brief_file,
    brief_bytes_from_text, read_verified_brief, verify_brief,
    append_turn, read_governed_input, verify_fixed_artifact,
    ARCHITECT_PLAN_FILENAME, MAX_PLAN_BYTES, MAX_BASELINE_BYTES,
    REVISION_BASELINE_PLAN, REVISION_BASELINE_APPROVAL, _is_reparse_point,
)
from events import (
    emit_event, create_events_file, format_event, format_next_prompt,
    TERMINAL_EVENTS, read_all_events, EVENTS_FILENAME,
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
              repo_root=None, mode="planning", from_loop=None,
              brief_path=None, brief_text=None, source_brief=None,
              plan_path=None, revise_from=None):
    """Create a new loop session on disk.

    When ``repo_root`` is provided (dashboard path), it is used directly.
    When ``repo_root`` is None (CLI path), ``find_gator_root()`` discovers
    the repo from cwd — no behavioral change for CLI callers.

    ``mode="coding"`` (#41) creates a guarded successor of the approved
    planning loop ``from_loop`` instead of copying a sketch; see
    ``_init_coding_loop()``. Callers own ``start.lock`` (start_loop /
    Dashboard start), exactly as for planning loops.

    Architect brief (#43): at most one of ``brief_path`` (CLI file) or
    ``brief_text`` (Dashboard textarea; blank = none) is validated BEFORE
    any directory is created and stored immutably as architect-brief.md.
    ``source_brief`` ("keep" default / "drop") applies to coding starts only.

    ``plan_path`` (#51) starts a planning loop from an Architect-originated
    draft plan at Reviewer ``plan_review``; see ``_init_architect_plan_loop``.
    The sketch is optional then. ``revise_from`` (#51) starts an ordinary
    planning loop that revises an approved planning loop, from verified
    baseline copies; see ``_init_revision_loop``. The two are mutually
    exclusive and planning-only; ``revise_from`` requires a sketch.

    Returns ``(loop_id, loop_dir)`` without entering the watch loop.
    """
    if plan_path is not None and revise_from is not None:
        raise ValueError("Use --plan-file or --revise-from, not both")
    if plan_path is not None and mode != "planning":
        raise ValueError("--plan-file starts a planning loop; it is not valid "
                         "with --mode coding")
    if revise_from is not None and mode != "planning":
        raise ValueError("--revise-from starts a planning loop; it is not "
                         "valid with --mode coding")
    if revise_from is not None and sketch_path is None:
        raise ValueError("--revise-from requires --sketch (the revision sketch)")
    brief_bytes = _resolve_brief_input(brief_path, brief_text)
    if mode == "coding":
        if sketch_path is not None:
            raise ValueError(
                "A coding loop starts from --from-loop; --sketch is not used")
        if source_brief not in (None, "keep", "drop"):
            raise ValueError("source brief choice must be 'keep' or 'drop'")
        if repo_root is None:
            repo_root = find_gator_root()
        return _init_coding_loop(feature, from_loop, max_rounds,
                                 turn_timeout, Path(repo_root),
                                 brief_bytes=brief_bytes,
                                 source_brief=source_brief or "keep")
    if mode != "planning":
        raise ValueError(f"Unknown loop mode: {mode!r}")
    if from_loop is not None:
        raise ValueError("--from-loop is only valid with --mode coding")
    if source_brief is not None:
        raise ValueError(
            "--source-brief is only valid when starting a coding loop")
    if plan_path is not None:
        if repo_root is None:
            repo_root = find_gator_root()
        return _init_architect_plan_loop(
            feature, plan_path, sketch_path, max_rounds, turn_timeout,
            Path(repo_root), brief_bytes=brief_bytes)
    if revise_from is not None:
        if repo_root is None:
            repo_root = find_gator_root()
        return _init_revision_loop(
            feature, sketch_path, revise_from, max_rounds, turn_timeout,
            Path(repo_root), brief_bytes=brief_bytes)
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
    try:
        sketch_dest = loop_dir / "sketch.md"
        shutil.copy2(str(sketch), str(sketch_dest))
        _make_readonly(sketch_dest)

        brief = None
        if brief_bytes is not None:
            brief = _write_brief(loop_dir, BRIEF_FILENAME, brief_bytes)

        tok_d, nonce_d = make_token(loop_id, "draftor")
        tok_r, nonce_r = make_token(loop_id, "reviewer")
        tok_a, nonce_a = make_token(loop_id, "architect")
        save_tokens(loop_dir, {
            "draftor": {"nonce": nonce_d, "token": tok_d},
            "reviewer": {"nonce": nonce_r, "token": tok_r},
            "architect": {"nonce": nonce_a, "token": tok_a},
        })

        session = create_session(feature, loop_id, max_rounds, turn_timeout,
                                 brief=brief)
        save_session(loop_dir, session)

        create_events_file(loop_dir)
        start_event = {
            "event": "loop_started",
            "detail": "Loop initialized",
        }
        if brief is not None:
            start_event["brief_sha256"] = brief["sha256"]
            start_event["brief_bytes"] = brief["bytes"]
        emit_event(loop_dir, start_event)
    except BaseException:
        # #43: a failed start never leaves a partial loop directory.
        _remove_partial_loop(loop_dir)
        raise

    return loop_id, loop_dir


def _resolve_brief_input(brief_path, brief_text):
    """Validated brief bytes, or None. At most one source may be given."""
    if brief_path is not None and brief_text is not None:
        raise ValueError("Give the Architect brief as a file or as text, not both")
    if brief_path is not None:
        return read_brief_file(brief_path)
    if brief_text is not None:
        return brief_bytes_from_text(brief_text)
    return None


def _write_brief(loop_dir, name, data):
    """Write brief bytes immutably and verify the copy. Returns metadata."""
    meta = brief_meta(data, name)
    dest = Path(loop_dir) / name
    with open(dest, "wb") as f:
        f.write(data)
    _make_readonly(dest)
    if verify_brief(loop_dir, meta, name) != "ok":
        raise ValueError(f"Architect brief copy failed its digest check ({name})")
    return meta


def _write_fixed_artifact(loop_dir, name, data):
    """Write immutable fixed-artifact bytes and verify the copy (#51).
    Returns the {artifact, sha256, bytes} metadata."""
    meta = brief_meta(data, name)
    dest = Path(loop_dir) / name
    with open(dest, "wb") as f:
        f.write(data)
    _make_readonly(dest)
    if verify_fixed_artifact(loop_dir, meta, name) != "ok":
        raise ValueError(f"{name} copy failed its digest check")
    return meta


def _write_checked_bytes(loop_dir, name, data, sha):
    """Write bytes, re-read them and compare the SHA-256 with ``sha``."""
    import hashlib
    from submit import _write_artifact_bytes
    _write_artifact_bytes(loop_dir, name, data)
    if hashlib.sha256((Path(loop_dir) / name).read_bytes()).hexdigest() != sha:
        raise ValueError(f"{name} copy failed its digest check")


ARCHITECT_PLAN_TURN_SUMMARY = (
    "Architect-originated draft plan submitted for Reviewer approval")
ARCHITECT_PLAN_EVENT_DETAIL = (
    "Architect-originated draft plan -- awaiting Reviewer approval")


def _init_architect_plan_loop(feature, plan_path, sketch_path, max_rounds,
                              turn_timeout, repo_root, brief_bytes=None):
    """#51: a planning loop whose first plan is Architect-originated.

    Order (atomic -- any failure after the directory exists removes it):
      1. the plan is read ONCE through ``read_governed_input`` (repository
         containment, no links/aliases, regular, stable, UTF-8, bounded);
      2. the captured bytes pass the SAME check as a Draftor draft
         (``_check_plan_draft`` with both new-session contract flags);
      3. the optional sketch is checked the ordinary way;
      4. only then the loop directory; ``architect-plan.md`` (immutable,
         verified), ``plan.round-0.md`` and ``plan.current.md`` (the exact
         validated bytes, digest-checked); the optional sketch and brief;
      5. tokens, the session (plan_source block, one Architect
         ``initial_plan`` turn, ``plan_review`` entry), then the events
         ``loop_started`` and ``architect_plan_submitted``.
    The plan is never approved by being written: the Reviewer owns the
    first turn, and no Draftor turn is fabricated.
    """
    import hashlib
    from submit import _check_plan_draft
    from state_machine import enter_architect_plan_review

    plan_bytes = read_governed_input(plan_path, repo_root, MAX_PLAN_BYTES,
                                     "Architect plan")
    _check_plan_draft(plan_bytes, True, True)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()

    sketch = None
    if sketch_path is not None:
        sketch = Path(sketch_path)
        if not sketch.exists():
            raise FileNotFoundError(f"Sketch file not found: {sketch_path}")
        if sketch.stat().st_size == 0:
            raise ValueError(f"Sketch file is empty: {sketch_path}")

    loop_id = make_loop_id(feature)
    loops_base = repo_root / ".gator" / "loops"
    loops_base.mkdir(parents=True, exist_ok=True)
    ensure_loops_gitignore(loops_base)
    loop_dir = loops_base / loop_id
    loop_dir.mkdir()
    try:
        plan_meta = _write_fixed_artifact(loop_dir, ARCHITECT_PLAN_FILENAME,
                                          plan_bytes)
        _write_checked_bytes(loop_dir, "plan.round-0.md", plan_bytes, plan_sha)
        _write_checked_bytes(loop_dir, "plan.current.md", plan_bytes, plan_sha)
        if sketch is not None:
            sketch_dest = loop_dir / "sketch.md"
            shutil.copy2(str(sketch), str(sketch_dest))
            _make_readonly(sketch_dest)
        brief = None
        if brief_bytes is not None:
            brief = _write_brief(loop_dir, BRIEF_FILENAME, brief_bytes)

        tok_d, nonce_d = make_token(loop_id, "draftor")
        tok_r, nonce_r = make_token(loop_id, "reviewer")
        tok_a, nonce_a = make_token(loop_id, "architect")
        save_tokens(loop_dir, {
            "draftor": {"nonce": nonce_d, "token": tok_d},
            "reviewer": {"nonce": nonce_r, "token": tok_r},
            "architect": {"nonce": nonce_a, "token": tok_a},
        })

        plan_source = dict(plan_meta, kind="architect")
        session = create_session(feature, loop_id, max_rounds, turn_timeout,
                                 brief=brief, plan_source=plan_source)
        turn = append_turn(session, "architect", "initial_plan",
                           ARCHITECT_PLAN_TURN_SUMMARY, "plan.round-0.md")
        session["current"]["draft"] = {
            "turn_id": turn["turn_id"],
            "summary": turn["summary"],
            "artifact_path": "plan.current.md",
        }
        enter_architect_plan_review(session, turn_timeout)
        save_session(loop_dir, session)

        create_events_file(loop_dir)
        start_event = {
            "event": "loop_started",
            "detail": "Loop initialized from an Architect-originated draft plan",
            "plan_source_kind": "architect",
            "plan_sha256": plan_sha,
            "plan_bytes": len(plan_bytes),
        }
        if brief is not None:
            start_event["brief_sha256"] = brief["sha256"]
            start_event["brief_bytes"] = brief["bytes"]
        emit_event(loop_dir, start_event)
        emit_event(loop_dir, {
            "event": "architect_plan_submitted",
            "role": "architect",
            "round": 0,
            "artifact_path": "plan.round-0.md",
            "detail": ARCHITECT_PLAN_EVENT_DETAIL,
        })
    except BaseException:
        _remove_partial_loop(loop_dir)
        raise
    return loop_id, loop_dir


_PLAN_ROUND_RE = __import__("re").compile(r"^plan\.round-\d+\.md$")
_FINDINGS_ROUND_RE = __import__("re").compile(r"^findings\.round-\d+\.md$")
APPROVING_REVIEW_SUMMARY = "Plan approved"


def _require_source_dir(source_dir, loop_id):
    """Containment guard for a source loop directory (#51 follow-up).

    A Windows directory junction is a reparse point but not a symlink, so
    ``is_symlink()`` alone would let one under ``.gator/loops/`` redirect
    source reads outside the governed loops directory. Reject either form
    before ``session.json`` or any source artifact is opened; the error
    names only the requested id, never the redirected target.
    """
    if source_dir.is_symlink() or _is_reparse_point(source_dir):
        raise ValueError(
            f"Source loop must not be a symlink or reparse point: {loop_id}")
    if not source_dir.is_dir():
        raise ValueError(f"Source loop not found: {loop_id}")


def _read_source_file(source_dir, name, what):
    """Bytes of one source-loop artifact: a regular, non-link, non-empty
    file of at most MAX_BASELINE_BYTES. ValueError names the problem."""
    path = Path(source_dir) / name
    if path.is_symlink() or _is_reparse_point(path):
        raise ValueError(f"Source loop's {what} ({name}) is a link")
    if not path.is_file():
        raise ValueError(f"Source loop's {what} ({name}) is missing")
    with open(path, "rb") as f:
        data = f.read(MAX_BASELINE_BYTES + 1)
    if not data.strip():
        raise ValueError(f"Source loop's {what} ({name}) is empty")
    if len(data) > MAX_BASELINE_BYTES:
        raise ValueError(
            f"Source loop's {what} ({name}) is larger than "
            f"{MAX_BASELINE_BYTES} bytes; it cannot be a revision baseline")
    return data


def _read_revision_source(source_dir, revise_from):
    """#51: the approved plan and its approving review, read under the
    source's session lock (read-only callback: the source is never written).

    Identification (no guessing; any mismatch fails with a named reason):
      - canonical id (session.loop_id == requested id), planning mode,
        stage plan_approved;
      - approval: the LAST turn is the Reviewer's ``plan_review`` turn with
        summary "Plan approved" and a ``findings.round-N.md`` artifact that
        is byte-equal to ``findings.current.md``;
      - plan: ``plan.current.md`` is byte-equal to the artifact of the latest
        plan-producing turn (a Draftor ``plan_draft`` or the Architect
        ``initial_plan``).
    Returns ``(plan_bytes, approval_bytes, approval_source_name)``.
    """
    from session import with_session_lock, loop_mode

    captured = {}

    def _check(session):
        if session.get("loop_id") != revise_from:
            raise ValueError(
                f"Source loop id {revise_from!r} is not canonical "
                "(it does not match the source session's loop_id)")
        try:
            mode = loop_mode(session)
        except ValueError as exc:
            raise ValueError(f"Source loop has an unknown mode: {exc}")
        if mode != "planning":
            raise ValueError(
                "Only an approved planning loop can be revised (got a coding loop)")
        stage = session.get("status", {}).get("stage")
        if stage != "plan_approved":
            raise ValueError(
                f"Source loop's plan is not approved (stage: {stage})")
        turns = session.get("turns") or []
        last = turns[-1] if turns else {}
        approval_name = last.get("artifact_path")
        if not (last.get("role") == "reviewer"
                and last.get("type") == "plan_review"
                and last.get("summary") == APPROVING_REVIEW_SUMMARY
                and isinstance(approval_name, str)
                and _FINDINGS_ROUND_RE.match(approval_name)):
            raise ValueError(
                "Source loop's approving review cannot be identified (the last "
                "turn is not the Reviewer's approval)")
        approval = _read_source_file(source_dir, approval_name, "approving review")
        current = _read_source_file(source_dir, "findings.current.md",
                                    "current review")
        if approval != current:
            raise ValueError(
                f"Source loop's approving review is inconsistent "
                f"({approval_name} differs from findings.current.md)")
        plan_turns = [t for t in turns
                      if (t.get("role") == "draftor" and t.get("type") == "plan_draft")
                      or (t.get("role") == "architect"
                          and t.get("type") == "initial_plan")]
        plan_name = plan_turns[-1].get("artifact_path") if plan_turns else None
        if not (isinstance(plan_name, str) and _PLAN_ROUND_RE.match(plan_name)):
            raise ValueError("Source loop's approved plan cannot be identified "
                             "(no plan submission turn)")
        plan = _read_source_file(source_dir, "plan.current.md", "approved plan")
        latest = _read_source_file(source_dir, plan_name, "latest plan round")
        if plan != latest:
            raise ValueError(
                f"Source loop's approved plan is inconsistent "
                f"(plan.current.md differs from {plan_name})")
        captured.update(plan=plan, approval=approval, approval_name=approval_name)
        return None  # read-only: never write the source session

    with_session_lock(source_dir, _check)
    return captured["plan"], captured["approval"], captured["approval_name"]


def _init_revision_loop(feature, sketch_path, revise_from, max_rounds,
                        turn_timeout, repo_root, brief_bytes=None):
    """#51: an ordinary Draftor-led planning loop that revises an approved
    planning loop, from immutable verified baseline copies.

    Order (atomic -- any failure after the directory exists removes it):
      1. canonical source id shape; source dir/session present;
      2. the revision sketch through ``read_governed_input``;
      3. ``_read_revision_source`` under the source lock (read-only);
      4. only then the loop dir: ``sketch.md`` (the exact sketch bytes),
         ``revision-baseline-plan.md`` and ``revision-baseline-approval.md``
         (immutable, verified), the optional brief;
      5. tokens, the session (``revision`` block, ordinary plan_drafting),
         ``loop_started`` with the source id and both digests.
    The source loop is only read; the copies, not live paths, are the
    authority if the source later changes or is removed.
    """
    import hashlib

    if (not isinstance(revise_from, str) or not revise_from
            or not _SOURCE_LOOP_ID_RE.match(revise_from) or ".." in revise_from):
        raise ValueError(f"Invalid source loop id: {revise_from!r}")
    loops_base = repo_root / ".gator" / "loops"
    source_dir = loops_base / revise_from
    _require_source_dir(source_dir, revise_from)
    if not (source_dir / "session.json").is_file():
        raise ValueError(f"Source loop has no session: {revise_from}")

    sketch_bytes = read_governed_input(sketch_path, repo_root, MAX_PLAN_BYTES,
                                       "Revision sketch")
    plan_bytes, approval_bytes, approval_name = _read_revision_source(
        source_dir, revise_from)

    loops_base.mkdir(parents=True, exist_ok=True)
    ensure_loops_gitignore(loops_base)
    loop_id = make_loop_id(feature)
    loop_dir = loops_base / loop_id
    loop_dir.mkdir()
    try:
        _write_checked_bytes(loop_dir, "sketch.md", sketch_bytes,
                             hashlib.sha256(sketch_bytes).hexdigest())
        baseline = _write_fixed_artifact(loop_dir, REVISION_BASELINE_PLAN,
                                         plan_bytes)
        approval = _write_fixed_artifact(loop_dir, REVISION_BASELINE_APPROVAL,
                                         approval_bytes)
        brief = None
        if brief_bytes is not None:
            brief = _write_brief(loop_dir, BRIEF_FILENAME, brief_bytes)

        tok_d, nonce_d = make_token(loop_id, "draftor")
        tok_r, nonce_r = make_token(loop_id, "reviewer")
        tok_a, nonce_a = make_token(loop_id, "architect")
        save_tokens(loop_dir, {
            "draftor": {"nonce": nonce_d, "token": tok_d},
            "reviewer": {"nonce": nonce_r, "token": tok_r},
            "architect": {"nonce": nonce_a, "token": tok_a},
        })

        revision = {
            "source_loop_id": revise_from,
            "baseline": baseline,
            "approval": dict(approval, source_artifact=approval_name),
        }
        session = create_session(feature, loop_id, max_rounds, turn_timeout,
                                 brief=brief, revision=revision)
        save_session(loop_dir, session)

        create_events_file(loop_dir)
        start_event = {
            "event": "loop_started",
            "detail": f"Revision planning loop initialized from {revise_from}",
            "revision_source_loop_id": revise_from,
            "baseline_sha256": baseline["sha256"],
            "approval_sha256": approval["sha256"],
            "approval_source_artifact": approval_name,
        }
        if brief is not None:
            start_event["brief_sha256"] = brief["sha256"]
            start_event["brief_bytes"] = brief["bytes"]
        emit_event(loop_dir, start_event)
    except BaseException:
        _remove_partial_loop(loop_dir)
        raise
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


def _read_approved_source(source_dir, from_loop, source_brief="keep"):
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
        # #55: the source session's checkpoint flag decides whether a plan
        # without '## Coding Checkpoints' may get the implicit checkpoint.
        from submit import _coding_checkpoints_required
        captured["checkpoints_required"] = _coding_checkpoints_required(session)

        # #43 D1: carry the planning brief forward only when asked. "drop"
        # never opens or verifies it, so a corrupt source brief cannot block
        # a start that does not use it.
        ref = session.get("brief")
        if ref is None:
            captured["brief_decision"] = "none_available"
            captured["brief"] = None
        elif source_brief == "drop":
            captured["brief_decision"] = "dropped"
            captured["brief"] = None
        else:
            state, brief_data = read_verified_brief(
                source_dir, ref, BRIEF_FILENAME)
            if state != "ok":
                raise ValueError(
                    "The approved plan's Architect brief failed its integrity "
                    f"check ({state}); start with --source-brief drop to "
                    "begin the coding loop without it")
            captured["brief_decision"] = "kept"
            captured["brief"] = brief_data
        return None  # read-only: never write the source session

    with_session_lock(source_dir, _check)
    return (captured["plan"], captured["brief_decision"], captured["brief"],
            captured["checkpoints_required"])


def _plan_checkpoints(plan_bytes, required):
    """#55 D1 coding-start table: ``(source, items)`` from the frozen plan
    bytes, or ValueError. A flagged source must declare valid checkpoints;
    a legacy source without the section gets one implicit checkpoint; a
    present-but-invalid section is refused for either."""
    from submit import parse_coding_checkpoints, ONE_CHECKPOINT_EXAMPLE
    from session import IMPLICIT_CHECKPOINT

    text = plan_bytes.decode("utf-8", errors="replace")
    present, items, problems = parse_coding_checkpoints(text)
    if present and problems:
        raise ValueError(
            "The approved plan's '## Coding Checkpoints' section is invalid: "
            + "; ".join(problems))
    if present:
        return "declared", items
    if required:
        raise ValueError(
            "The approved plan has no '## Coding Checkpoints' section, but "
            "its planning loop requires one; revise the plan in a planning "
            f"loop (a small fix declares one: {ONE_CHECKPOINT_EXAMPLE})")
    return "implicit", [dict(IMPLICIT_CHECKPOINT)]


def _init_coding_loop(feature, from_loop, max_rounds, turn_timeout,
                      repo_root, brief_bytes=None, source_brief="keep"):
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
      2b. (#55) the approved plan's ``## Coding Checkpoints`` decides the
         manifest: declared, implicit (legacy sources only), or refused;
      4. new loop dir; ``approved-plan.md`` written, then re-read and its
         SHA-256 compared with the source bytes' digest;
      5. only then tokens, ``session.json``, and events.
    """
    import hashlib
    import gitsnap
    from session import MODE_CODING, build_checkpoint_manifest

    if (not isinstance(from_loop, str) or not from_loop
            or not _SOURCE_LOOP_ID_RE.match(from_loop) or ".." in from_loop):
        raise ValueError(f"Invalid source loop id: {from_loop!r}")

    loops_base = repo_root / ".gator" / "loops"
    source_dir = loops_base / from_loop
    _require_source_dir(source_dir, from_loop)
    if not (source_dir / "session.json").is_file():
        raise ValueError(f"Source loop has no session: {from_loop}")

    (plan_bytes, source_brief_decision, source_brief_bytes,
     checkpoints_required) = _read_approved_source(
        source_dir, from_loop, source_brief)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    checkpoint_source, checkpoint_items = _plan_checkpoints(
        plan_bytes, checkpoints_required)

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

        source_brief_meta = None
        if source_brief_bytes is not None:
            source_brief_meta = _write_brief(
                loop_dir, SOURCE_BRIEF_FILENAME, source_brief_bytes)
        brief = None
        if brief_bytes is not None:
            brief = _write_brief(loop_dir, BRIEF_FILENAME, brief_bytes)

        coding = {
            "source_loop_id": from_loop,
            "plan_sha256": plan_sha,
            "base_head": snap["current_head"],
            "base_tree": snap["head_tree"],
            "generations": [],
            "approval": None,
            "source_brief": source_brief_meta,
            "source_brief_decision": source_brief_decision,
            # #55 D2: frozen once from the approved-plan bytes; never
            # re-parsed after creation.
            "checkpoints": build_checkpoint_manifest(
                checkpoint_items, checkpoint_source, snap["head_tree"]),
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
                                 mode=MODE_CODING, coding=coding, brief=brief)
        save_session(loop_dir, session)

        create_events_file(loop_dir)
        start_event = {
            "event": "loop_started",
            "mode": "coding",
            "source_loop_id": from_loop,
            "source_brief_decision": source_brief_decision,
            "detail": (f"Coding loop initialized from {from_loop} "
                       f"(plan sha256 {plan_sha[:12]}, base "
                       f"{snap['current_head'][:12]})"),
        }
        if source_brief_meta is not None:
            start_event["source_brief_sha256"] = source_brief_meta["sha256"]
            start_event["source_brief_bytes"] = source_brief_meta["bytes"]
        if brief is not None:
            start_event["brief_sha256"] = brief["sha256"]
            start_event["brief_bytes"] = brief["bytes"]
        emit_event(loop_dir, start_event)
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
               mode="planning", from_loop=None, brief_path=None,
               source_brief=None, plan_path=None, revise_from=None):
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
            repo_root=repo_root, mode=mode, from_loop=from_loop,
            brief_path=brief_path, source_brief=source_brief,
            plan_path=plan_path, revise_from=revise_from)

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
        source_note=(("Architect-originated draft plan -- awaiting Reviewer "
                      "approval (the Reviewer acts first)") if plan_path else
                     (f"Revision of {revise_from} (baseline plan and approving "
                      "review copied)") if revise_from else None))

    try:
        watch_loop(loop_dir, host_lock_fd=host_fd)
    finally:
        release_host_lock(host_fd)

    return loop_id


# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------

def _print_banner(loop_id, feature, max_rounds, turn_timeout, tok_d, tok_r, tok_a,
                  source_note=None):
    """Print the startup display with tokens and join instructions."""
    timeout_str = _format_timeout(turn_timeout)
    source_line = f"\n  Plan source: {source_note}" if source_note else ""
    print(f"""
  gator loop

  Loop: {loop_id}
  Feature: {feature}{source_line}
  Max rounds: {max_rounds}
  Attention interval: {timeout_str} (Architect notice only; participants never see it)

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
        if active and attention_mode(session):
            # #47: soft Architect attention, never a state change. Cheap
            # unlocked pre-check; the locked procedure re-decides.
            status = session["status"]
            if (status.get("attention_notified_turn") != status.get("turn_started_at")
                    and _attention_due(session, datetime.now(tz=timezone.utc))):
                try:
                    _try_record_attention(loop_dir)
                except Exception:
                    pass  # never fatal; the next poll converges (Decision 3)
        elif active:
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
        if attention_mode(session):
            return None  # #47: flagged loops never time out

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
# Architect attention (#47) — soft awareness, never a state change
# ---------------------------------------------------------------------------

ATTENTION_EVENT = "architect_attention_due"


def _attention_due(session, now):
    """True when a flagged, active (not paused) turn has run past its
    interval. Pure; never raises on malformed status values."""
    if not attention_mode(session):
        return False
    try:
        if not is_active(session) or is_paused(session):
            return False
    except ValueError:
        return False
    status = session.get("status", {})
    key = status.get("turn_started_at")
    interval = status.get("turn_timeout_seconds")
    if not isinstance(key, str) or isinstance(interval, bool) \
            or not isinstance(interval, int) or interval <= 0:
        return False
    try:
        started = datetime.fromisoformat(key)
    except ValueError:
        return False
    # A naive timestamp parses but cannot be compared with the aware clock;
    # treat it as malformed rather than raising (#47 M2-1).
    if started.tzinfo is None or started.utcoffset() is None:
        return False
    try:
        return now >= started + timedelta(seconds=interval)
    except (TypeError, OverflowError):
        return False


def _find_attention_event(loop_dir, key):
    """True if a VALID attention event for this turn key is in the log.

    Uses the shared reader, which skips blank and torn/unparsable lines.
    """
    for event in read_all_events(loop_dir):
        if (isinstance(event, dict) and event.get("event") == ATTENTION_EVENT
                and event.get("attention_key") == key):
            return True
    return False


def _ensure_events_newline(events_path):
    """If a previous write left a partial final line, terminate it so the
    next record can never be concatenated onto it."""
    try:
        size = events_path.stat().st_size
    except OSError:
        return
    if size == 0:
        return
    with open(events_path, "rb") as f:
        f.seek(-1, os.SEEK_END)
        last = f.read(1)
    if last != b"\n":
        _make_writable(events_path)
        with open(events_path, "ab") as f:
            f.write(b"\n")
        _make_readonly(events_path)


def _format_attention_detail(role, stage, interval):
    return (f"{role} active for at least {_format_timeout(interval)} in "
            f"{str(stage).replace('_', ' ')}; loop still running")


def _try_record_attention(loop_dir, now=None):
    """Record exactly one durable ``architect_attention_due`` per turn.

    Event-first, marker-second, with a recovery scan (#47 Decision 3).
    The two files are NOT updated atomically; the procedure converges:

    1. preconditions (flagged, active, not paused, interval elapsed);
    2. fast path: ``attention_notified_turn == turn_started_at`` -> no write;
    3. recovery: a valid event with this ``attention_key`` already exists
       -> repair the marker only, append nothing;
    4. otherwise terminate any torn final line, append the event, THEN
       set the marker (saved by with_session_lock after this callback).

    This deliberately inverts the session-before-event rule for this one
    awareness-only event: it implies no loop state, so an event visible
    before its marker loses nothing. Returns True if an event was appended.
    """
    loop_dir = Path(loop_dir)
    appended = {"value": False}

    def _record(session):
        clock = now or datetime.now(tz=timezone.utc)
        if not _attention_due(session, clock):
            return None
        status = session["status"]
        key = status["turn_started_at"]
        if status.get("attention_notified_turn") == key:
            return None
        if not _find_attention_event(loop_dir, key):
            _ensure_events_newline(loop_dir / EVENTS_FILENAME)
            role = status.get("next_role")
            stage = status.get("stage")
            interval = status["turn_timeout_seconds"]
            emit_event(loop_dir, {
                "event": ATTENTION_EVENT,
                "attention_key": key,
                "role": role,
                "round": status.get("round", 0),
                "stage": stage,
                "interval_seconds": interval,
                "turn_started_at": key,
                "detail": _format_attention_detail(role, stage, interval),
            })
            appended["value"] = True
        status["attention_notified_turn"] = key
        return session, None  # saved AFTER the append; nothing more emitted

    with_session_lock(loop_dir, _record)
    return appended["value"]


HOST_STATE_ATTACHED = "attached"
HOST_STATE_NONE = "none"
HOST_STATE_UNKNOWN = "unknown"


def probe_host_state(loop_dir):
    """Authoritative, non-blocking: is any process hosting this loop?

    host.lock is the ownership proof for a watcher (CLI or Dashboard, any
    process). One non-blocking attempt: held -> "attached"; acquired ->
    "none" (released immediately); the file cannot be opened -> "unknown".
    A second handle conflicts with a held lock even in the same process.
    Callers must probe only rarely (attention due and not yet recorded),
    never on every poll.
    """
    fd, err = _try_host_lock(loop_dir)
    if fd is not None:
        release_host_lock(fd)
        return HOST_STATE_NONE
    if err == "held":
        return HOST_STATE_ATTACHED
    return HOST_STATE_UNKNOWN


def attention_status_view(session, loop_dir, now=None, probe=None):
    """Architect-only attention projection for the Dashboard (#47 M4).

    Built field by field from validated primitives (never a passthrough).
    Returns None for legacy sessions. ``notified`` is true when the durable
    marker matches the current turn OR the log already holds a valid event
    for it (the brief event-before-marker window of Decision 3 must never
    hide the notice). The log is scanned only when the marker is missing and
    the turn is actually due, so ordinary polls never read events.jsonl.

    ``host`` (M5 P2) is set only in the due-but-not-notified state, from an
    authoritative host.lock probe ("attached" / "none" / "unknown");
    otherwise it is None and nothing is probed.
    """
    if not attention_mode(session):
        return None
    status = session.get("status", {}) if isinstance(session, dict) else {}
    interval = status.get("turn_timeout_seconds")
    if isinstance(interval, bool) or not isinstance(interval, int):
        interval = None
    key = status.get("turn_started_at")
    if isinstance(key, str):
        try:
            parsed = datetime.fromisoformat(key)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                key = None
        except ValueError:
            key = None
    else:
        key = None
    marker = status.get("attention_notified_turn")
    marker = marker if isinstance(marker, str) else None
    due = _attention_due(session, now or datetime.now(tz=timezone.utc))
    notified = key is not None and marker == key
    if key is not None and not notified and due:
        try:
            notified = _find_attention_event(loop_dir, key)
        except OSError:
            notified = False
    host = None
    if due and not notified:
        try:
            host = (probe or probe_host_state)(loop_dir)
        except Exception:
            host = HOST_STATE_UNKNOWN
        if host not in (HOST_STATE_ATTACHED, HOST_STATE_NONE, HOST_STATE_UNKNOWN):
            host = HOST_STATE_UNKNOWN
    return {
        "interval_seconds": interval,
        "turn_started_at": key,
        "notified_turn": marker,
        "notified": bool(notified),
        "due": bool(due),
        "host": host,
    }


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
