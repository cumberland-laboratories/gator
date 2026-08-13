#!/usr/bin/env python3
"""
gator audit — Convergence dashboard for fleet governance posture.

Assembles data from fleet-report, drift, sessions, and charters into
a unified audit view. Three output modes: terminal text (PI/developer),
JSON (automation), HTML (CISO/browser, self-contained, no external deps).

This is the presentation layer for everything Gator knows. No new data
collection — intelligence from existing data sources.

Usage:
    python gator-command/scripts/gator-audit.py
    python gator-command/scripts/gator-audit.py --json
    python gator-command/scripts/gator-audit.py --html
    python gator-command/scripts/gator-audit.py --html --open
    python gator-command/scripts/gator-audit.py --since 7d

@reads: fleet-report data, drift data, session index, .gator/ state
@writes: stdout (text/json) or audit-report.html (--html)
"""

import argparse
import json
import os
import subprocess
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gator_core import get_version, ensure_utf8_stdout, import_sibling, find_gator_root

# Renderers live in a separate module — pure functions, no shared state.
# Loaded lazily so --sessions and --json don't crash if renderers are missing.
_renderers = None


def render_text(data):
    """Render audit data as terminal text (delegates to gator-audit-renderers)."""
    _ensure_renderers()
    return _renderers.render_text(data)


def render_html(data):
    """Render audit data as self-contained HTML (delegates to gator-audit-renderers)."""
    _ensure_renderers()
    return _renderers.render_html(data)


def _ensure_renderers():
    global _renderers
    if _renderers is not None:
        return
    _renderers = import_sibling("gator-audit-renderers")
    if _renderers is None:
        raise ImportError(
            "gator-audit-renderers.py not found. "
            "This file must be in the same directory as gator-audit.py."
        )


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

VERSION = get_version()

# Alias for readability in this script
_import_script = import_sibling


# ---------------------------------------------------------------------------
# Data Assembly
# ---------------------------------------------------------------------------

# Session choreography phrases that are NOT governance decisions
_CHOREOGRAPHY = {
    "yes", "ok", "no", "sure", "thanks", "thank you", "got it",
    "yes, proceed", "yes, update it", "do it", "proceed", "approved",
    "go ahead", "sounds good", "looks good", "continue", "next",
    "let's continue", "let's move on",
}

# Patterns that indicate session choreography, not governance decisions
_CHOREOGRAPHY_PATTERNS = [
    "let's review", "let's look", "let's check", "let's see",
    "let's commit", "let's push", "let's merge",
    "let's get", "let's do", "let's start", "let's try",
    "please review", "please check", "review pass", "review please",
    "read the constitution", "read the org policy", "read the mission",
    "gator init", "gator update", "gator commit",
    "yes, read", "yes, re-read", "yes, make", "yes, draft",
    "make all", "fix that", "fix this",
]


def _is_real_decision(text):
    """Filter session choreography from governance decisions.

    A real decision changes direction, commits to an approach, or
    resolves a tradeoff. Session choreography (review requests,
    confirmations, navigation) is not governance evidence.
    """
    if not text or len(text) < 20:
        return False

    # Skip tool results
    if text.startswith("[tool result"):
        return False

    lower = text.lower().strip()

    # Skip bare confirmations
    if lower in _CHOREOGRAPHY:
        return False

    # Skip choreography patterns (check anywhere in text, not just start)
    for pattern in _CHOREOGRAPHY_PATTERNS:
        if pattern in lower:
            return False

    # Require substantive content — must contain a noun-like word
    # beyond just "let's" + verb
    words = lower.split()
    if len(words) < 4:
        return False

    return True


