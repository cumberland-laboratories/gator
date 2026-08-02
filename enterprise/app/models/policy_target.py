"""Policy target model — maps policies to repositories."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class PolicyTarget(Base, TimestampMixin):
    __tablename__ = "policy_targets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policies.id"), nullable=False
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_policy_targets_policy_repo", "policy_id", "repository_id", unique=True),
    )
