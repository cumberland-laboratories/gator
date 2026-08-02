"""Provider sync run model — operator debugging for sync operations."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class ProviderSyncRun(Base, TimestampMixin):
    __tablename__ = "provider_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("git_providers.id"), nullable=False
    )
    run_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="webhook, reconciliation, manual",
    )
    scope: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="What was targeted (repo id, 'all', etc.)",
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="started",
        comment="started, completed, failed",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    commits_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
