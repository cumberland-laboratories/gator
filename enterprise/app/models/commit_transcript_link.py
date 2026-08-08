"""Commit ↔ transcript session linkage.

Many-to-many between the `commits` evidence anchor and
`transcript_sessions`. Every row records WHY the link exists via
`linkage_basis`, so audit consumers can distinguish hard matches
(commit SHA appears verbatim in transcript) from inferred matches
(same machine, same repo, overlapping time).

The `linkage_basis` vocabulary is a string column (not a DB enum)
so post-MVP additions don't require a migration. MVP-supported values:

- ``"exact_sha_in_transcript"`` — commit SHA appears verbatim in
  transcript content (highest confidence)
- ``"session_id_in_snippet"`` — commit's snippet-recorded
  ``transcript_session_id`` matches this session's
  ``vendor_session_id``
- ``"strong_machine_repo_time"`` — same machine_id + same
  repo_identifier + overlapping timestamps + same vendor
- ``"orchestrator_declared"`` — explicit link via API/CLI

Weak-heuristic basis values (``strong_machine_workspace``,
``weak_machine_time``) are deferred post-MVP but the schema tolerates
them without change.

TRIPWIRE: any addition/change to the vocabulary must be reflected in
the API docs, the CLI help text for `gator-enterprise transcripts
link`, and the operator query documentation. There is no DB-level
check constraint on the values by design (evolvability > enforceability
at this layer).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_uuid


class CommitTranscriptLink(Base):
    __tablename__ = "commit_transcript_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False,
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), nullable=False,
    )
    transcript_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcript_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    linkage_basis: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="Why this link exists — see module docstring for MVP vocabulary",
    )
    linkage_confidence: Mapped[str] = mapped_column(
        String(16), nullable=False,
        comment="'high' | 'medium' | 'low' — coarse audit-facing confidence",
    )
    linkage_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment="Debug info, matched fields, timestamps — free-form per linkage_basis",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "commit_id", "transcript_session_id", "linkage_basis",
            name="uq_ctl_commit_session_basis",
        ),
        Index("ix_ctl_commit", "commit_id"),
        Index("ix_ctl_transcript", "transcript_session_id"),
    )
