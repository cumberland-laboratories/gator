#!/usr/bin/env python3
"""
gator session-sink — load session data into SQLite, DuckDB, or pipe to external command.

Usage:
    python gator-session-sink.py sqlite  [--db PATH] [--from-spool] [--from-summaries DIR] [--include-turns]
    python gator-session-sink.py duckdb  [--db PATH] [--from-spool] [--from-summaries DIR] [--include-turns]
    python gator-session-sink.py command --command "python load.py"
    python gator-session-sink.py schema  [--format sqlite|duckdb] [--include-turns]

Two input paths:
  --from-spool      reads ~/.gator/session-spool/*.json (rich, full exports with turns)
  --from-summaries  reads .gator/sessions/*.md (lightweight committed summaries, no turns)

Both can be combined in one invocation. The sink is idempotent — duplicate
session rows are skipped via unique constraint on row_key.

--include-turns adds full conversation turns and tool call tables (spool only).
command sink reads spool only (full turns required) and pipes NDJSON to an external process.

This script has zero required dependencies beyond the Python standard library
(for SQLite). DuckDB requires `pip install duckdb`.

@reads: ~/.gator/session-spool/*.json, .gator/sessions/*.md
@writes: specified database file, or external process stdin
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "gator-session-sink-v2"

# Sessions table: one row per session, sourced from either spool or summaries
SESSIONS_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS sessions (
    row_key         TEXT PRIMARY KEY,
    session_id      TEXT,
    date            TEXT,
    start_time      TEXT,
    end_time        TEXT,
    repo            TEXT,
    vendor          TEXT,
    agent           TEXT,
    pi              TEXT,
    branch          TEXT,
    machine_id      TEXT,
    machine_host    TEXT,
    machine_label   TEXT,
    user_turns      INTEGER,
    assistant_turns INTEGER,
    goal            TEXT,
    source_type     TEXT,
    source_file     TEXT,
    loaded_at       TEXT
);
"""

DECISIONS_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key     TEXT REFERENCES sessions(row_key),
    timestamp       TEXT,
    text            TEXT,
    UNIQUE(session_key, timestamp, text)
);
"""

FILES_CHANGED_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS files_changed (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key     TEXT REFERENCES sessions(row_key),
    file_path       TEXT,
    UNIQUE(session_key, file_path)
);
"""

TOOLS_USED_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS tools_used (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key     TEXT REFERENCES sessions(row_key),
    tool            TEXT,
    UNIQUE(session_key, tool)
);
"""

METADATA_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS sink_metadata (
    key             TEXT PRIMARY KEY,
    value           TEXT
);
"""

# Turns tables — only created when --include-turns is active
TURNS_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS turns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key     TEXT REFERENCES sessions(row_key),
    seq             INTEGER NOT NULL,
    role            TEXT,
    timestamp       TEXT,
    content         TEXT,
    vendor_type     TEXT,
    UNIQUE(session_key, seq)
);
"""

TOOL_CALLS_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS tool_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key     TEXT REFERENCES sessions(row_key),
    turn_seq        INTEGER NOT NULL,
    tool            TEXT,
    input_keys      TEXT,
    UNIQUE(session_key, turn_seq, tool, input_keys)
);
"""

ALL_DDL_SQLITE = [
    SESSIONS_DDL_SQLITE,
    DECISIONS_DDL_SQLITE,
    FILES_CHANGED_DDL_SQLITE,
    TOOLS_USED_DDL_SQLITE,
    METADATA_DDL_SQLITE,
]

TURNS_DDL_ALL_SQLITE = [TURNS_DDL_SQLITE, TOOL_CALLS_DDL_SQLITE]


# ---------------------------------------------------------------------------
# Input: spool JSON
# ---------------------------------------------------------------------------

SPOOL_DIR = Path.home() / ".gator" / "session-spool"


