"""Policy drift finding model — deterministic comparison results."""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class PolicyDriftFinding(Base, TimestampMixin):
    __tablename__ = "policy_drift_findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policies.id"), nullable=False
    )
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policy_versions.id"), nullable=False
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id"), nullable=False
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id"), nullable=False
    )
    check_name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="charter_required, status_json_required, trailers_required",
    )
    severity: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="aligned, drift",
    )
    expected: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    observed: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_drift_findings_unique",
            "policy_version_id", "repository_id", "commit_id", "check_name",
            unique=True,
        ),
    )
