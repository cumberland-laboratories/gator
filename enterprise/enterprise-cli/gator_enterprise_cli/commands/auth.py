"""auth commands — token identity and connectivity check."""

from gator_enterprise_cli.output import print_json, print_kv


def register(subparsers):
    """Register auth subcommands."""
    auth_parser = subparsers.add_parser("auth", help="Authentication commands")
    auth_sub = auth_parser.add_subparsers(dest="auth_command")
    auth_sub.add_parser("whoami", help="Show current token identity")


def handle(args, client):
    """Handle auth commands."""
    if args.auth_command == "whoami":
        data = client.get("/api/v1/tokens/me")
        if args.json:
            print_json(data)
        else:
            print_kv([
                ("Label", data.get("label", "—")),
                ("Scopes", str(data.get("scopes", "full admin"))),
                ("Last used", data.get("last_used_at", "—")),
                ("Expires", data.get("expires_at", "never")),
            ])
