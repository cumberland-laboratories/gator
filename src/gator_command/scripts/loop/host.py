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


# ---------------------------------------------------------------------------
# Initialization — gator loop start
# ---------------------------------------------------------------------------

def start_loop(feature, sketch_path, max_rounds=3, turn_timeout=300):
    """Initialize a new loop session and enter the watch loop.

    1. Validate sketch file
    2. Create loop directory under .gator/loops/
    3. Copy sketch, generate tokens, write session + initial event
    4. Print startup banner with tokens
    5. Enter watch loop (blocks until terminal state)

    Returns the loop_id (after the watch loop exits).
    """
    # Validate sketch
    sketch = Path(sketch_path)
    if not sketch.exists():
        raise FileNotFoundError(f"Sketch file not found: {sketch_path}")
    if sketch.stat().st_size == 0:
        raise ValueError(f"Sketch file is empty: {sketch_path}")

    # Resolve repo root and create loop directory
    repo_root = find_gator_root()
    loop_id = make_loop_id(feature)
    loops_base = repo_root / ".gator" / "loops"
    loops_base.mkdir(parents=True, exist_ok=True)
    ensure_loops_gitignore(loops_base)

    loop_dir = loops_base / loop_id
    loop_dir.mkdir()

    # Copy sketch
    sketch_dest = loop_dir / "sketch.md"
    shutil.copy2(str(sketch), str(sketch_dest))
    _make_readonly(sketch_dest)

    # Generate tokens (three roles: draftor, reviewer, architect)
    tok_d, nonce_d = make_token(loop_id, "draftor")
    tok_r, nonce_r = make_token(loop_id, "reviewer")
    tok_a, nonce_a = make_token(loop_id, "architect")
    save_tokens(loop_dir, {
        "draftor": {"nonce": nonce_d, "token": tok_d},
        "reviewer": {"nonce": nonce_r, "token": tok_r},
        "architect": {"nonce": nonce_a, "token": tok_a},
    })

    # Write initial session
    session = create_session(feature, loop_id, max_rounds, turn_timeout)
    save_session(loop_dir, session)

    # Write initial event
    create_events_file(loop_dir)
    emit_event(loop_dir, {
        "event": "loop_started",
        "detail": "Loop initialized",
    })

    # Print startup banner
    _print_banner(loop_id, feature, max_rounds, turn_timeout, tok_d, tok_r, tok_a)

    # Enter watch loop (blocks)
    watch_loop(loop_dir)

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

def watch_loop(loop_dir):
    """Tail events.jsonl, render log lines, enforce turn timeouts.

    Runs until a terminal state is reached. During paused states
    (blocked_on_architect), the host stays alive but suspends timeout
    enforcement — it continues rendering events (e.g., loop_unblocked).
    """
    loop_dir = Path(loop_dir)
    events_path = loop_dir / "events.jsonl"

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

                    if event.get("event") in TERMINAL_EVENTS:
                        _print_terminal_summary(loop_dir)
                        return

                last_pos = f.tell()

            # After rendering events, show the next-step prompt
            try:
                session = load_session(loop_dir)
                if not is_terminal(session):
                    print(format_next_prompt(session))
                    print("  waiting...")
                    sys.stdout.flush()
            except (FileNotFoundError, KeyError):
                pass

        # --- Phase 2: timeout enforcement (active states only) ---
        try:
            session = load_session(loop_dir)
        except (FileNotFoundError, KeyError):
            time.sleep(POLL_INTERVAL)
            continue

        stage = session["status"].get("stage")
        if stage in ACTIVE_STAGES:
            deadline_str = session["status"].get("turn_deadline")
            if deadline_str:
                try:
                    deadline = datetime.fromisoformat(deadline_str)
                    if datetime.now(tz=timezone.utc) > deadline:
                        _try_enforce_timeout(loop_dir)
                except (ValueError, TypeError):
                    pass

        time.sleep(POLL_INTERVAL)


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
