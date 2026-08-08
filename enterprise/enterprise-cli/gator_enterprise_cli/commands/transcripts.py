"""transcripts commands — pull (ingest), list.

`transcripts pull` is the primary operator entry point for MVP evidence
custody (2026-08-08 transcripts-first plan §10):

  1. Discover commits from known gatorized repos on this machine
     (~/.gator/dashboard-repos.json + git log + .gator/session-snippets/)
  2. POST /api/v1/commits/ingest with the batch
  3. Discover vendor transcripts (MVP: Claude Code only)
  4. POST /api/v1/transcripts/ingest for each transcript — server-side
     linkage runs immediately

`transcripts list` is the minimum operator-query surface needed to
verify the exit criteria of Phase 2 (item ingested → visible).
`show`/`get`/`link`/`relink` land in Phase 3-4.
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from gator_enterprise_cli.output import print_json, print_kv, print_table
from gator_enterprise_cli.transcripts_discovery import (
    DiscoveredTranscript,
    discover as discover_transcripts,
)


# --- Constants ---

_DASHBOARD_REPOS = Path(os.path.expanduser("~/.gator/dashboard-repos.json"))
_MACHINE_ID_FILE = Path(os.path.expanduser("~/.gator/machine-id"))
# Cap the number of commits pulled per repo per invocation. The Enterprise
# ingest endpoint accepts arbitrary batches; this is a client-side sanity
# cap so a repo with 50k commits doesn't produce a 30MB payload.
_DEFAULT_COMMITS_PER_REPO = 500
# Cap raw content size read into memory per transcript. 50MB is generous
# for real Claude Code sessions (largest observed on this machine: ~8MB);
# above the cap we skip with a warning instead of OOMing.
_MAX_CONTENT_BYTES = 50 * 1024 * 1024


def register(subparsers):
    parser = subparsers.add_parser(
        "transcripts",
        help="Transcript ingestion + query (MVP: Claude Code)",
    )
    sub = parser.add_subparsers(dest="transcripts_command")

    pull = sub.add_parser(
        "pull",
        help="Discover local vendor transcripts + governed commits, upload to Enterprise",
    )
    pull.add_argument(
        "--vendor", default="claude",
        choices=["claude", "anthropic", "all"],
        help="Vendor to pull from (default: claude). MVP supports only claude.",
    )
    pull.add_argument(
        "--since", default=None,
        help="ISO 8601 lower bound on transcript timestamps (e.g. 2026-08-01)",
    )
    pull.add_argument("--dry-run", action="store_true", help="Discover but don't upload")
    pull.add_argument("--limit", type=int, default=0, help="Max transcripts to upload (0 = no cap)")
    pull.add_argument(
        "--force-relink", action="store_true",
        help="Re-upload sessions already ingested (regenerates linkage)",
    )
    pull.add_argument(
        "--no-compress", action="store_true",
        help="Send raw content instead of gzip-encoded (larger payload; default is gzip)",
    )
    pull.add_argument(
        "--commits-per-repo", type=int, default=_DEFAULT_COMMITS_PER_REPO,
        help=f"Cap commits per repo per invocation (default: {_DEFAULT_COMMITS_PER_REPO})",
    )

    ls = sub.add_parser("list", help="List ingested transcript sessions")
    ls.add_argument("--vendor", default=None)
    ls.add_argument("--machine-id", default=None)
    ls.add_argument("--since", default=None)
    ls.add_argument("--limit", type=int, default=50)


def handle(args, client):
    if args.transcripts_command == "pull":
        _handle_pull(args, client)
    elif args.transcripts_command == "list":
        _handle_list(args, client)
    else:
        print("Usage: gator-enterprise transcripts {pull,list}", file=sys.stderr)
        sys.exit(2)


# ----------------------------------------------------------------------
# transcripts list
# ----------------------------------------------------------------------


def _handle_list(args, client):
    params: dict = {"limit": args.limit}
    if args.vendor:
        params["vendor"] = args.vendor
    if args.machine_id:
        params["machine_id"] = args.machine_id
    if args.since:
        params["since"] = args.since
    data = client.get("/api/v1/transcripts", params=params)
    if args.json:
        print_json(data)
        return
    items = data.get("items", [])
    rows = [
        [
            item["id"][:8],
            item["vendor"],
            (item.get("vendor_session_id") or "")[:12],
            item.get("model") or "—",
            (item.get("ingested_at") or "")[:19],
            str(item.get("blob_size_bytes") or 0),
            str(item.get("linked_commit_count") or 0),
        ]
        for item in items
    ]
    print_table(
        ["ID", "Vendor", "SessionID", "Model", "Ingested", "Bytes", "Links"],
        rows,
    )
    pagination = data.get("pagination", {})
    if pagination.get("has_more"):
        print(f"\n(more results — increase --limit or use --json to page)")


# ----------------------------------------------------------------------
# transcripts pull
# ----------------------------------------------------------------------


def _handle_pull(args, client):
    if args.vendor == "all":
        vendor = "claude"
        print("note: --vendor all resolves to claude in MVP (only vendor supported)")
    else:
        vendor = args.vendor

    since_dt = _parse_iso(args.since)
    machine_id = _read_machine_id()

    # Step 1 + 2 — commit discovery + ingest.
    repos = _read_dashboard_repos()
    commit_batch, snippet_hint_count = _build_commit_batch(
        repos, machine_id=machine_id, per_repo_cap=args.commits_per_repo,
    )

    print(f"Discovered {len(commit_batch)} commits across {len(repos)} repos "
          f"({snippet_hint_count} with snippet linkage hints)")

    if args.dry_run:
        print("(dry-run: skipping commits/ingest POST)")
        commits_ingested_result = None
    else:
        if commit_batch:
            commit_payload = {
                "machine_id": machine_id,
                "commits": [_item_dict(item) for item in commit_batch],
            }
            resp = client.post("/api/v1/commits/ingest", json=commit_payload)
            commits_ingested_result = resp
            statuses = _tally_statuses(resp.get("commits_ingested", []))
            print(f"Commits ingested: {statuses}")
        else:
            commits_ingested_result = None
            print("No commits to ingest.")

    # Step 3 + 4 — transcript discovery + ingest.
    discovered = list(discover_transcripts(vendor, since=since_dt))
    print(f"Discovered {len(discovered)} {vendor} transcripts")

    if args.limit and len(discovered) > args.limit:
        print(f"Applying --limit {args.limit} (skipping {len(discovered) - args.limit} discovered transcripts)")
        discovered = discovered[: args.limit]

    linkage_totals: dict[str, int] = {}
    transcripts_ingested = 0
    transcripts_updated = 0
    transcripts_failed: list[tuple[str, str]] = []

    if args.dry_run:
        for record in discovered:
            _print_discovered(record)
        print("(dry-run: skipping transcripts/ingest POST)")
    else:
        for record in discovered:
            try:
                result = _upload_transcript(
                    client, record,
                    machine_id=machine_id,
                    compress=not args.no_compress,
                )
            except _TranscriptSkip as skip:
                transcripts_failed.append((record.vendor_session_id, str(skip)))
                print(f"  skip {record.vendor_session_id[:12]}  {skip}")
                continue
            except Exception as e:  # noqa: BLE001 — network + FS + decode
                transcripts_failed.append((record.vendor_session_id, repr(e)))
                print(f"  error {record.vendor_session_id[:12]}  {e}")
                continue
            if result.get("status") == "created":
                transcripts_ingested += 1
            else:
                transcripts_updated += 1
            for link in result.get("commits_linked", []):
                basis = link.get("linkage_basis", "unknown")
                linkage_totals[basis] = linkage_totals.get(basis, 0) + 1
            print(
                f"  ok   {record.vendor_session_id[:12]}  "
                f"-> {result['transcript_session_id'][:8]}  "
                f"status={result['status']}  "
                f"linked={len(result.get('commits_linked', []))}"
            )

    # Summary
    print()
    print("Pull summary")
    print("=" * 40)
    print_kv([
        ("machine_id", machine_id or "(none)"),
        ("vendor", vendor),
        ("commits discovered", str(len(commit_batch))),
        ("transcripts discovered", str(len(discovered))),
        ("transcripts ingested (new)", str(transcripts_ingested)),
        ("transcripts updated", str(transcripts_updated)),
        ("transcripts failed", str(len(transcripts_failed))),
        ("links by basis", json.dumps(linkage_totals) if linkage_totals else "{}"),
    ])
    if transcripts_failed:
        print("\nFailures:")
        for sid, reason in transcripts_failed:
            print(f"  {sid[:12]}  {reason}")

    if args.json:
        print_json({
            "machine_id": machine_id,
            "vendor": vendor,
            "commits_ingested": commits_ingested_result,
            "transcripts_ingested_new": transcripts_ingested,
            "transcripts_updated": transcripts_updated,
            "transcripts_failed": [
                {"vendor_session_id": sid, "reason": reason}
                for sid, reason in transcripts_failed
            ],
            "linkage_totals": linkage_totals,
        })


class _TranscriptSkip(Exception):
    """Discovered transcript should be skipped (non-fatal to the pull)."""


def _upload_transcript(
    client,
    record: DiscoveredTranscript,
    *,
    machine_id: str | None,
    compress: bool,
) -> dict:
    """Read a transcript file, base64-encode (optionally gzip), POST."""
    source = Path(record.source_path)
    try:
        raw = source.read_bytes()
    except OSError as e:
        raise _TranscriptSkip(f"read failed: {e}")
    if len(raw) > _MAX_CONTENT_BYTES:
        raise _TranscriptSkip(
            f"content {len(raw)} bytes exceeds cap {_MAX_CONTENT_BYTES}",
        )

    if compress:
        payload_bytes = gzip.compress(raw)
        encoding = "gzip"
    else:
        payload_bytes = raw
        encoding = "raw"

    payload = {
        "machine_id": machine_id or "unknown",
        "vendor": record.vendor,
        "vendor_session_id": record.vendor_session_id,
        "model": record.model,
        "workspace_hint": record.workspace_hint,
        "transcript_source_path": record.source_path,
        "started_at": _iso(record.started_at),
        "ended_at": _iso(record.ended_at),
        "content_encoding": encoding,
        "content": base64.b64encode(payload_bytes).decode("ascii"),
    }
    return client.post("/api/v1/transcripts/ingest", json=payload)


def _print_discovered(record: DiscoveredTranscript) -> None:
    print(
        f"  {record.vendor_session_id[:12]}  "
        f"model={record.model or '?'}  "
        f"start={_iso(record.started_at) or '?'}  "
        f"end={_iso(record.ended_at) or '?'}  "
        f"turns={record.turn_count}  "
        f"bytes={record.file_size_bytes}"
    )
    if record.parse_error:
        print(f"    parse_error: {record.parse_error}")


# ----------------------------------------------------------------------
# Commit + repo discovery
# ----------------------------------------------------------------------


class _CommitItem:
    __slots__ = (
        "repo_canonical_id", "sha", "subject", "author", "committed_at",
        "branch", "gator_trailers", "transcript_session_id", "machine_id",
        "machine_label", "snippet_agent",
    )

    def __init__(self, **kw):
        for slot in self.__slots__:
            setattr(self, slot, kw.get(slot))


def _item_dict(item: _CommitItem) -> dict:
    out = {}
    for slot in item.__slots__:
        v = getattr(item, slot)
        if v is None:
            continue
        out[slot] = v
    return out


def _read_dashboard_repos() -> list[dict]:
    if not _DASHBOARD_REPOS.exists():
        print(f"warning: {_DASHBOARD_REPOS} not found — no repos to scan for commits",
              file=sys.stderr)
        return []
    try:
        data = json.loads(_DASHBOARD_REPOS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"warning: failed to read {_DASHBOARD_REPOS}: {e}", file=sys.stderr)
        return []
    if isinstance(data, dict):
        return data.get("repos", [])
    if isinstance(data, list):
        return data
    return []


def _read_machine_id() -> str | None:
    if not _MACHINE_ID_FILE.exists():
        return None
    try:
        for line in _MACHINE_ID_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("id:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def _build_commit_batch(
    repos: list[dict],
    *,
    machine_id: str | None,
    per_repo_cap: int,
) -> tuple[list[_CommitItem], int]:
    """Extract commit metadata + snippet linkage hints from each repo.

    Returns (batch, snippet_hint_count) where snippet_hint_count counts
    commits that got a `transcript_session_id` from a snippet.
    """
    batch: list[_CommitItem] = []
    hint_count = 0

    for repo in repos:
        path = repo.get("path")
        if not path or not Path(path).exists():
            continue
        # Build canonical id — for MVP we use the same 'local/<basename>'
        # convention as the sandbox repo (see inbox.md).
        name = repo.get("name") or Path(path).name
        canonical_id = f"local/{name}"

        # Snippet-side hints: commit_sha → transcript_session_id
        snippet_hints = _load_snippet_hints(Path(path))

        for commit in _iter_recent_commits(Path(path), limit=per_repo_cap):
            snippet_hint = snippet_hints.get(commit["sha"])
            item = _CommitItem(
                repo_canonical_id=canonical_id,
                sha=commit["sha"],
                subject=commit.get("subject"),
                author=commit.get("author"),
                committed_at=commit.get("committed_at"),
                branch=commit.get("branch"),
                gator_trailers=commit.get("gator_trailers"),
                transcript_session_id=(
                    snippet_hint.get("transcript_session_id") if snippet_hint else None
                ),
                machine_id=(snippet_hint.get("machine_id") if snippet_hint else None) or machine_id,
                machine_label=snippet_hint.get("machine_label") if snippet_hint else None,
                snippet_agent=snippet_hint.get("agent") if snippet_hint else None,
            )
            if item.transcript_session_id:
                hint_count += 1
            batch.append(item)

    return batch, hint_count


def _iter_recent_commits(repo_path: Path, limit: int):
    """git log — subject + author + committed_at + branch for the last `limit` commits."""
    fmt = "%H%x1f%s%x1f%an <%ae>%x1f%aI"
    try:
        result = subprocess.run(
            ["git", "log", "-n", str(limit), f"--pretty=format:{fmt}"],
            cwd=str(repo_path),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"warning: git log failed on {repo_path}: {e}", file=sys.stderr)
        return
    if result.returncode != 0:
        return

    branch = _current_branch(repo_path)

    for line in result.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) < 4:
            continue
        sha, subject, author, committed_at = parts[0], parts[1], parts[2], parts[3]
        yield {
            "sha": sha,
            "subject": subject,
            "author": author,
            "committed_at": committed_at,
            "branch": branch,
        }


def _current_branch(repo_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_path),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch if branch and branch != "HEAD" else None


def _load_snippet_hints(repo_path: Path) -> dict[str, dict]:
    """Read .gator/session-snippets/*.json and index by commit SHA."""
    snippet_dir = repo_path / ".gator" / "session-snippets"
    if not snippet_dir.exists() or not snippet_dir.is_dir():
        return {}
    hints: dict[str, dict] = {}
    for entry in snippet_dir.iterdir():
        if not entry.is_file() or entry.suffix != ".json":
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sha = data.get("commit")
        if not sha:
            continue
        # If multiple snippets reference the same commit (unlikely but
        # possible with multi-session pool + hook races), the last one
        # wins — snippet_dir.iterdir is arbitrary order.
        hints[sha] = data
    return hints


# ----------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        # Accept bare dates (YYYY-MM-DD).
        if len(normalized) == 10 and normalized[4] == "-":
            normalized = normalized + "T00:00:00+00:00"
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _tally_statuses(rows: list[dict]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for row in rows:
        status = row.get("status", "unknown")
        tally[status] = tally.get(status, 0) + 1
    return tally