def load_spool_sessions(include_turns=False):
    """Read all spool JSON exports, return list of normalized dicts."""
    if not SPOOL_DIR.is_dir():
        return []

    sessions = []
    for f in sorted(SPOOL_DIR.glob("*.json")):
        if f.name.startswith("."):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        meta = data.get("metadata", {})
        summary = data.get("summary", {})
        machine = data.get("machine", {})

        # Build row_key using canonical separator (matches make_row_key in gator-session-common.py)
        import hashlib
        session_id = meta.get("session_id", "")
        source_path = meta.get("source_path", "")
        row_key = hashlib.sha256(
            f"{session_id}|{source_path}".encode()
        ).hexdigest()[:16]

        session_dict = {
            "row_key": row_key,
            "session_id": session_id,
            "date": meta.get("start", "")[:10],
            "start_time": meta.get("start", ""),
            "end_time": meta.get("end", ""),
            "repo": meta.get("repo", ""),
            "vendor": data.get("vendor", ""),
            "agent": summary.get("agent", ""),
            "pi": summary.get("architect", summary.get("pi", "")),
            "branch": (meta.get("branches") or [""])[0] if isinstance(meta.get("branches"), list) else meta.get("branch", ""),
            "machine_id": machine.get("id", ""),
            "machine_host": machine.get("hostname", ""),
            "machine_label": machine.get("label", ""),
            "user_turns": meta.get("user_turns", 0),
            "assistant_turns": meta.get("assistant_turns", 0),
            "goal": summary.get("goal", ""),
            "source_type": "spool",
            "source_file": f.name,
            "decisions": summary.get("decisions", []),
            "files_changed": summary.get("files_changed", []),
            "tools_used": meta.get("tools_used", []) or summary.get("tools", []),
        }

        if include_turns:
            raw_turns = data.get("turns", [])
            session_dict["turns"] = [normalize_turn(t, seq=i) for i, t in enumerate(raw_turns)]

        sessions.append(session_dict)

    return sessions


# ---------------------------------------------------------------------------
# Input: committed summaries
# ---------------------------------------------------------------------------

