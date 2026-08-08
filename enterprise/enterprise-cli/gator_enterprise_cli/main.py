"""Gator Enterprise CLI — entry point.

Usage:
    gator-enterprise [--url URL] [--token TOKEN] [--json] <command> <subcommand> [args]

Environment variables:
    GATOR_ENTERPRISE_URL    Base URL of the Enterprise API
    GATOR_ENTERPRISE_TOKEN  API bearer token
"""

import argparse
import sys

from gator_enterprise_cli import __version__
from gator_enterprise_cli.client import CliError, EnterpriseClient
from gator_enterprise_cli.config import CliConfig
from gator_enterprise_cli.commands import (
    auth, repos, providers, policies, reports, blocks, machines,
    activate, repo_init, transcripts,
)


# Commands that require Enterprise server connection
_SERVER_COMMANDS = {"auth", "repos", "providers", "policies", "reports", "blocks", "machines", "activate", "sync", "transcripts"}

# Commands that work without server connection (local-only)
_LOCAL_COMMANDS = set()  # repo init now needs server connection to register hook policy


def main():
    parser = argparse.ArgumentParser(
        prog="gator-enterprise",
        description="Gator Enterprise operator CLI",
    )
    parser.add_argument("--version", action="version", version=f"gator-enterprise {__version__}")
    parser.add_argument("--url", help="Enterprise API base URL (overrides GATOR_ENTERPRISE_URL)")
    parser.add_argument("--token", help="API token (overrides GATOR_ENTERPRISE_TOKEN)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    subparsers = parser.add_subparsers(dest="command")

    # Register command groups
    auth.register(subparsers)
    repos.register(subparsers)
    providers.register(subparsers)
    policies.register(subparsers)
    reports.register(subparsers)
    blocks.register(subparsers)
    machines.register(subparsers)
    activate.register(subparsers)  # activate + sync
    repo_init.register(subparsers)  # repo init
    transcripts.register(subparsers)  # transcripts pull + list

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Dispatch handlers
    handlers = {
        "auth": auth.handle,
        "repos": repos.handle,
        "providers": providers.handle,
        "policies": policies.handle,
        "reports": reports.handle,
        "blocks": blocks.handle,
        "machines": machines.handle,
        "activate": activate.handle,
        "sync": activate.handle,
        "repo": repo_init.handle,
        "transcripts": transcripts.handle,
    }

    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(0)

    # Local commands don't need server connection
    if args.command in _LOCAL_COMMANDS:
        try:
            handler(args, None)
        except CliError as e:
            print(f"Error: {e.message}", file=sys.stderr)
            sys.exit(e.exit_code)
        return

    # Server commands need config + client
    config = CliConfig.load(url_override=args.url, token_override=args.token)
    client = EnterpriseClient(config)

    try:
        handler(args, client)
    except CliError as e:
        print(f"Error: {e.message}", file=sys.stderr)
        sys.exit(e.exit_code)


if __name__ == "__main__":
    main()
