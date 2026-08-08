"""Transcript session — Enterprise-first evidence custody.

One row per distinct vendor AI session that Enterprise has ingested
from a client machine. The transcript BODY lives in the BlobStore
(referenced by `blob_key`); this table stores only metadata.

Populated by `POST /api/v1/transcripts/ingest` (per the 2026-08-08
transcripts-first MVP plan). Idempotent by
`(organization_id, machine_id, vendor, vendor_session_id)` — re-ingest
of the same session upserts the row and refreshes the blob.

TRANSITIONAL NOTE (per plan D2): base-gator's SessionStart hook writes
`<repo>/.gator/active-vendor-session.json` with the same vendor_session_id
values consumed here. Post-MVP, that capture moves to Enterprise and
the ingestion source shifts from repo-local files to Enterprise-owned
machine-scope state without changing this table's shape.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class TranscriptSession(Base, TimestampMixin):
    __tablename__ = "transcript_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False,
    )
    machine_id: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Gator machine identifier from ~/.gator/machine-id",
    )
    vendor: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="Canonical vendor slug: 'anthropic' | 'openai' | 'google' | ...",
    )
    vendor_session_id: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Opaque per-vendor session identifier",
    )
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workspace_hint: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="cwd or workspace root at session capture time",
    )
    transcript_source_path: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Original path of the transcript on the client machine",
    )
    blob_key: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Namespaced key into the BlobStore where the transcript body is persisted",
    )
    blob_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
        comment="Payload size in bytes for retention/quota reporting",
    )
    blob_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="SHA-256 hex of the raw (pre-compression) payload for integrity",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="Last time this session was updated in Enterprise (on re-ingest)",
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="When Enterprise first recorded this transcript session",
    )
    retention_class: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default",
        comment="Retention policy class; enforcement is post-MVP",
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "machine_id", "vendor", "vendor_session_id",
            name="uq_transcript_sessions_org_machine_vendor_session",
        ),
        Index(
            "ix_transcript_sessions_org_machine",
            "organization_id", "machine_id",
        ),
        Index(
            "ix_transcript_sessions_vendor_session",
            "vendor", "vendor_session_id",
        ),
    )
