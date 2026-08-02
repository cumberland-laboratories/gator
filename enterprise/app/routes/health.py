"""Health and readiness endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import VERSION
from app.config import get_settings
from app.db import get_db

router = APIRouter()
settings = get_settings()


@router.get("/healthz")
def health():
    """Basic liveness check."""
    return {
        "status": "ok",
        "version": VERSION,
        "env": settings.app_env,
    }


@router.get("/readyz")
def ready(db: Session = Depends(get_db)):
    """Readiness check — verifies database connectivity. Returns 503 if DB is unreachable."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unreachable"},
        )
