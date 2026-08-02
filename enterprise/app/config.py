"""Gator Enterprise configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    app_env: str = "dev"
    port: int = 8000
    worker_poll_interval: int = 5  # seconds
    reconciliation_interval: int = 3600  # seconds (default 60 min)

    # GitHub App integration (all optional — empty = not configured)
    github_app_id: str = ""
    github_private_key: str = ""  # PEM content via Fly secret
    github_webhook_secret: str = ""

    # Bare clone cache for reading repo files
    clone_cache_dir: str = "/var/lib/gator-enterprise/clones"

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    return Settings()
