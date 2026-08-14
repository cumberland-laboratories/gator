"""commits commands — reverse-lookup for the transcript custody surface.

`commits transcripts <sha>` is the operator's answer to "what AI
sessions produced this commit?" — the primary evidence path in the
2026-08-08 transcripts-first MVP. Backed by
`GET /api/v1/commits/{sha}/transcripts` from `routes/transcripts.py`.

(Verb-first arg order — `commits transcripts <sha>`, not `commits <sha>
transcripts` — because argparse resolves subcommand groups before
positionals. The API URL keeps `{sha}` mid-path; only the CLI shape
differs from the URL shape.)
"""

from __future__ import annotations

import sys

from gator_enterprise_cli.output import print_json, print_table


def register(subparsers):
    parser = subparsers.add_parser(
        "commits",
        help="Reverse-lookup commit → transcript sessions",
    )
    sub = parser.add_subparsers(dest="commits_command")

    show = sub.add_parser(
        "transcripts",
        help="List transcripts linked to a commit SHA",
    )
    show.add_argument("commit_sha", help="Commit SHA (7-40 hex chars)")
    show.add_argument(
        "--repo", default=None,
        help="Optional repo_canonical_id scope for ambiguous SHAs",
    )


def handle(args, client):
    if args.commits_command == "transcripts":
        _handle_transcripts(args, client)
    else:
        print("Usage: gator-enterprise commits transcripts <sha> [--repo <id>]", file=sys.stderr)
        sys.exit(2)


def _handle_transcripts(args, client):
    params = {}
    if args.repo:
        params["repo_canonical_id"] = args.repo
    data = client.get(
        f"/api/v1/commits/{args.commit_sha}/transcripts",
        params=params or None,
    )
    if args.json:
        print_json(data)
        return

    commits = data.get("commits", [])
    print(f"Commit matches ({len(commits)}):")
    for c in commits:
        print(f"  {c['commit_sha'][:12]}  {c['repo_identifier']}")

    links = data.get("links", [])
    if not links:
        print("\nNo linked transcripts.")
        return

    print("\nLinked transcripts:")
    rows = [
        [
            link["commit_sha"][:12],
            link["transcript_session_id"][:8],
            link["vendor"],
            (link.get("vendor_session_id") or "")[:12],
            link.get("model") or "-",
            link["linkage_basis"],
            link["linkage_confidence"],
        ]
        for link in links
    ]
    print_table(
        ["Commit", "Transcript", "Vendor", "SessionID", "Model", "Basis", "Confidence"],
        rows,
    )
