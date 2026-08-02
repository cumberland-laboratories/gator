"""policies commands — list, get."""

from gator_enterprise_cli.output import print_json, print_kv, print_table


def register(subparsers):
    """Register policies subcommands."""
    pol_parser = subparsers.add_parser("policies", help="Policy management")
    pol_sub = pol_parser.add_subparsers(dest="policies_command")

    pol_sub.add_parser("list", help="List all policies")

    get = pol_sub.add_parser("get", help="Get policy detail")
    get.add_argument("policy_id", help="Policy UUID")


def handle(args, client):
    """Handle policies commands."""
    if args.policies_command == "list":
        data = client.get("/api/v1/policies")
        if args.json:
            print_json(data)
        else:
            rows = [
                [
                    p["id"][:8],
                    p["name"],
                    p["slug"],
                    p["status"],
                    str(p.get("version_count", 0)),
                ]
                for p in data
            ]
            print_table(["ID", "Name", "Slug", "Status", "Versions"], rows)

    elif args.policies_command == "get":
        data = client.get(f"/api/v1/policies/{args.policy_id}")
        if args.json:
            print_json(data)
        else:
            av = data.get("active_version")
            print_kv([
                ("ID", data["id"]),
                ("Name", data["name"]),
                ("Slug", data["slug"]),
                ("Status", data["status"]),
                ("Versions", str(data.get("version_count", 0))),
                ("Active version", f"v{av['version_number']} ({av['content_hash'][:12]})" if av else "none"),
                ("Created", data.get("created_at", "—")),
            ])
