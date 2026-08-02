"""Policy rollout model — tracks intended application of a policy version to a repo.

State machine:
  pending → applied | failed | superseded
  applied → outdated (when a newer version is activated)

Non-terminal states (pending, applied): at most one per (policy_id, repository_id).
Terminal states (superseded, failed, outdated): historical, never modified.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class PolicyRollout(Base, TimestampMixin):
    __tablename__ = "policy_rollouts"

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
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending",
        comment="pending, applied, outdated, failed, superseded",
    )
    source: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="activation, retarget, manual",
    )
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_rollouts_policy_repo_status", "policy_id", "repository_id", "status"),
    )
