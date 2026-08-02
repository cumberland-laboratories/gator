"""reports commands — runs."""

from gator_enterprise_cli.output import print_json, print_table


def register(subparsers):
    """Register reports subcommands."""
    rep_parser = subparsers.add_parser("reports", help="Report management")
    rep_sub = rep_parser.add_subparsers(dest="reports_command")

    rep_sub.add_parser("runs", help="List recent report runs")


def handle(args, client):
    """Handle reports commands."""
    if args.reports_command == "runs":
        data = client.get("/api/v1/reports/runs")
        if args.json:
            print_json(data)
        else:
            rows = [
                [
                    r["id"][:8],
                    r["run_type"],
                    r.get("scope", "—") or "—",
                    r["status"],
                    r.get("started_at", "—"),
                ]
                for r in data
            ]
            print_table(["ID", "Type", "Scope", "Status", "Started"], rows)
