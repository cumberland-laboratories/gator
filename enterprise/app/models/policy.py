"""Policy and PolicyVersion models.

Policies are the central control-plane objects. Versions are immutable
once created — content and content_hash never change. Active version
is tracked via is_active boolean with a partial unique index.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class Policy(Base, TimestampMixin):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="URL-safe identifier, unique per org",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft",
        comment="draft, active",
    )

    __table_args__ = (
        Index("ix_policies_org_slug", "organization_id", "slug", unique=True),
    )


class PolicyVersion(Base, TimestampMixin):
    __tablename__ = "policy_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policies.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment="Governance config payload — immutable after creation",
    )
    content_hash: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="SHA-256 of canonical JSON serialization",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="Whether this is the currently active version",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_token_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_tokens.id"), nullable=True
    )

    __table_args__ = (
        Index("ix_policy_versions_policy_number", "policy_id", "version_number", unique=True),
        # One active version per policy. sqlite_where added 2026-08-21
        # (Phase 5): without it, SQLite create_all IGNORES the
        # postgresql_where clause and degrades this to a FULL unique index
        # on policy_id — any second version 500s in the in-memory test
        # environment. Pre-existing latent limitation; surfaced by the
        # first multi-version tests (test_policy_state.py). Production
        # Postgres schema is unchanged.
        Index("ix_policy_versions_active", "policy_id", unique=True,
              postgresql_where=(is_active == True),
              sqlite_where=(is_active == True)),
    )
