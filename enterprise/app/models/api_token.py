"""API token model — hashed access tokens for service authentication."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class ApiToken(Base, TimestampMixin):
    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False,
        comment="SHA-256 hex digest of the raw token",
    )
    label: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Human-readable label, e.g. 'bootstrap-admin' or 'ci-service'",
    )
    scopes: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Permitted scopes, null means full admin",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
