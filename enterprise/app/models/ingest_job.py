"""Ingest job model — worker job queue backed by Postgres."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class IngestJob(Base, TimestampMixin):
    __tablename__ = "ingest_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Job type: register_commit_metadata, etc.",
    )
    payload: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Job-specific parameters",
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending",
        comment="pending, claimed, completed, failed",
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_ingest_jobs_status", "status"),
    )
