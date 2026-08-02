"""Admin audit log — records administrative actions."""

import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class AdminAuditLog(Base, TimestampMixin):
    __tablename__ = "admin_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    actor_token_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_tokens.id"), nullable=True,
        comment="Token that performed the action, null for system/bootstrap actions",
    )
    action: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="Action identifier, e.g. 'token.bootstrap', 'org.create'",
    )
    detail: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Structured detail about the action",
    )

    __table_args__ = (
        Index("ix_audit_log_org_created", "organization_id", "created_at"),
    )
