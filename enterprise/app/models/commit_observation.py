"""Commit observation model — structured governance facts extracted from a commit."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class CommitObservation(Base, TimestampMixin):
    __tablename__ = "commit_observations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id"), unique=True, nullable=False,
        comment="One observation per commit",
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id"), nullable=False
    )
    status_json_present: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status_json_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    charter_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    charter_names: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    constitution_present: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    trailers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Parsed governance trailers from commit message",
    )
    observation_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending",
        comment="pending, observed, failed",
    )
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
