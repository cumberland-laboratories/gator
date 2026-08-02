# Gator Enterprise

Git-commit-driven evidence and forensic reconstruction for AI-assisted software development.

## Prerequisites

- Python 3.11+
- [flyctl](https://fly.io/docs/flyctl/install/) installed and authenticated
- Access to the Cumberland Fly.io organization

## Local Development

```bash
cd enterprise
pip install -r requirements.txt

# Point at Fly dev database (via proxy or direct URL)
export DATABASE_URL=postgresql://...

# Run migrations
alembic upgrade head

# Bootstrap first admin token (prints token to stdout)
python -m app.admin bootstrap

# Start API
uvicorn app.main:app --reload --port 8000

# Start worker (separate terminal)
python -m app.worker
```

## Fly.io Deployment

### First-Time Setup

```bash
cd enterprise

# Create app
fly apps create gator-enterprise-dev

# Create and attach Postgres
fly postgres create --name gator-enterprise-dev-db --region iad
fly postgres attach gator-enterprise-dev-db -a gator-enterprise-dev

# Deploy
fly deploy
```

### Bootstrap Admin Token (Remote)

```bash
fly ssh console -a gator-enterprise-dev -C "python -m app.admin bootstrap"
```

Save the printed token securely. It cannot be retrieved again.

### Verify

```bash
# Health check
curl https://gator-enterprise-dev.fly.dev/healthz

# Auth test (use token from bootstrap)
curl -H "Authorization: Bearer <token>" https://gator-enterprise-dev.fly.dev/api/v1/tokens/me
```

### Subsequent Deploys

```bash
cd enterprise
fly deploy
```

Migrations run automatically via `release_command` on every deploy.

## Secrets Inventory

| Secret | Source | Notes |
|--------|--------|-------|
| `DATABASE_URL` | Auto-attached by `fly postgres attach` | No manual setup needed |

No other Fly secrets are required for E1. The bootstrap token is generated on the host via CLI, not injected as an environment variable.

## Architecture

```
┌─────────────────────────────────────┐
│           Fly.io (iad)              │
│                                     │
│  ┌─────────┐     ┌──────────────┐  │
│  │   API   │     │    Worker    │  │
│  │ (web)   │     │ (background) │  │
│  └────┬────┘     └──────┬───────┘  │
│       │                  │          │
│       └──────┬───────────┘          │
│              │                      │
│       ┌──────┴──────┐              │
│       │  PostgreSQL  │              │
│       └─────────────┘              │
└─────────────────────────────────────┘
```

## Windows / Git Bash Caveats

- `flyctl` interactive prompts may not work in Git Bash. Use `--yes` flags or switch to PowerShell for app creation commands.
- When setting secrets with special characters, use PowerShell or escape carefully.
- `fly ssh console` works in Git Bash but may need `winpty` prefix for interactive sessions.

## Process Overview

- **API**: Serves authenticated JSON API. Health checks at `/healthz` and `/readyz`.
- **Worker**: Polls `ingest_jobs` table, processes commit metadata registration.
- **Migrations**: Run via Alembic on every deploy (`release_command`).
- **Bootstrap**: Local CLI command creates first admin token. Runs once per environment.
