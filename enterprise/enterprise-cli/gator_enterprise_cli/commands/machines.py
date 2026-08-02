"""machines commands — list, pending."""

from gator_enterprise_cli.output import print_json, print_table


def register(subparsers):
    """Register machines subcommands."""
    machines_parser = subparsers.add_parser("machines", help="Machine management")
    machines_sub = machines_parser.add_subparsers(dest="machines_command")

    machines_sub.add_parser("list", help="List all known machines")
    machines_sub.add_parser("pending", help="List AI-assisted commits with pending session blocks")


def handle(args, client):
    """Handle machines commands."""
    if args.machines_command == "list":
        data = client.get("/api/v1/views/machines")
        if args.json:
            print_json(data)
        else:
            rows = [
                [
                    m.get("machine_id", "—"),
                    m.get("machine_label", "—") or "—",
                    str(m.get("repo_count", 0)),
                    str(m.get("commit_count", 0)),
                    m.get("last_seen", "—")[:16] if m.get("last_seen") else "—",
                ]
                for m in data.get("machines", [])
            ]
            print_table(["Machine ID", "Label", "Repos", "Commits", "Last Seen"], rows)

    elif args.machines_command == "pending":
        data = client.get("/api/v1/views/machines/pending")
        if args.json:
            print_json(data)
        else:
            pending = data.get("pending", [])
            if not pending:
                print("No pending session blocks.")
                return
            rows = [
                [
                    p.get("machine_id", "—"),
                    p.get("commit_sha", "—")[:8],
                    p.get("agent", "—"),
                    p.get("repo", "—").split("/")[-1] if p.get("repo") else "—",
                    f"{p.get('hours_pending', 0):.1f}h" if p.get("hours_pending") else "—",
                ]
                for p in pending
            ]
            print_table(["Machine", "Commit", "Agent", "Repo", "Pending"], rows)
