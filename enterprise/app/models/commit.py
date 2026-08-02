"""Commit model — the primary evidence anchor.

This is the architectural declaration: Gator Enterprise is organized
around Git commits. Every piece of evidence, attribution, and
reconstruction pivots on this boundary.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class Commit(Base, TimestampMixin):
    __tablename__ = "commits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    repo_identifier: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="Canonical repo identifier, e.g. 'github.com/org/repo'",
    )
    commit_sha: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="Full 40-char hex SHA",
    )
    author_identity: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Human author identity string from commit metadata",
    )
    model_identities: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="AI models involved in producing this commit, as structured metadata",
    )
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp from the commit itself",
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="When Enterprise first recorded this commit",
    )

    # Machine identity + AI attribution (populated from snippet during reconciliation)
    machine_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Gator machine identifier from snippet machine_id field",
    )
    machine_label: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Human-readable machine name from snippet machine_label field",
    )
    snippet_agent: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="AI agent from snippet. Null = human-only commit. Key discriminator for pending block detection.",
    )

    __table_args__ = (
        Index("ix_commits_org_repo_sha", "organization_id", "repo_identifier", "commit_sha", unique=True),
        Index("ix_commits_org_machine", "organization_id", "machine_id"),
    )
