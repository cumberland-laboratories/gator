"""providers commands — list (from org overview), reconcile."""

from gator_enterprise_cli.output import print_json, print_table


def register(subparsers):
    """Register providers subcommands."""
    prov_parser = subparsers.add_parser("providers", help="Provider management")
    prov_sub = prov_parser.add_subparsers(dest="providers_command")

    prov_sub.add_parser("list", help="List registered providers")

    reconcile = prov_sub.add_parser("reconcile", help="Trigger full provider reconciliation")
    reconcile.add_argument("provider_id", help="Provider UUID")


def handle(args, client):
    """Handle providers commands."""
    if args.providers_command == "list":
        # Providers are exposed via the org overview endpoint
        data = client.get("/api/v1/views/org")
        providers = data.get("providers", [])
        if args.json:
            print_json(providers)
        else:
            rows = [
                [
                    p["id"][:8],
                    p["type"],
                    p["status"],
                    str(p.get("repos_tracked", 0)),
                    p.get("last_sync", "—") or "—",
                ]
                for p in providers
            ]
            print_table(["ID", "Type", "Status", "Repos", "Last Sync"], rows)

    elif args.providers_command == "reconcile":
        data = client.post(f"/api/v1/providers/{args.provider_id}/reconcile")
        if args.json:
            print_json(data)
        else:
            print(f"Reconciliation complete: {data.get('provider_id', args.provider_id)}")
