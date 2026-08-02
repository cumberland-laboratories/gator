"""Report snapshot model — materialized report output."""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class ReportSnapshot(Base, TimestampMixin):
    __tablename__ = "report_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_runs.id"), nullable=False
    )
    snapshot_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="repo_governance, policy_compliance",
    )
    scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="SHA-256 of canonical JSON",
    )
