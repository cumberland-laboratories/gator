"""Machine key model — developer machine public keys registered during activate."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class MachineKey(Base, TimestampMixin):
    __tablename__ = "machine_keys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    machine_id: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Gator machine identifier from ~/.gator/machine-id",
    )
    machine_label: Mapped[str] = mapped_column(
        String(255), nullable=False, default="",
    )
    key_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Key identifier, e.g., machine-key-abc123",
    )
    public_key_pem: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="PEM-encoded public key. Private key stays on the machine.",
    )
    algorithm: Mapped[str] = mapped_column(
        String(50), nullable=False, default="rsa-oaep",
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "machine_id", name="uq_machine_keys_org_machine"),
    )
