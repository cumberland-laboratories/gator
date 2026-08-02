"""
Event stream for gator loop.

Owns: event emission (append to events.jsonl), event tailing (follow for
new entries), and human-readable event formatting.

Events are append-only. The events.jsonl file is the observation surface
for the host process and the `gator loop tail` command. All event emission
happens inside the session lock, AFTER session.json has been durably
written — see session.py's with_session_lock().
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# sys.path-based import — scripts/ is package data, not an importable
# sub-package, so relative imports don't work in this repo's dispatch model.
_LOOP_DIR = str(Path(__file__).resolve().parent)
if _LOOP_DIR not in sys.path:
    sys.path.insert(0, _LOOP_DIR)

from session import EVENTS_FILENAME, _make_readonly, _make_writable


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------

def emit_event(loop_dir, event_dict):
    """Append a single event to events.jsonl.

    Called inside the session lock by with_session_lock() — never call
    this outside of a lock context during normal operation. The only
    exception is the initial loop_started event during host init.

    Adds timestamp and loop_id if not already present.
    """
    loop_dir = Path(loop_dir)
    events_path = loop_dir / EVENTS_FILENAME

    if "ts" not in event_dict:
        event_dict["ts"] = datetime.now(tz=timezone.utc).isoformat()
    if "loop_id" not in event_dict:
        event_dict["loop_id"] = loop_dir.name

    _make_writable(events_path)
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event_dict, separators=(",", ":")) + "\n")
    _make_readonly(events_path)


def create_events_file(loop_dir):
    """Create an empty events.jsonl file."""
    events_path = Path(loop_dir) / EVENTS_FILENAME
    events_path.touch(exist_ok=True)


# ---------------------------------------------------------------------------
# Event tailing
# ---------------------------------------------------------------------------

TERMINAL_EVENTS = frozenset({
    "plan_approved",
    "max_rounds_exceeded",
    "turn_timed_out",
    "loop_ended_by_architect",
})


def tail_events(loop_dir, poll_interval=2.0):
    """Follow events.jsonl, yielding new events as they appear.

    This is a generator that polls for new lines appended to the file.
    Yields parsed event dicts. Stops when a terminal event is seen or
    when the caller breaks out of the loop.

    Used by the host watch loop and `gator loop tail`.
    """
    events_path = Path(loop_dir) / EVENTS_FILENAME

    # Start from the current end of file
    if events_path.exists():
        last_pos = events_path.stat().st_size
    else:
        last_pos = 0

    while True:
        if not events_path.exists():
            time.sleep(poll_interval)
            continue

        current_size = events_path.stat().st_size
        if current_size > last_pos:
            with open(events_path, "r", encoding="utf-8") as f:
                f.seek(last_pos)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    yield event
                    if event.get("event") in TERMINAL_EVENTS:
                        return
                last_pos = f.tell()

        time.sleep(poll_interval)


def read_all_events(loop_dir):
    """Read all events from events.jsonl. Non-blocking, returns a list."""
    events_path = Path(loop_dir) / EVENTS_FILENAME
    if not events_path.exists():
        return []
    events = []
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


# ---------------------------------------------------------------------------
# Event formatting
# ---------------------------------------------------------------------------

# Map event types to human-readable labels and optional format templates
_EVENT_FORMATS = {
    "loop_started": ("loop started", None),
    "draft_submitted": ("draft submitted", "round {round}"),
    "review_submitted": ("review submitted", "round {round}"),
    "plan_approved": ("plan APPROVED", "round {round}"),
    "revision_requested": ("revision requested", "round {round}"),
    "escalated": ("ESCALATED", "{detail}"),
    "max_rounds_exceeded": ("MAX ROUNDS", "limit reached at round {round}"),
    "turn_timed_out": ("TIMED OUT", "{role} did not submit in time"),
    "loop_unblocked": ("unblocked", "{detail}"),
    "loop_paused": ("PAUSED", "{detail}"),
    "architect_interjection": ("ARCHITECT", "{detail}"),
    "loop_ended_by_architect": ("ENDED", "{detail}"),
}


def format_event(event):
    """Format an event dict as a human-readable log line.

    Output format: [HH:MM:SS] <label> (<detail>)
    """
    ts = event.get("ts", "")
    try:
        dt = datetime.fromisoformat(ts)
        time_str = dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        time_str = "??:??:??"

    event_type = event.get("event", "unknown")
    label, detail_template = _EVENT_FORMATS.get(event_type, (event_type, None))

    parts = [f"  [{time_str}] {label}"]

    if detail_template:
        try:
            detail = detail_template.format(**event)
            parts.append(f"({detail})")
        except (KeyError, IndexError):
            pass
    elif "detail" in event:
        parts.append(f"({event['detail']})")

    role = event.get("role")
    if role and not detail_template:
        parts.append(f"[{role}]")

    return " ".join(parts)


def format_next_prompt(session):
    """Format a 'next step' line based on current session state.

    Used by the host to show what's expected after each event.
    """
    stage = session.get("status", {}).get("stage", "")
    next_role = session.get("status", {}).get("next_role")

    if next_role:
        return f"  next: {next_role} ({stage})"
    elif stage in ("blocked_on_architect", "paused_by_architect"):
        return "  paused -- waiting for Architect (gator loop unblock)"
    else:
        return f"  loop ended ({stage})"