def load_committed_summaries(sessions_dir):
    """Read committed summary markdown files, return list of normalized dicts."""
    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        return []

    # Import the canonical parser via shared import helper
    scripts_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts_dir))

    try:
        from gator_core import import_sibling
        mod = import_sibling("gator-sessions")
        parse_fn = mod.parse_committed_summary
    except Exception as e:
        print(f"  ! Could not import parse_committed_summary: {e}")
        return []

    sessions = []
    for f in sorted(sessions_path.glob("*.md")):
        if f.name.startswith("_"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        result = parse_fn(text, f.name)
        if not result:
            continue

        # Extract canonical row_key from filename suffix.
        # Committed summaries are written as <date>-<repo>-<vendor>-<row_key>.md
        # where row_key is the 16-char hex hash from make_row_key().
        # This matches the spool path's row_key, enabling cross-path dedup.
        stem = f.stem
        last_segment = stem.rsplit("-", 1)[-1] if "-" in stem else stem
        if len(last_segment) == 16 and all(c in "0123456789abcdef" for c in last_segment):
            row_key = last_segment
        else:
            # Fallback for non-standard filenames
            row_key = f"summary-{stem}"

        sessions.append({
            "row_key": row_key,
            "session_id": "",
            "date": result.get("date", ""),
            "start_time": "",
            "end_time": "",
            "repo": result.get("repo", ""),
            "vendor": result.get("vendor", ""),
            "agent": result.get("agent", ""),
            "pi": "",
            "branch": "",
            "machine_id": "",
            "machine_host": "",
            "machine_label": "",
            "user_turns": 0,
            "assistant_turns": 0,
            "goal": result.get("goal", ""),
            "source_type": "committed-summary",
            "source_file": f.name,
            "decisions": result.get("decisions", []),
            "files_changed": [],
            "tools_used": [],
        })

    return sessions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_content(content):
    """Coerce turn content to string. Codex uses lists, Claude uses strings."""
    if isinstance(content, str):
        return content
    return json.dumps(content, default=str)


def _extract_vendor_type(turn):
    """Extract vendor-specific turn type (Claude: 'type', Codex: 'item_type')."""
    return turn.get("type", "") or turn.get("item_type", "")


def _normalize_tool_calls(turn):
    """Normalize tool_calls to stable format [{tool, input_keys, input_hash}].

    input_keys stores the parameter names (for schema inspection).
    input_hash stores a short hash of the full input (for dedup of
    multiple calls to the same tool with different arguments).
    """
    import hashlib
    raw = turn.get("tool_calls", [])
    normalized = []
    for tc in raw:
        tool = tc.get("tool", "") or tc.get("name", "")
        if isinstance(tc.get("input"), dict):
            input_keys = sorted(tc["input"].keys())
            input_hash = hashlib.sha256(
                json.dumps(tc["input"], sort_keys=True, default=str).encode()
            ).hexdigest()[:8]
        else:
            input_keys = tc.get("input_keys", [])
            input_hash = ""
        normalized.append({
            "tool": tool,
            "input_keys": input_keys,
            "input_hash": input_hash,
        })
    return normalized


def normalize_turn(turn, seq=None):
    """Normalize a vendor-specific turn to the stable contract.

    Output follows the published schema: seq, role, timestamp, content
    (always string), vendor_type (stable field), tool_calls (normalized).
    Vendor-specific fields (cwd, branch, item_type, etc.) are stripped.
    """
    return {
        "seq": seq if seq is not None else turn.get("seq", 0),
        "role": turn.get("role", ""),
        "timestamp": turn.get("timestamp", ""),
        "content": _coerce_content(turn.get("content", "")),
        "vendor_type": _extract_vendor_type(turn),
        "tool_calls": _normalize_tool_calls(turn),
    }


def _insert_turns_sqlite(cur, row_key, turns):
    """Insert turns and tool_calls for a session into SQLite.

    Normalizes each turn on the fly for robustness — handles both
    pre-normalized turns and raw vendor turns.
    """
    for i, t in enumerate(turns):
        norm = normalize_turn(t, seq=t.get("seq", i))
        seq = norm["seq"]
        cur.execute(
            """INSERT OR IGNORE INTO turns
               (session_key, seq, role, timestamp, content, vendor_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                row_key,
                seq,
                norm["role"],
                norm["timestamp"],
                norm["content"],
                norm["vendor_type"],
            ),
        )

        for tc in norm["tool_calls"]:
            # Include hash in stored value for uniqueness across same-tool calls
            keys_with_hash = tc.get("input_keys", [])
            ih = tc.get("input_hash", "")
            input_keys = json.dumps(keys_with_hash) + (f"|{ih}" if ih else "")
            cur.execute(
                "INSERT OR IGNORE INTO tool_calls (session_key, turn_seq, tool, input_keys) VALUES (?, ?, ?, ?)",
                (row_key, seq, tc.get("tool", ""), input_keys),
            )


# ---------------------------------------------------------------------------
# Sink: SQLite
# ---------------------------------------------------------------------------

def sink_sqlite(db_path, sessions, include_turns=False):
    """Write sessions to a SQLite database."""
    import sqlite3

    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db))
    cur = conn.cursor()

    # Create schema
    for ddl in ALL_DDL_SQLITE:
        cur.execute(ddl)

    if include_turns:
        for ddl in TURNS_DDL_ALL_SQLITE:
            cur.execute(ddl)

    # Write schema version
    cur.execute(
        "INSERT OR REPLACE INTO sink_metadata (key, value) VALUES (?, ?)",
        ("schema_version", SCHEMA_VERSION),
    )
    cur.execute(
        "INSERT OR REPLACE INTO sink_metadata (key, value) VALUES (?, ?)",
        ("last_load", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
    )

    loaded = 0
    skipped = 0

    for s in sessions:
        try:
            cur.execute(
                """INSERT OR IGNORE INTO sessions
                   (row_key, session_id, date, start_time, end_time, repo, vendor,
                    agent, pi, branch, machine_id, machine_host, machine_label,
                    user_turns, assistant_turns, goal, source_type, source_file, loaded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    s["row_key"], s["session_id"], s["date"], s["start_time"],
                    s["end_time"], s["repo"], s["vendor"], s["agent"], s["pi"],
                    s["branch"], s["machine_id"], s["machine_host"], s["machine_label"],
                    s["user_turns"], s["assistant_turns"], s["goal"],
                    s["source_type"], s["source_file"],
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )

            if cur.rowcount == 0:
                skipped += 1
                continue

            loaded += 1

            # Decisions
            for d in s.get("decisions", []):
                ts = d.get("timestamp", "") if isinstance(d, dict) else ""
                text = d.get("text", "") if isinstance(d, dict) else str(d)
                cur.execute(
                    "INSERT OR IGNORE INTO decisions (session_key, timestamp, text) VALUES (?, ?, ?)",
                    (s["row_key"], ts, text),
                )

            # Files changed
            for fp in s.get("files_changed", []):
                cur.execute(
                    "INSERT OR IGNORE INTO files_changed (session_key, file_path) VALUES (?, ?)",
                    (s["row_key"], fp),
                )

            # Tools used
            for tool in s.get("tools_used", []):
                cur.execute(
                    "INSERT OR IGNORE INTO tools_used (session_key, tool) VALUES (?, ?)",
                    (s["row_key"], tool),
                )

            # Turns (only from spool — summaries don't have turns)
            if include_turns and s.get("turns"):
                _insert_turns_sqlite(cur, s["row_key"], s["turns"])

        except Exception as e:
            print(f"  ! {s.get('source_file', '?')}: {e}")
            continue

    conn.commit()
    conn.close()

    return loaded, skipped


# ---------------------------------------------------------------------------
# Sink: DuckDB
# ---------------------------------------------------------------------------

def sink_duckdb(db_path, sessions, include_turns=False):
    """Write sessions to a DuckDB database."""
    try:
        import duckdb
    except ImportError:
        print("  ! DuckDB not installed. Run: pip install duckdb")
        sys.exit(1)

    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(db))

    # Create schema — DuckDB accepts most SQLite DDL
    conn.execute(SESSIONS_DDL_SQLITE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id              INTEGER PRIMARY KEY DEFAULT nextval('decisions_id_seq'),
            session_key     TEXT,
            timestamp       TEXT,
            text            TEXT,
            UNIQUE(session_key, timestamp, text)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files_changed (
            id              INTEGER PRIMARY KEY DEFAULT nextval('files_id_seq'),
            session_key     TEXT,
            file_path       TEXT,
            UNIQUE(session_key, file_path)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tools_used (
            id              INTEGER PRIMARY KEY DEFAULT nextval('tools_id_seq'),
            session_key     TEXT,
            tool            TEXT,
            UNIQUE(session_key, tool)
        );
    """)
    conn.execute(METADATA_DDL_SQLITE)

    if include_turns:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turns (
                id              INTEGER PRIMARY KEY DEFAULT nextval('turns_id_seq'),
                session_key     TEXT,
                seq             INTEGER NOT NULL,
                role            TEXT,
                timestamp       TEXT,
                content         TEXT,
                vendor_type     TEXT,
                UNIQUE(session_key, seq)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tool_calls (
                id              INTEGER PRIMARY KEY DEFAULT nextval('tcalls_id_seq'),
                session_key     TEXT,
                turn_seq        INTEGER NOT NULL,
                tool            TEXT,
                input_keys      TEXT,
                UNIQUE(session_key, turn_seq, tool, input_keys)
            );
        """)

    # Schema version
    conn.execute(
        "INSERT OR REPLACE INTO sink_metadata (key, value) VALUES (?, ?)",
        [SCHEMA_VERSION, SCHEMA_VERSION],
    )

    loaded = 0
    skipped = 0

    for s in sessions:
        try:
            result = conn.execute(
                "SELECT 1 FROM sessions WHERE row_key = ?", [s["row_key"]]
            ).fetchone()
            if result:
                skipped += 1
                continue

            conn.execute(
                """INSERT INTO sessions
                   (row_key, session_id, date, start_time, end_time, repo, vendor,
                    agent, pi, branch, machine_id, machine_host, machine_label,
                    user_turns, assistant_turns, goal, source_type, source_file, loaded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    s["row_key"], s["session_id"], s["date"], s["start_time"],
                    s["end_time"], s["repo"], s["vendor"], s["agent"], s["pi"],
                    s["branch"], s["machine_id"], s["machine_host"], s["machine_label"],
                    s["user_turns"], s["assistant_turns"], s["goal"],
                    s["source_type"], s["source_file"],
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ],
            )

            loaded += 1

            for d in s.get("decisions", []):
                ts = d.get("timestamp", "") if isinstance(d, dict) else ""
                text = d.get("text", "") if isinstance(d, dict) else str(d)
                try:
                    conn.execute(
                        "INSERT INTO decisions (session_key, timestamp, text) VALUES (?, ?, ?)",
                        [s["row_key"], ts, text],
                    )
                except duckdb.ConstraintException:
                    pass

            for fp in s.get("files_changed", []):
                try:
                    conn.execute(
                        "INSERT INTO files_changed (session_key, file_path) VALUES (?, ?)",
                        [s["row_key"], fp],
                    )
                except duckdb.ConstraintException:
                    pass

            for tool in s.get("tools_used", []):
                try:
                    conn.execute(
                        "INSERT INTO tools_used (session_key, tool) VALUES (?, ?)",
                        [s["row_key"], tool],
                    )
                except duckdb.ConstraintException:
                    pass

            # Turns — normalize on the fly for robustness
            if include_turns and s.get("turns"):
                for i, t in enumerate(s["turns"]):
                    norm = normalize_turn(t, seq=t.get("seq", i))
                    seq = norm["seq"]
                    try:
                        conn.execute(
                            """INSERT INTO turns
                               (session_key, seq, role, timestamp, content, vendor_type)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            [
                                s["row_key"], seq, norm["role"],
                                norm["timestamp"], norm["content"],
                                norm["vendor_type"],
                            ],
                        )
                    except duckdb.ConstraintException:
                        pass

                    for tc in norm["tool_calls"]:
                        keys_with_hash = tc.get("input_keys", [])
                        ih = tc.get("input_hash", "")
                        input_keys = json.dumps(keys_with_hash) + (f"|{ih}" if ih else "")
                        try:
                            conn.execute(
                                "INSERT INTO tool_calls (session_key, turn_seq, tool, input_keys) VALUES (?, ?, ?, ?)",
                                [s["row_key"], seq, tc.get("tool", ""), input_keys],
                            )
                        except duckdb.ConstraintException:
                            pass

        except Exception as e:
            print(f"  ! {s.get('source_file', '?')}: {e}")
            continue

    conn.close()

    return loaded, skipped


# ---------------------------------------------------------------------------
# Sink: Command (NDJSON pipe)
# ---------------------------------------------------------------------------

def sink_command(sessions, command):
    """Pipe sessions as NDJSON to an external process's stdin."""
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except Exception as e:
        print(f"  ! Failed to start command: {e}")
        return 0, 0

    written = 0
    for s in sessions:
        try:
            line = json.dumps(s, default=str)
            proc.stdin.write(line + "\n")
            written += 1
        except BrokenPipeError:
            print("  ! Pipe broken — external process closed stdin early")
            break
        except Exception as e:
            print(f"  ! Error writing session: {e}")
            continue

    proc.stdin.close()
    exit_code = proc.wait()

    if exit_code != 0:
        print(f"  ! Command exited with code {exit_code}")

    return written, exit_code


# ---------------------------------------------------------------------------
# Command: schema
# ---------------------------------------------------------------------------

def cmd_schema(args):
    """Print the database schema DDL."""
    fmt = getattr(args, "format", "sqlite") or "sqlite"
    include_turns = getattr(args, "include_turns", False)
    print(f"-- gator-session-sink schema ({fmt})")
    print(f"-- version: {SCHEMA_VERSION}")
    print()
    for ddl in ALL_DDL_SQLITE:
        print(ddl.strip())
        print()
    if include_turns:
        print("-- Turn-level tables (--include-turns)")
        print()
        for ddl in TURNS_DDL_ALL_SQLITE:
            print(ddl.strip())
            print()


# ---------------------------------------------------------------------------
# Command: sqlite / duckdb
# ---------------------------------------------------------------------------

def cmd_sink(args, engine):
    """Load sessions into a database."""
    include_turns = getattr(args, "include_turns", False)
    sessions = []

    if args.from_spool:
        print(f"  Reading spool from {SPOOL_DIR} ...")
        spool = load_spool_sessions(include_turns=include_turns)
        print(f"  Found {len(spool)} spool exports")
        sessions.extend(spool)

    if args.from_summaries:
        print(f"  Reading committed summaries from {args.from_summaries} ...")
        summaries = load_committed_summaries(args.from_summaries)
        print(f"  Found {len(summaries)} committed summaries")
        sessions.extend(summaries)

    if not args.from_spool and not args.from_summaries:
        # Default: load from spool
        print(f"  Reading spool from {SPOOL_DIR} ...")
        spool = load_spool_sessions(include_turns=include_turns)
        print(f"  Found {len(spool)} spool exports")
        sessions.extend(spool)

    if not sessions:
        print("  No sessions to load.")
        return

    db_path = args.db or f"gator-sessions.{engine}"
    turns_note = " (with turns)" if include_turns else ""
    print(f"  Loading {len(sessions)} sessions{turns_note} into {db_path} ...")

    if engine == "sqlite":
        loaded, skipped = sink_sqlite(db_path, sessions, include_turns=include_turns)
    else:
        loaded, skipped = sink_duckdb(db_path, sessions, include_turns=include_turns)

    print()
    print(f"  Loaded:  {loaded} sessions")
    if skipped:
        print(f"  Skipped: {skipped} (already in database)")
    print(f"  Database: {Path(db_path).resolve()}")
    print()


# ---------------------------------------------------------------------------
# Command: command (NDJSON pipe)
# ---------------------------------------------------------------------------

def cmd_command(args):
    """Pipe full-turn sessions as NDJSON to an external process.

    Spool-only: committed summaries lack turns and are excluded from
    the command sink to guarantee every NDJSON line is turn-complete.
    """
    print(f"  Reading spool from {SPOOL_DIR} ...")
    sessions = load_spool_sessions(include_turns=True)

    if not sessions:
        print("  No sessions to deliver.")
        return

    print(f"  Piping {len(sessions)} sessions to: {args.ext_command}")

    written, exit_code = sink_command(sessions, args.ext_command)

    print()
    print(f"  Delivered: {written} sessions")
    if exit_code != 0:
        print(f"  Command exit code: {exit_code}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="gator session-sink — load session data into SQLite, DuckDB, or pipe to external command."
    )
    sub = parser.add_subparsers(dest="command", help="Sink target")

    # sqlite
    sq = sub.add_parser("sqlite", help="Load into SQLite database")
    sq.add_argument("--db", help="Database path (default: gator-sessions.sqlite)")
    sq.add_argument("--from-spool", action="store_true", help="Load from ~/.gator/session-spool/")
    sq.add_argument("--from-summaries", metavar="DIR", help="Load from committed summaries directory")
    sq.add_argument("--include-turns", action="store_true", help="Include full conversation turns and tool calls")

    # duckdb
    dk = sub.add_parser("duckdb", help="Load into DuckDB database")
    dk.add_argument("--db", help="Database path (default: gator-sessions.duckdb)")
    dk.add_argument("--from-spool", action="store_true", help="Load from ~/.gator/session-spool/")
    dk.add_argument("--from-summaries", metavar="DIR", help="Load from committed summaries directory")
    dk.add_argument("--include-turns", action="store_true", help="Include full conversation turns and tool calls")

    # command (NDJSON pipe) — spool only (full turns required)
    cmd = sub.add_parser("command", help="Pipe full-turn NDJSON to external process stdin (spool only)")
    cmd.add_argument("--from-spool", action="store_true", help="Load from ~/.gator/session-spool/ (default)")
    cmd.add_argument("--command", dest="ext_command", required=True, help="External command to pipe to")

    # schema
    sc = sub.add_parser("schema", help="Print the database schema DDL")
    sc.add_argument("--format", choices=["sqlite", "duckdb"], default="sqlite")
    sc.add_argument("--include-turns", action="store_true", help="Include turns/tool_calls DDL")

    args = parser.parse_args()

    if args.command == "sqlite":
        cmd_sink(args, "sqlite")
    elif args.command == "duckdb":
        cmd_sink(args, "duckdb")
    elif args.command == "command":
        cmd_command(args)
    elif args.command == "schema":
        cmd_schema(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
