"""transcripts commands — pull (ingest), list, show, get, link, relink.

`transcripts pull` is the primary operator entry point for evidence
custody (2026-08-08 transcripts-first plan §10):

  1. Discover commits from known gatorized repos on this machine
     (~/.gator/dashboard-repos.json + git log + .gator/session-snippets/)
  2. POST /api/v1/commits/ingest with the batch
  3. Discover vendor transcripts — Claude Code (`--vendor claude`),
     Codex CLI (`codex`), Gemini CLI (`gemini`), or `all` (audit-surface
     tranche Phases 3+4, 2026-08-15)
  4. POST /api/v1/transcripts/ingest for each transcript — server-side
     linkage runs immediately

`transcripts list` is the minimum operator-query surface needed to
verify item-ingested → visible; `show`/`get`/`link`/`relink` are the
per-transcript query + explicit-linkage verbs.
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
    claude_root_path,
    codex_root_path,
    discover as discover_transcripts,
    gemini_root_path,
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
        help="Transcript ingestion + query (Claude Code, Codex, Gemini)",
    )
    sub = parser.add_subparsers(dest="transcripts_command")

    pull = sub.add_parser(
        "pull",
        help="Discover local vendor transcripts + governed commits, upload to Enterprise",
    )
    pull.add_argument(
        "--vendor", default="claude",
        choices=["claude", "anthropic", "codex", "openai", "gemini", "google", "all"],
        help=(
            "Vendor to pull from (default: claude). Phase 3 (2026-08-15) added "
            "Codex ('codex'/'openai' → `~/.codex/sessions/`); Phase 4 "
            "(2026-08-15) added Gemini ('gemini'/'google' → `~/.gemini/tmp/`). "
            "'anthropic' remains an alias for 'claude'. 'all' still resolves "
            "to claude in this release; iterating across all installed "
            "vendors is Phase 5+ work."
        ),
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
    ls.add_argument("--since", default=None,
        help="ISO 8601 lower bound on started_at (accepts YYYY-MM-DD)")
    ls.add_argument("--until", default=None,
        help="ISO 8601 upper bound on started_at (accepts YYYY-MM-DD)")
    ls.add_argument("--limit", type=int, default=50)
    ls.add_argument("--offset", type=int, default=0,
        help="Pagination offset (default: 0)")
    ls.add_argument("--unlinked", action="store_true",
        help="Show only sessions with zero linked commits (server-side filter)")
    ls.add_argument("--sort", default="ingested",
        choices=["ingested", "started", "size", "links"],
        help="Sort key (default: ingested, descending)")
    ls.add_argument("--wide", action="store_true",
        help="Show additional columns (machine_id short, started_at)")

    show = sub.add_parser("show", help="Show a transcript session's metadata + links")
    show.add_argument("transcript_id", help="Transcript session UUID (full or 8-char prefix)")

    get = sub.add_parser("get", help="Fetch a transcript's raw blob content")
    get.add_argument("transcript_id", help="Transcript session UUID")
    get.add_argument(
        "--output", "-o", default="-",
        help="Output path (default: stdout as '-')",
    )

    link = sub.add_parser("link", help="Explicit orchestrator-declared linkage")
    link.add_argument("transcript_id", help="Transcript session UUID")
    link.add_argument("--commit", required=True, help="Commit SHA (7-40 hex chars)")
    link.add_argument("--repo", default=None,
        help="Optional repo_canonical_id scope for ambiguous SHAs")
    link.add_argument("--basis", default="orchestrator_declared",
        help="linkage_basis value (default: orchestrator_declared)")
    link.add_argument("--confidence", default="high",
        choices=["high", "medium", "low"])
    link.add_argument("--metadata", default=None,
        help="JSON object merged into linkage_metadata")

    relink = sub.add_parser(
        "relink",
        help="Re-run the ingest-time linkage algorithm on an existing transcript",
    )
    relink.add_argument("transcript_id", help="Transcript session UUID")


def handle(args, client):
    if args.transcripts_command == "pull":
        _handle_pull(args, client)
    elif args.transcripts_command == "list":
        _handle_list(args, client)
    elif args.transcripts_command == "show":
        _handle_show(args, client)
    elif args.transcripts_command == "get":
        _handle_get(args, client)
    elif args.transcripts_command == "link":
        _handle_link(args, client)
    elif args.transcripts_command == "relink":
        _handle_relink(args, client)
    else:
        print(
            "Usage: gator-enterprise transcripts {pull,list,show,get,link,relink}",
            file=sys.stderr,
        )
        sys.exit(2)


# ----------------------------------------------------------------------
# transcripts list
# ----------------------------------------------------------------------


_SORT_KEYS = {
    "ingested": ("ingested_at", True),   # (field, descending)
    "started":  ("started_at", True),
    "size":     ("blob_size_bytes", True),
    "links":    ("linked_commit_count", True),
}


def _handle_list(args, client):
    params: dict = {"limit": args.limit, "offset": args.offset}
    if args.vendor:
        params["vendor"] = args.vendor
    if args.machine_id:
        params["machine_id"] = args.machine_id
    if args.since:
        params["since"] = args.since
    if args.until:
        params["until"] = args.until
    if args.unlinked:
        # Server-side filter (Phase 2 Q3 promotion, 2026-08-14). Earlier
        # MVP versions of the CLI did the filter client-side because the
        # server had no `unlinked=true` param; the server-side param was
        # added in the same commit as this CLI change. On the off chance
        # a caller runs a new CLI against an older server that doesn't
        # honor the param, the extra client-side filter below covers the
        # gap (defensive, cheap, no-op on new servers).
        params["unlinked"] = "true"
    data = client.get("/api/v1/transcripts", params=params)
    if args.json:
        print_json(data)
        return

    items = data.get("items", [])
    if args.unlinked:
        # Defensive client-side filter — see comment on the params block
        # above. On a matching server, the items list already excludes
        # linked sessions and this filter is a no-op.
        items = [item for item in items if not (item.get("linked_commit_count") or 0)]

    # Client-side sort — the API returns `ingested_at DESC` by default,
    # so `--sort ingested` is a no-op. Other keys re-sort in memory.
    if args.sort != "ingested":
        field, descending = _SORT_KEYS[args.sort]
        items = sorted(
            items,
            key=lambda item: (item.get(field) is None, item.get(field) or 0),
            reverse=descending,
        )

    if args.wide:
        headers = ["ID", "Vendor", "SessionID", "Model", "Machine",
                   "Started", "Ingested", "Bytes", "Links"]
        rows = [
            [
                item["id"][:8],
                item["vendor"],
                (item.get("vendor_session_id") or "")[:12],
                item.get("model") or "-",
                (item.get("machine_id") or "")[:8],
                (item.get("started_at") or "")[:19] or "-",
                (item.get("ingested_at") or "")[:19],
                str(item.get("blob_size_bytes") or 0),
                str(item.get("linked_commit_count") or 0),
            ]
            for item in items
        ]
    else:
        headers = ["ID", "Vendor", "SessionID", "Model", "Ingested", "Bytes", "Links"]
        rows = [
            [
                item["id"][:8],
                item["vendor"],
                (item.get("vendor_session_id") or "")[:12],
                item.get("model") or "-",
                (item.get("ingested_at") or "")[:19],
                str(item.get("blob_size_bytes") or 0),
                str(item.get("linked_commit_count") or 0),
            ]
            for item in items
        ]
    print_table(headers, rows)

    # Summary line: per-vendor breakdown when there are >= 2 vendors visible.
    vendors = {}
    for item in items:
        v = item["vendor"]
        vendors[v] = vendors.get(v, 0) + 1
    if len(vendors) > 1:
        summary = ", ".join(f"{v}={n}" for v, n in sorted(vendors.items()))
        print(f"\nBy vendor: {summary}")

    pagination = data.get("pagination", {})
    if pagination.get("has_more"):
        print(f"\n(more results -- increase --limit or paginate with --offset)")


# ----------------------------------------------------------------------
# transcripts show
# ----------------------------------------------------------------------


def _handle_show(args, client):
    tid = _resolve_transcript_id(args.transcript_id, client)
    data = client.get(f"/api/v1/transcripts/{tid}")
    if args.json:
        print_json(data)
        return
    print_kv([
        ("id", data["id"]),
        ("vendor", data["vendor"]),
        ("vendor_session_id", data["vendor_session_id"]),
        ("machine_id", data["machine_id"]),
        ("model", data.get("model") or "(none)"),
        ("workspace_hint", data.get("workspace_hint") or "(none)"),
        ("started_at", data.get("started_at") or "(none)"),
        ("ended_at", data.get("ended_at") or "(none)"),
        ("ingested_at", data.get("ingested_at") or "(none)"),
        ("blob_key", data["blob_key"]),
        ("blob_size_bytes", str(data.get("blob_size_bytes") or 0)),
        ("blob_sha256", data["blob_sha256"]),
        ("retention_class", data["retention_class"]),
        ("linked_commit_count", str(data.get("linked_commit_count") or 0)),
    ])
    links = data.get("links", [])
    if links:
        print("\nLinks:")
        rows = [
            [
                link["commit_sha"][:12],
                link["linkage_basis"],
                link["linkage_confidence"],
                (link.get("created_at") or "")[:19],
            ]
            for link in links
        ]
        print_table(["Commit SHA", "Basis", "Confidence", "Created"], rows)


# ----------------------------------------------------------------------
# transcripts get
# ----------------------------------------------------------------------


def _handle_get(args, client):
    tid = _resolve_transcript_id(args.transcript_id, client)
    # httpx returns parsed JSON on 2xx; the blob endpoint returns raw
    # bytes with application/x-ndjson media type. Reach through the
    # client's session to get the raw response.
    import httpx  # local import — keeps CLI startup light
    url = f"{client._base}/api/v1/transcripts/{tid}/blob"  # noqa: SLF001
    try:
        resp = httpx.get(url, headers=client._headers, timeout=120.0)  # noqa: SLF001
    except httpx.ConnectError:
        from gator_enterprise_cli.client import CliError
        raise CliError(f"Connection failed: {client._base}")
    if resp.status_code != 200:
        from gator_enterprise_cli.client import CliError
        raise CliError(f"Error ({resp.status_code}): {resp.text[:200]}")

    if args.output == "-":
        # Binary safe write to stdout on Windows too
        sys.stdout.buffer.write(resp.content)
    else:
        out = Path(args.output)
        out.write_bytes(resp.content)
        sha = resp.headers.get("x-blob-sha256", "")
        print(f"Wrote {len(resp.content)} bytes to {out}")
        if sha:
            print(f"blob_sha256: {sha}")


# ----------------------------------------------------------------------
# transcripts link
# ----------------------------------------------------------------------


def _handle_link(args, client):
    tid = _resolve_transcript_id(args.transcript_id, client)
    metadata = None
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError as e:
            print(f"error: --metadata is not valid JSON: {e}", file=sys.stderr)
            sys.exit(2)
        if not isinstance(metadata, dict):
            print("error: --metadata must be a JSON object", file=sys.stderr)
            sys.exit(2)
    body = {
        "commit_sha": args.commit,
        "linkage_basis": args.basis,
        "linkage_confidence": args.confidence,
    }
    if args.repo:
        body["repo_canonical_id"] = args.repo
    if metadata is not None:
        body["linkage_metadata"] = metadata

    data = client.post(f"/api/v1/transcripts/{tid}/link", json=body)
    if args.json:
        print_json(data)
        return
    print(
        f"{data['status']}: link {data['link_id'][:8]}  "
        f"commit={data['commit_sha'][:12]}  "
        f"basis={data['linkage_basis']}  "
        f"confidence={data['linkage_confidence']}"
    )


# ----------------------------------------------------------------------
# transcripts relink
# ----------------------------------------------------------------------


def _handle_relink(args, client):
    tid = _resolve_transcript_id(args.transcript_id, client)
    data = client.post(f"/api/v1/transcripts/{tid}/relink")
    if args.json:
        print_json(data)
        return
    links = data.get("commits_linked", [])
    print(f"Relinked transcript {tid[:8]}: {len(links)} new links")
    for link in links:
        print(f"  {link['commit_sha'][:12]}  {link['linkage_basis']}")


# ----------------------------------------------------------------------
# Prefix expansion for transcript_id
# ----------------------------------------------------------------------


def _resolve_transcript_id(supplied: str, client) -> str:
    """Accept an 8+ char prefix and expand it to a full UUID.

    Full UUIDs (36 chars with dashes) pass through untouched.
    Anything shorter is looked up via `list` and expanded if a single
    match is found; multi-match errors so the caller can disambiguate.
    """
    if len(supplied) == 36 and supplied.count("-") == 4:
        return supplied
    if len(supplied) < 8:
        print(
            f"error: transcript_id prefix must be >= 8 chars, got {len(supplied)}",
            file=sys.stderr,
        )
        sys.exit(2)
    # Page through the list looking for prefix matches. MVP: no dedicated
    # server-side prefix endpoint; scan up to `_PREFIX_SCAN_CAP` sessions.
    data = client.get("/api/v1/transcripts", params={"limit": _PREFIX_SCAN_CAP})
    matches = [
        item["id"] for item in data.get("items", [])
        if item["id"].startswith(supplied)
    ]
    if len(matches) == 0:
        print(f"error: no transcript matches prefix {supplied!r}", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(
            f"error: {len(matches)} transcripts match prefix {supplied!r}; "
            f"use the full UUID",
            file=sys.stderr,
        )
        sys.exit(1)
    return matches[0]


_PREFIX_SCAN_CAP = 200


# ----------------------------------------------------------------------
# transcripts pull
# ----------------------------------------------------------------------


def _handle_pull(args, client):
    if args.vendor == "all":
        # Phase 3 (2026-08-15): Codex adapter shipped, but --vendor all
        # still resolves to claude only — iterating across all installed
        # vendors is Phase 4+ work per parent plan §5. Operators wanting
        # Codex today invoke `--vendor codex` (or `--vendor openai`)
        # explicitly.
        vendor = "claude"
        print(
            "note: --vendor all resolves to claude in this release "
            "(iteration across installed vendors is Phase 4+)"
        )
    else:
        vendor = args.vendor

    since_dt = _parse_iso(args.since)
    machine_id = _read_machine_id()

    # Phase 2 hardening (2026-08-14): fail fast on missing machine-id
    # instead of silently uploading with machine_id="unknown". A missing
    # machine-id file means the operator hasn't run `gator init` (or an
    # equivalent that creates ~/.gator/machine-id via gator_session_reader.
    # get_machine_identity), and every transcript ingested in this state
    # would collapse into a single synthesized "unknown" machine row —
    # breaking the strong_machine_repo_time linkage basis fleet-wide.
    if not machine_id:
        print(
            f"error: no machine-id found at {_MACHINE_ID_FILE}. Run `gator init` "
            f"in any Gator-governed repo on this machine to create it, then retry. "
            f"(Without machine-id, transcript ingest cannot attribute sessions "
            f"correctly and the strong_machine_repo_time linkage basis fails.)",
            file=sys.stderr,
        )
        sys.exit(2)

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
    # Phase 2 hardening (2026-08-14): informative warning when the vendor
    # transcript root is absent, so the operator sees WHY zero transcripts
    # were discovered instead of a silent zero-item pull. Phase 3
    # (2026-08-15) extended the same pattern to Codex; `openai` is an
    # alias for `codex` per the transcripts_discovery vendor-alias table.
    if vendor in ("claude", "anthropic"):
        _claude_root = claude_root_path()
        if not _claude_root.exists() or not _claude_root.is_dir():
            print(
                f"warning: Claude transcript root {_claude_root} does not exist. "
                f"This is normal if you have not used Claude Code on this machine; "
                f"otherwise check the CLAUDE_TRANSCRIPTS_ROOT env override.",
                file=sys.stderr,
            )
    elif vendor in ("codex", "openai"):
        _codex_root = codex_root_path()
        if not _codex_root.exists() or not _codex_root.is_dir():
            print(
                f"warning: Codex transcript root {_codex_root} does not exist. "
                f"This is normal if you have not used the Codex CLI on this "
                f"machine; otherwise check the CODEX_TRANSCRIPTS_ROOT env "
                f"override.",
                file=sys.stderr,
            )
    elif vendor in ("gemini", "google"):
        _gemini_root = gemini_root_path()
        if not _gemini_root.exists() or not _gemini_root.is_dir():
            print(
                f"warning: Gemini transcript root {_gemini_root} does not exist. "
                f"This is normal if you have not used the Gemini CLI on this "
                f"machine; otherwise check the GEMINI_TRANSCRIPTS_ROOT env "
                f"override.",
                file=sys.stderr,
            )
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
            # Phase 2 hardening (2026-08-14): skip records where the file
            # itself was unreadable — attempting to upload a file we never
            # actually read would either fail at read time (redundant work)
            # or upload empty content (silently pollutes evidence). Named-
            # file diagnostic so operator can investigate the underlying
            # filesystem issue.
            if record.unreadable:
                transcripts_failed.append(
                    (record.vendor_session_id, f"unreadable: {record.parse_error}")
                )
                print(
                    f"  skip {record.vendor_session_id[:12]}  "
                    f"unreadable file {record.source_path}: {record.parse_error}",
                    file=sys.stderr,
                )
                continue
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
        # Migration 011: "" for all vendors except Gemini, whose
        # duplicate-raw-ID files carry a source-path-hash qualifier.
        "session_qualifier": record.session_qualifier,
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
