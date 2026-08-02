"""Commit evidence block — session block metadata index.

For the repo-first model (E7), this table indexes session blocks that
live in Git as .gator/session-blocks/*.json.gz. Enterprise does not store
the transcript payload — it reads on demand from bare clones. This table
stores metadata for fast lookups, fleet reporting, and integrity verification.

The encrypted_payload and encryption_key_id columns are preserved for a
future encryption phase but unused in E7.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class CommitEvidenceBlock(Base, TimestampMixin):
    __tablename__ = "commit_evidence_blocks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), nullable=False
    )
    block_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Evidence type: session_block, charter_snapshot, review_record, etc.",
    )

    # Session block index fields (E7)
    artifact_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment=".gator/session-blocks/<stem>.json.gz",
    )
    indexed_from_ref: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Bare branch name where block was discovered. Upgraded to default branch on merge.",
    )
    target_commit_sha: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="Commit SHA this block describes (from target_commit in payload)",
    )
    capture_quality: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="exact, best_effort, partial, missing_head, missing_tail",
    )
    vendor: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="anthropic, openai, google, unknown",
    )
    turn_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    plaintext_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Encryption metadata (E8)
    encryption_mode: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="plaintext or aes-256-gcm",
    )
    org_key_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Which org key encrypted this block",
    )
    origin_machine_key_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Which machine key is a recipient",
    )

    # Preserved for potential future use
    encrypted_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    encryption_key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Integrity
    content_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="SHA-256 hash of plaintext content for integrity verification",
    )
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        Index("ix_evidence_blocks_commit_id", "commit_id"),
    )
