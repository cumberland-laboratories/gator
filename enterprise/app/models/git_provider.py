"""Git provider model — registered provider integrations."""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class GitProvider(Base, TimestampMixin):
    __tablename__ = "git_providers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    provider_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="github, azure_devops, bitbucket",
    )
    config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Provider-specific config: {app_id, installation_id, ...}",
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active",
        comment="active, disabled",
    )
