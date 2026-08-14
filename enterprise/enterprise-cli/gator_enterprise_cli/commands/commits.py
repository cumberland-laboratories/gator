"""commits commands — reverse-lookup + provenance + repo-scoped list.

Audit-question surfaces this module owns (see 2026-08-14 audit-question
surface artifact §3):

- ``commits transcripts <sha>`` — Q1 ("Which transcripts are linked to
  commit <sha>?"). Verb-first arg order (positional SHA after the verb)
  because argparse resolves subcommand groups before positionals.
- ``commits list --repo <id>`` — Q2 ("Which recent commits in repo <repo>
  have transcript coverage?"). Ratified as R4 = (a) at Phase 1 exit.
- ``commits provenance <sha>`` — Q4 ("Which machine produced commit
  <sha>?"). Ratified as R3 = (i) at Phase 1 exit.
"""

from __future__ import annotations

import sys

from gator_enterprise_cli.output import print_json, print_kv, print_table


def register(subparsers):
    parser = subparsers.add_parser(
        "commits",
        help="Commit-side audit-question surfaces",
    )
    sub = parser.add_subparsers(dest="commits_command")

    show = sub.add_parser(
        "transcripts",
        help="List transcripts linked to a commit SHA (Q1)",
    )
    show.add_argument("commit_sha", help="Commit SHA (7-40 hex chars)")
    show.add_argument(
        "--repo", default=None,
        help="Optional repo_canonical_id scope for ambiguous SHAs",
    )

    ls = sub.add_parser(
        "list",
        help="Recent commits in a repo with transcript coverage summary (Q2)",
    )
    ls.add_argument(
        "--repo", required=True,
        help="Canonical repo identifier (e.g. 'local/gator') — REQUIRED",
    )
    ls.add_argument("--limit", type=int, default=50)
    ls.add_argument("--offset", type=int, default=0, help="Pagination offset")

    prov = sub.add_parser(
        "provenance",
        help="Commit-side provenance: machine, agent, snippet linkage (Q4)",
    )
    prov.add_argument("commit_sha", help="Commit SHA (7-40 hex chars)")
    prov.add_argument(
        "--repo", default=None,
        help="Optional repo_canonical_id scope for ambiguous SHAs",
    )


def handle(args, client):
    if args.commits_command == "transcripts":
        _handle_transcripts(args, client)
    elif args.commits_command == "list":
        _handle_list(args, client)
    elif args.commits_command == "provenance":
        _handle_provenance(args, client)
    else:
        print(
            "Usage: gator-enterprise commits {transcripts,list,provenance} ...",
            file=sys.stderr,
        )
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


# ----------------------------------------------------------------------
# commits list (Q2)
# ----------------------------------------------------------------------


def _handle_list(args, client):
    params: dict = {"limit": args.limit, "offset": args.offset}
    data = client.get(
        f"/api/v1/repos/{args.repo}/commits",
        params=params,
    )
    if args.json:
        print_json(data)
        return

    items = data.get("items", [])
    if not items:
        print(f"No commits in repo {args.repo}.")
        return

    rows = [
        [
            item["commit_sha"][:12],
            (item.get("committed_at") or "")[:19] or "-",
            (item.get("author_identity") or "")[:30],
            (item.get("machine_id") or "")[:8],
            str(item.get("linked_transcript_count") or 0),
            item.get("best_linkage_basis_ranked") or "-",
        ]
        for item in items
    ]
    print_table(
        ["Commit", "CommittedAt", "Author", "Machine", "Transcripts", "BestBasis"],
        rows,
    )

    pagination = data.get("pagination", {})
    total = pagination.get("total_matched")
    if pagination.get("has_more"):
        shown = len(items) + pagination.get("offset", 0)
        print(
            f"\n(showing {shown}/{total} — increase --limit or paginate with --offset)"
        )
    elif total is not None and total > 0:
        print(f"\n({total} commits matched)")


# ----------------------------------------------------------------------
# commits provenance (Q4)
# ----------------------------------------------------------------------


def _handle_provenance(args, client):
    params = {}
    if args.repo:
        params["repo_canonical_id"] = args.repo
    data = client.get(
        f"/api/v1/commits/{args.commit_sha}/provenance",
        params=params or None,
    )
    if args.json:
        print_json(data)
        return

    commits = data.get("commits", [])
    if not commits:
        print(f"No commits match SHA prefix {args.commit_sha!r}.")
        return

    if len(commits) > 1:
        # Ambiguous SHA — print a compact one-line-per-commit table so
        # the operator can disambiguate with --repo.
        print(f"Multiple commits match SHA prefix {args.commit_sha!r} ({len(commits)}):")
        rows = [
            [
                c["commit_sha"][:12],
                c["repo_identifier"],
                (c.get("committed_at") or "")[:19] or "-",
                (c.get("machine_label") or c.get("machine_id") or "-")[:20],
                c.get("snippet_agent") or "-",
            ]
            for c in commits
        ]
        print_table(
            ["Commit", "Repo", "CommittedAt", "Machine", "Agent"],
            rows,
        )
        print("\nUse --repo <canonical-id> to disambiguate.")
        return

    # Single-match — print full provenance detail.
    c = commits[0]
    print_kv([
        ("commit_sha", c["commit_sha"]),
        ("repo_identifier", c["repo_identifier"]),
        ("committed_at", c.get("committed_at") or "(none)"),
        ("author_identity", c.get("author_identity") or "(none)"),
        ("machine_id", c.get("machine_id") or "(none)"),
        ("machine_label", c.get("machine_label") or "(none)"),
        ("snippet_agent", c.get("snippet_agent") or "(none — human-only commit or missing snippet)"),
        ("transcript_session_id", c.get("transcript_session_id") or "(none)"),
    ])
