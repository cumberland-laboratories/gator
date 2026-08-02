"""Repository model — tracked repositories from provider integrations."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("git_providers.id"), nullable=False
    )
    provider_repo_id: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="Provider's numeric/string repo ID",
    )
    canonical_identifier: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="e.g. github.com/cumberland-laboratories/test-repo",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str] = mapped_column(
        String(200), nullable=False, default="main"
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_webhook_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_commit_sha: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    hook_mode: Mapped[str] = mapped_column(
        String(50), nullable=False, default="evidence_only",
        comment="Hook enforcement mode: evidence_only, warning, strict, off",
    )

    __table_args__ = (
        Index("ix_repositories_provider_repo", "provider_id", "provider_repo_id", unique=True),
        Index("ix_repositories_canonical", "canonical_identifier"),
    )
