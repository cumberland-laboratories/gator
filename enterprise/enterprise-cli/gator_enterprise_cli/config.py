"""CLI configuration — resolves host and token from env vars."""

import os
import sys
from dataclasses import dataclass


@dataclass
class CliConfig:
    """Enterprise CLI configuration."""
    base_url: str
    token: str

    @classmethod
    def load(cls, url_override: str | None = None, token_override: str | None = None) -> "CliConfig":
        """Load config from flags > env vars.

        Precedence: flags > env vars. Config file support is intentionally
        deferred — env vars are sufficient for MVP and match the repo's
        existing CLI patterns (gator CLI, admin.py).

        Required:
            GATOR_ENTERPRISE_URL — base URL of the Enterprise API
            GATOR_ENTERPRISE_TOKEN — API bearer token
        """
        base_url = url_override or os.environ.get("GATOR_ENTERPRISE_URL", "")
        token = token_override or os.environ.get("GATOR_ENTERPRISE_TOKEN", "")

        if not base_url:
            print("Error: GATOR_ENTERPRISE_URL is required (set via env var or --url flag)", file=sys.stderr)
            sys.exit(1)

        if not token:
            print("Error: GATOR_ENTERPRISE_TOKEN is required (set via env var or --token flag)", file=sys.stderr)
            sys.exit(1)

        # Normalize: strip trailing slash
        base_url = base_url.rstrip("/")

        return cls(base_url=base_url, token=token)
