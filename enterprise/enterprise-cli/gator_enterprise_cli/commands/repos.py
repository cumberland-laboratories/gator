"""repos commands — list, refresh, policies, transcripts (Q5).

Q5 audit-question surface (`repos transcripts <id>`) ratified as R5 = (b)
at Phase 1 exit. Answers "Which model/vendor sessions touched repo <repo>
over time?" via `GET /api/v1/repos/{repo_canonical_id}/transcripts` — see
`enterprise/app/routes/repos.py::list_repo_transcripts`.
"""

import sys

from gator_enterprise_cli.output import print_json, print_kv, print_table


def register(subparsers):
    """Register repos subcommands."""
    repos_parser = subparsers.add_parser("repos", help="Repository management + audit")
    repos_sub = repos_parser.add_subparsers(dest="repos_command")

    repos_sub.add_parser("list", help="List tracked repositories")

    refresh = repos_sub.add_parser("refresh", help="Trigger manual repo refresh")
    refresh.add_argument("repo_id", help="Repository UUID")

    policies = repos_sub.add_parser("policies", help="List policies targeting a repo")
    policies.add_argument("repo_id", help="Repository UUID")

    transcripts = repos_sub.add_parser(
        "transcripts",
        help="Transcript sessions that touched this repo, ordered by recency (Q5)",
    )
    transcripts.add_argument(
        "repo_canonical_id",
        help="Canonical repo identifier (e.g. 'local/gator')",
    )
    transcripts.add_argument("--vendor", default=None,
        help="Optional vendor filter (e.g. anthropic, openai, google)")
    transcripts.add_argument("--since", default=None,
        help="ISO 8601 lower bound on started_at (accepts YYYY-MM-DD)")
    transcripts.add_argument("--limit", type=int, default=50)
    transcripts.add_argument("--offset", type=int, default=0,
        help="Pagination offset")


def handle(args, client):
    """Handle repos commands."""
    if args.repos_command == "list":
        data = client.get("/api/v1/repos")
        if args.json:
            print_json(data)
        else:
            rows = [
                [
                    r["id"][:8],
                    r["name"],
                    r["default_branch"],
                    "active" if r["active"] else "inactive",
                    r.get("last_commit_sha", "—")[:8] if r.get("last_commit_sha") else "—",
                ]
                for r in data
            ]
            print_table(["ID", "Name", "Branch", "Status", "Last SHA"], rows)

    elif args.repos_command == "refresh":
        data = client.post(f"/api/v1/repos/{args.repo_id}/refresh")
        if args.json:
            print_json(data)
        else:
            print(f"Refresh started: {data.get('repo', args.repo_id)}")

    elif args.repos_command == "policies":
        data = client.get(f"/api/v1/repos/{args.repo_id}/policies")
        if args.json:
            print_json(data)
        else:
            rows = [
                [
                    p.get("policy_id", "—")[:8],
                    p.get("name", "—"),
                    p.get("status", "—"),
                    p.get("rollout_status", "—"),
                ]
                for p in data
            ]
            print_table(["ID", "Name", "Status", "Rollout"], rows)

    elif args.repos_command == "transcripts":
        _handle_transcripts(args, client)

    else:
        print(
            "Usage: gator-enterprise repos {list,refresh,policies,transcripts} ...",
            file=sys.stderr,
        )
        sys.exit(2)


def _handle_transcripts(args, client):
    """Q5 — list transcript sessions that touched a repo over time."""
    params: dict = {"limit": args.limit, "offset": args.offset}
    if args.vendor:
        params["vendor"] = args.vendor
    if args.since:
        params["since"] = args.since
    data = client.get(
        f"/api/v1/repos/{args.repo_canonical_id}/transcripts",
        params=params,
    )
    if args.json:
        print_json(data)
        return

    items = data.get("items", [])
    if not items:
        print(f"No transcript sessions found for repo {args.repo_canonical_id}.")
        return

    rows = [
        [
            item["id"][:8],
            item["vendor"],
            item.get("model") or "-",
            (item.get("vendor_session_id") or "")[:12],
            (item.get("started_at") or "")[:19] or "-",
            (item.get("machine_id") or "")[:8],
            str(item.get("blob_size_bytes") or 0),
        ]
        for item in items
    ]
    print_table(
        ["Transcript", "Vendor", "Model", "SessionID", "Started", "Machine", "Bytes"],
        rows,
    )

    pagination = data.get("pagination", {})
    if pagination.get("has_more"):
        print("\n(more results — increase --limit or paginate with --offset)")
