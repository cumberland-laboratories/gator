"""repos commands — list, refresh, policies."""

from gator_enterprise_cli.output import print_json, print_kv, print_table


def register(subparsers):
    """Register repos subcommands."""
    repos_parser = subparsers.add_parser("repos", help="Repository management")
    repos_sub = repos_parser.add_subparsers(dest="repos_command")

    repos_sub.add_parser("list", help="List tracked repositories")

    refresh = repos_sub.add_parser("refresh", help="Trigger manual repo refresh")
    refresh.add_argument("repo_id", help="Repository UUID")

    policies = repos_sub.add_parser("policies", help="List policies targeting a repo")
    policies.add_argument("repo_id", help="Repository UUID")


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
