"""Org encryption key model — asymmetric keypair for envelope encryption."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class OrgEncryptionKey(Base, TimestampMixin):
    __tablename__ = "org_encryption_keys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    key_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Human-readable key identifier, e.g., org-key-2026-07",
    )
    public_key_pem: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="PEM-encoded public key for DEK wrapping",
    )
    private_key_pem: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="PEM-encoded private key. Server-local, never exposed via API.",
    )
    algorithm: Mapped[str] = mapped_column(
        String(50), nullable=False, default="rsa-oaep",
        comment="Key wrapping algorithm: rsa-oaep or x25519",
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Only one active key per org. Old keys kept for historical decrypt.",
    )
