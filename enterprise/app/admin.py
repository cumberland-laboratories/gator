"""Local admin CLI commands for Gator Enterprise.

Usage:
    python -m app.admin bootstrap

This is infrastructure administration, not an API route.
Designed for customer-hosted / air-gapped environments.
"""

import secrets
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.auth import hash_token
from app.config import get_settings
from app.db import SessionLocal
from app.models.api_token import ApiToken
from app.models.audit_log import AdminAuditLog
from app.models.organization import Organization


def bootstrap():
    """Create the first admin token and default organization.

    Prints the raw token to stdout exactly once.
    Refuses to run if a bootstrap token already exists.
    """
    settings = get_settings()
    db = SessionLocal()

    try:
        # Check if bootstrap token already exists
        existing = db.execute(
            select(ApiToken).where(ApiToken.label == "bootstrap-admin")
        ).scalar_one_or_none()

        if existing is not None:
            print("ERROR: Bootstrap token already exists.", file=sys.stderr)
            print("This command can only be run once.", file=sys.stderr)
            sys.exit(1)

        # Create default organization if none exists
        org = db.execute(select(Organization)).scalars().first()
        if org is None:
            org = Organization(
                name="Default Organization",
                slug="default",
            )
            db.add(org)
            db.flush()

        # Generate and store token
        raw_token = secrets.token_urlsafe(32)
        token_record = ApiToken(
            organization_id=org.id,
            token_hash=hash_token(raw_token),
            label="bootstrap-admin",
            scopes=None,  # full admin
        )
        db.add(token_record)

        # Audit log
        db.add(AdminAuditLog(
            organization_id=org.id,
            actor_token_id=None,
            action="token.bootstrap",
            detail={"label": "bootstrap-admin", "method": "cli"},
        ))

        db.commit()

        # Print token to stdout — this is the only time it's visible
        print(raw_token)

    finally:
        db.close()


def register_provider():
    """Register a new provider integration.

    Usage:
        python -m app.admin register-provider --type github --config '{"app_id": "...", "installation_id": "..."}'
    """
    import json as json_mod

    # Parse args
    provider_type = None
    config_json = None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--type" and i + 1 < len(args):
            provider_type = args[i + 1]
            i += 2
        elif args[i] == "--config" and i + 1 < len(args):
            config_json = args[i + 1]
            i += 2
        else:
            i += 1

    if not provider_type:
        print("ERROR: --type required (e.g. github)", file=sys.stderr)
        sys.exit(1)
    if not config_json:
        print("ERROR: --config required (JSON blob)", file=sys.stderr)
        sys.exit(1)

    try:
        config = json_mod.loads(config_json)
    except json_mod.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in --config: {e}", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        # Get or create default org
        org = db.execute(select(Organization)).scalars().first()
        if org is None:
            print("ERROR: no organization exists. Run 'bootstrap' first.", file=sys.stderr)
            sys.exit(1)

        from app.models.git_provider import GitProvider
        provider = GitProvider(
            organization_id=org.id,
            provider_type=provider_type,
            config=config,
            status="active",
        )
        db.add(provider)

        # Audit log
        db.add(AdminAuditLog(
            organization_id=org.id,
            actor_token_id=None,
            action="provider.register",
            detail={"provider_type": provider_type, "config_keys": list(config.keys())},
        ))
        db.commit()

        print(f"Provider registered: {provider.id} (type={provider_type})")

        # Immediate repo inventory sync
        print("Running initial repo inventory sync...")
        from app.services.sync import sync_repo_inventory
        try:
            sync_repo_inventory(db, provider)
            from app.models.repository import Repository
            repos = db.execute(
                select(Repository).where(Repository.provider_id == provider.id)
            ).scalars().all()
            print(f"Repos discovered: {len(repos)}")
            for r in repos:
                print(f"  - {r.canonical_identifier} ({r.default_branch})")
        except Exception as e:
            print(f"WARNING: inventory sync failed: {e}", file=sys.stderr)
            print("Provider was registered. You can retry sync manually.", file=sys.stderr)

    finally:
        db.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.admin <command>", file=sys.stderr)
        print("Commands: bootstrap, register-provider", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    if command == "bootstrap":
        bootstrap()
    elif command == "register-provider":
        register_provider()
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