def _collect_trailer_intelligence(fleet_status, since_days):
    """Scan commit trailers across accessible fleet repos.

    Produces three datasets used by the dashboard Audit view:
    - override_events: commits where Gator-Override: trailer was present
    - significance_distribution: counts of each Gator-Significance value
    - governed_commits: governed commit counts per repo + fleet total

    A governed commit is any commit carrying at least one Gator-* trailer.
    Runs git log directly against each local repo path.

    @reads: git log from each accessible local repo path
    """
    override_events = []
    sig_dist = {}
    governed_commits = {}

    since_str = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")

    for repo in fleet_status:
        if not repo.get("accessible"):
            continue
        path = repo.get("path", "")
        name = repo.get("name", "?")
        if not path or not Path(path).is_dir():
            continue

        try:
            result = subprocess.run(
                [
                    "git", "log", f"--since={since_str}",
                    # %at = Unix timestamp (seconds since epoch) — always UTC,
                    # no offset ambiguity. Do NOT use %ai/%aI: those embed a
                    # local offset that we'd have to parse to convert to UTC.
                    "--format=COMMIT\x1f%H\x1f%at\x1f%(trailers:separator=\x1e)",
                ],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                continue

            repo_governed = 0
            for block in result.stdout.split("COMMIT"):
                # Do NOT strip block — \x1f is treated as whitespace by Python's
                # str.strip(), which would remove the leading field separator and
                # collapse 4 parts into 3.
                if not block:
                    continue
                parts = block.split("\x1f")
                if len(parts) < 4:
                    continue
                commit_hash = parts[1].strip()
                # Convert Unix timestamp to UTC ISO 8601
                try:
                    commit_ts = datetime.fromtimestamp(
                        int(parts[2].strip()), tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                except (ValueError, OSError):
                    commit_ts = ""
                trailers_raw = parts[3]

                # Parse trailer lines into a dict
                trailer_dict = {}
                for line in (t.strip() for t in trailers_raw.split("\x1e") if t.strip()):
                    if ":" in line:
                        k, _, v = line.partition(":")
                        trailer_dict[k.strip()] = v.strip()

                # Only count commits with Gator-* trailers
                if not any(k.startswith("Gator-") for k in trailer_dict):
                    continue

                repo_governed += 1

                # Override events
                override_val = trailer_dict.get("Gator-Override", "")
                if override_val:
                    override_events.append({
                        "repo": name,
                        "hash": commit_hash[:7],
                        "timestamp": commit_ts,
                        "override_type": override_val,
                        # Approver comes from Gator-Override-Approved-By, not
                        # Gator-Architect. The hook writes this trailer from
                        # .override-meta.json at commit time — it records who
                        # actually ran gator-approve.py, which may differ from
                        # the session PI identity.
                        "approver": trailer_dict.get("Gator-Override-Approved-By", ""),
                        "block_id": trailer_dict.get("Gator-Override-Block", ""),
                    })

                # Significance distribution
                sig = trailer_dict.get("Gator-Significance", "").lower()
                if sig:
                    sig_dist[sig] = sig_dist.get(sig, 0) + 1

            governed_commits[name] = repo_governed

        except (subprocess.TimeoutExpired, OSError, ValueError):
            continue

    governed_commits["total"] = sum(v for k, v in governed_commits.items() if k != "total")

    # Sort overrides most-recent first
    override_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return override_events, sig_dist, governed_commits


# ---------------------------------------------------------------------------
# Decision-source branches (Phase 2B, 2026-08-12 — extracted from
# assemble_audit_data for cleanly-separable Phase 3 deletion per parent plan
# .gator/vault/artifacts/2026-08-11-non-enterprise-session-cleanup-plan.md §6
# Phase 2. Behavior preserved byte-for-byte.)
# ---------------------------------------------------------------------------

def _committed_decisions_from_snippets(
    reader_mod, sessions_dirs_tagged, has_remote_sessions, data, since_days
):
    """Assemble (decisions, summary_items) from committed .md summaries.

    Snippet-reader branch. **SURVIVING** contract per parent plan §2.1 — the
    durable, portable read path via `gator_session_reader.py`. Called from
    assemble_audit_data() when at least one `.gator/sessions/*.md` exists in
    the fleet or a remote cache has session summaries.

    Reader-side data mutations: pops `data["_remote_sessions"]` if present.
    """
    committed_decisions = []
    summary_items = []
    all_summaries = []

    if reader_mod:
        for sdir, source_kind in sessions_dirs_tagged:
            for s in reader_mod.read_committed_summaries(sdir, since_days):
                s["source_kind"] = source_kind
                all_summaries.append(s)

    # Also read remote session summaries from bare caches.
    # Uses the same parse_committed_summary() as the local path
    # to ensure identical decision extraction behavior.
    if has_remote_sessions and reader_mod:
        try:
            from gator_remote import read_session_summary_remote
            for remote_info in data.pop("_remote_sessions"):
                for filename in remote_info["files"]:
                    content = read_session_summary_remote(
                        remote_info["cache_path"], filename
                    )
                    if content:
                        result = reader_mod.parse_committed_summary(
                            content, filename
                        )
                        if result:
                            result["source_kind"] = "remote-cache"
                            all_summaries.append(result)
        except ImportError:
            pass

    # Build summary metadata with provenance for drill-down
    for s in all_summaries:
        summary_items.append({
            "date": s.get("date", ""),
            "start": s.get("start", ""),
            "repo": s.get("repo", ""),
            "vendor": s.get("vendor", ""),
            "agent": s.get("agent", ""),
            "goal": s.get("goal", ""),
            "decisions_count": len(s.get("decisions", [])),
            "source_file": s.get("source_file", ""),
            "source_kind": s.get("source_kind", "command-post"),
        })
    summary_items.sort(
        key=lambda x: (x.get("start", "") or x.get("date", ""), x.get("source_file", "")),
        reverse=True,
    )

    for s in all_summaries:
        for d in s.get("decisions", []):
            text = d.get("text", "")
            if not _is_real_decision(text):
                continue
            committed_decisions.append({
                "timestamp": d.get("timestamp", ""),
                "text": text,
                "repo": s.get("repo", ""),
                "vendor": s.get("vendor", ""),
            })

    return committed_decisions, summary_items


def assemble_audit_data(since_days=7):
    """Assemble all audit data from existing Gator subsystems.

    Returns a unified dict with fleet_status, drift, sessions,
    governance, decisions, and metadata.
    """
    data = {
        "schema": "gator-audit-v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_local": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "version": VERSION,
        "since_days": since_days,
        "machine": {},
        "fleet_status": [],
        "drift": [],
        "drift_summary": {},
        "sessions": {},
        "governance": {},
        "decisions": [],
    }

    # Snippet-based session reader (`gator_session_reader.py`) — post-Phase-3
    # owner of both `get_machine_identity()` (folded from gator-session-common
    # in Phase 3F, 2026-08-13) AND the committed-summary parser/reader
    # (extracted from gator-sessions in Phase 2A). Used here for machine
    # identity; used again in the decisions section below.
    try:
        reader_mod = _import_script("gator_session_reader")
    except ImportError as e:
        reader_mod = None
        data["_errors"] = data.get("_errors", []) + [f"session-reader: {e}"]
    if reader_mod:
        data["machine"] = reader_mod.get_machine_identity()

    # Fleet report
    try:
        fleet_mod = _import_script("gator-fleet-report")
    except ImportError as e:
        fleet_mod = None
        data["fleet_status"] = [{"error": f"import failed: {e}"}]
    if fleet_mod:
        try:
            cp = fleet_mod.find_command_post()
            if cp:
                repos = fleet_mod.parse_registry(cp)
                reports = fleet_mod.scan_fleet(repos)
                data["fleet_status"] = reports
        except (OSError, KeyError, ValueError) as e:
            data["fleet_status"] = [{"error": f"{type(e).__name__}: {e}"}]

    # Drift
    try:
        drift_mod = _import_script("gator-drift")
    except ImportError as e:
        drift_mod = None
        data["drift"] = [{"error": f"import failed: {e}"}]
    if drift_mod:
        try:
            cp = drift_mod.find_command_post()
            if cp:
                repos = drift_mod.parse_registry(cp)
                cp_state = drift_mod.read_command_post_policy(cp)
                results = [drift_mod.check_repo_drift(r, cp_state) for r in repos]
                data["drift"] = results
                data["drift_summary"] = {
                    "command_post": cp_state,
                    "ok": sum(1 for r in results if r["severity"] == "ok"),
                    "warn": sum(1 for r in results if r["severity"] == "warn"),
                    "drift": sum(1 for r in results if r["severity"] == "drift"),
                }
        except (OSError, KeyError, ValueError) as e:
            data["drift"] = [{"error": f"{type(e).__name__}: {e}"}]

    # (`reader_mod` loaded above with machine identity — reused for the
    # decisions section further down. Vendor-transcript-derived session
    # counts retired in Phase 3 Commit D per parent plan §5 decision 4 = (i)
    # drop silently. `data["sessions"]` stays as the `{}` init.)

    # Governance coverage (from fleet data)
    if data["fleet_status"]:
        accessible = [r for r in data["fleet_status"] if r.get("accessible")]
        total_charters = sum(r.get("charters", 0) for r in accessible)
        total_functions = sum(r.get("functions", 0) for r in accessible)
        total_issues = sum(r.get("issues", 0) for r in accessible)
        with_hooks = sum(1 for r in accessible if r.get("has_hooks"))
        with_trailers = sum(1 for r in accessible if r.get("trailers"))

        data["governance"] = {
            "repos": len(accessible),
            "charters": total_charters,
            "functions": total_functions,
            "issues": total_issues,
            "hooks_installed": with_hooks,
            "trailers_flowing": with_trailers,
        }

    # Trailer intelligence: override events, significance distribution, governed commits
    data["override_events"] = []
    data["significance_distribution"] = {}
    data["governed_commits"] = {}
    if data["fleet_status"]:
        accessible = [r for r in data["fleet_status"] if r.get("accessible")]
        try:
            ov, sig, gov_c = _collect_trailer_intelligence(accessible, since_days)
            data["override_events"] = ov
            data["significance_distribution"] = sig
            data["governed_commits"] = gov_c
        except Exception as e:
            data["_errors"] = data.get("_errors", []) + [
                f"trailer intelligence: {type(e).__name__}: {e}"
            ]

    # Recent decisions — read from the committed summary layer
    # (.gator/sessions/). Scans both the command post AND fleet repos'
    # .gator/sessions/ directories; fleet repos produce commit summaries
    # automatically via the post-commit hook. The raw-vendor-logs fallback
    # retired in Phase 3 (2026-08-13); base Gator no longer parses vendor
    # transcripts. Enterprise transcripts-first substrate is the source of
    # truth for full transcript custody.
    committed_decisions = []
    sessions_dirs = []
    sessions_dirs_tagged = []  # (dir, source_kind)
    try:
        from gator_core import find_command_post, parse_registry, normalize_path
        cp = find_command_post()
        if cp:
            cp_sessions = cp / ".gator" / "sessions"
            if cp_sessions.is_dir():
                sessions_dirs.append(cp_sessions)
                sessions_dirs_tagged.append((cp_sessions, "command-post"))
            # Also scan fleet repos' .gator/sessions/
            for repo in parse_registry(cp):
                repo_path = Path(normalize_path(repo["path"]))
                repo_sessions = repo_path / ".gator" / "sessions"
                if repo_sessions.is_dir():
                    sessions_dirs.append(repo_sessions)
                    sessions_dirs_tagged.append((repo_sessions, "local-repo"))
                elif repo.get("remote") and repo["remote"] != "—":
                    # Remote fallback: read sessions from bare cache
                    try:
                        from gator_remote import (
                            ensure_cache, list_committed_sessions_remote,
                            read_session_summary_remote, CACHE_DIR, _cache_key,
                        )
                        cache_path = CACHE_DIR / _cache_key(repo["name"], repo["remote"])
                        if cache_path.is_dir() or ensure_cache(repo["name"], repo["remote"]):
                            remote_sessions = list_committed_sessions_remote(cache_path)
                            if remote_sessions:
                                # Store for later processing
                                if not hasattr(data, "_remote_sessions"):
                                    data["_remote_sessions"] = []
                                data["_remote_sessions"].append({
                                    "repo": repo["name"],
                                    "cache_path": cache_path,
                                    "files": remote_sessions,
                                })
                    except ImportError:
                        pass
    except ImportError:
        pass

    has_committed = any(
        any(d.glob("*.md")) for d in sessions_dirs
    ) if sessions_dirs else False
    has_remote_sessions = bool(data.get("_remote_sessions"))

    if has_committed or has_remote_sessions:
        data["decisions_source"] = "committed"
        data["decisions_dirs"] = len(sessions_dirs)
        committed_decisions, summary_items = _committed_decisions_from_snippets(
            reader_mod, sessions_dirs_tagged, has_remote_sessions, data, since_days
        )
        data["session_summaries"] = summary_items[:50]

    # Sort by timestamp, most recent first, cap at 15
    committed_decisions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    data["decisions"] = committed_decisions[:15]

    return data


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Session Summary Mode
# ---------------------------------------------------------------------------

def _handle_sessions(args):
    """Handle --sessions mode: aggregate and display session summaries."""
    aggregator = _import_script("gator-session-aggregator")

    if args.fleet:
        summaries = aggregator.get_fleet_summaries(force_refresh=args.refresh)
    else:
        repo_root = find_gator_root()
        if not repo_root:
            print("error: not inside a gator-governed repo", file=sys.stderr)
            sys.exit(1)
        summaries = aggregator.get_session_summaries(
            str(repo_root), force_refresh=args.refresh
        )

    if args.json:
        print(json.dumps(summaries, indent=2, default=str))
    else:
        print(_render_sessions_text(summaries, fleet=args.fleet))


def _render_sessions_text(summaries, fleet=False):
    """Render session summaries as terminal text."""
    if not summaries:
        return "  No sessions found."

    # In fleet mode, group by repo first, then by started_at descending within each repo
    if fleet:
        summaries = sorted(summaries, key=lambda s: (
            s.get("repo", ""),
            # Negate time for descending sort within repo — use reverse string trick
            s.get("started_at", ""),
        ))
        # Re-sort: group by repo, within each repo sort by started_at descending
        from itertools import groupby
        grouped = []
        for repo, group in groupby(summaries, key=lambda s: s.get("repo", "")):
            grouped.extend(sorted(group, key=lambda s: s.get("started_at", ""), reverse=True))
        summaries = grouped

    lines = []
    current_repo = None

    for s in summaries:
        # In fleet mode, group by repo
        if fleet and s.get("repo") != current_repo:
            current_repo = s.get("repo", "?")
            if lines:
                lines.append("")
            lines.append(f"  Sessions for {current_repo}")
            lines.append("")

        # Date range
        started = s.get("started_at", "")[:16].replace("T", " ")
        ended = s.get("ended_at", "")[11:16]  # just HH:MM
        if started and ended:
            date_range = f"{started}\u2013{ended}"
        else:
            date_range = started or "?"

        model = s.get("model", "?")
        count = s.get("commit_count", 0)
        sig = s.get("significance", "routine")

        lines.append(f"    {date_range}  {model}  {count} commits  {sig}")

        goal = s.get("goal")
        if goal:
            lines.append(f"      Goal: {goal}")

        tags = s.get("decision_tags", [])
        if tags:
            lines.append(f"      Tags: {', '.join(tags[:8])}")

        commits = s.get("commits", [])
        for c in commits:
            short = c.get("short_commit", "?")
            ct = c.get("change_type", "")
            intent = c.get("intent", "")
            lines.append(f"      {short} {ct}  {intent}")

        lines.append("")

    return "\n".join(lines)


def main():
    ensure_utf8_stdout()

    parser = argparse.ArgumentParser(
        description="Gator audit — fleet governance dashboard."
    )
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--html", action="store_true", help="Generate HTML dashboard")
    parser.add_argument("--open", "-o", action="store_true", help="Open HTML in browser (with --html)")
    parser.add_argument("--since", "-s", default="7d", help="Lookback period for sessions (e.g., 7d, 30d)")
    parser.add_argument("--output", help="Output file path (default: stdout or audit-report.html)")
    parser.add_argument("--sessions", action="store_true", help="Show session summaries (aggregated from snippets)")
    parser.add_argument("--fleet", action="store_true", help="Show sessions across all registered repos (with --sessions)")
    parser.add_argument("--refresh", action="store_true", help="Force regeneration of cached session summaries (with --sessions)")
    args = parser.parse_args()

    # Reject --fleet and --refresh without --sessions
    if (args.fleet or args.refresh) and not args.sessions:
        parser.error("--fleet and --refresh require --sessions")

    # Session summary mode — separate path from the full audit
    if args.sessions:
        _handle_sessions(args)
        return

    # Parse since
    import re
    since_days = 7
    match = re.match(r'^(\d+)\s*d$', args.since.lower())
    if match:
        since_days = int(match.group(1))

    # Assemble
    data = assemble_audit_data(since_days=since_days)

    if args.json:
        print(json.dumps(data, indent=2, default=str))

    elif args.html:
        html = render_html(data)
        output_path = args.output or "audit-report.html"
        Path(output_path).write_text(html, encoding="utf-8")
        print(f"  Audit dashboard written to: {output_path}")
        if args.open:
            webbrowser.open(f"file://{Path(output_path).resolve()}")
            print(f"  Opened in browser.")

    else:
        print(render_text(data))


if __name__ == "__main__":
    main()
