"""009 — Transcript custody: transcript_sessions + commit_transcript_links.

Introduces Enterprise-first transcript evidence storage per the
2026-08-08 transcripts-first MVP plan. Two new tables:

- `transcript_sessions`: one row per distinct vendor session with
  metadata + blob-storage reference (payloads themselves live in
  BlobStore, not in a DB column).
- `commit_transcript_links`: many-to-many between commits and
  transcript sessions, with explicit `linkage_basis` recording
  WHY each link exists (exact SHA match, session ID from snippet,
  strong metadata match, or orchestrator-declared).

No changes to existing tables. Phase 0 (2026-08-08) verified `commits`
already has `machine_id`, `machine_label`, `snippet_agent`,
`transcript_session_id`, and uses string `repo_identifier` (not FK
to `repositories`), so local-repo commits work without any schema
changes to the existing tables. `repositories` remains provider-only.

Revision ID: 009
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    # -----------------------------------------------------------------
    # transcript_sessions
    # -----------------------------------------------------------------
    op.create_table(
        "transcript_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "machine_id", sa.String(255), nullable=False,
            comment="Gator machine identifier from ~/.gator/machine-id",
        ),
        sa.Column(
            "vendor", sa.String(64), nullable=False,
            comment="Canonical vendor slug: 'anthropic' | 'openai' | 'google' | ...",
        ),
        sa.Column(
            "vendor_session_id", sa.String(255), nullable=False,
            comment="Opaque per-vendor session identifier",
        ),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column(
            "workspace_hint", sa.Text(), nullable=True,
            comment="cwd or workspace root at session capture time",
        ),
        sa.Column(
            "transcript_source_path", sa.Text(), nullable=True,
            comment="Original path of the transcript on the client machine",
        ),
        sa.Column(
            "blob_key", sa.Text(), nullable=False,
            comment="Namespaced key into the BlobStore where the transcript body is persisted",
        ),
        sa.Column(
            "blob_size_bytes", sa.BigInteger(), nullable=True,
            comment="Payload size in bytes for retention/quota reporting",
        ),
        sa.Column(
            "blob_sha256", sa.String(64), nullable=False,
            comment="SHA-256 hex of the raw (pre-compression) payload for integrity",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False,
            comment="Last time this session was updated in Enterprise (on re-ingest)",
        ),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
            comment="When Enterprise first recorded this transcript session",
        ),
        sa.Column(
            "retention_class", sa.String(64),
            server_default="default", nullable=False,
            comment="Retention policy class; enforcement is post-MVP",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        # Idempotency: re-ingesting the same session upserts, never duplicates
        sa.UniqueConstraint(
            "organization_id", "machine_id", "vendor", "vendor_session_id",
            name="uq_transcript_sessions_org_machine_vendor_session",
        ),
    )
    op.create_index(
        "ix_transcript_sessions_org_machine",
        "transcript_sessions",
        ["organization_id", "machine_id"],
    )
    op.create_index(
        "ix_transcript_sessions_vendor_session",
        "transcript_sessions",
        ["vendor", "vendor_session_id"],
    )

    # -----------------------------------------------------------------
    # commit_transcript_links
    # -----------------------------------------------------------------
    #
    # linkage_basis vocabulary (kept as a string column, not a DB enum,
    # so evolving the vocabulary post-MVP doesn't require a migration):
    #   - "exact_sha_in_transcript"     — commit SHA appears verbatim
    #                                     in transcript content (highest)
    #   - "session_id_in_snippet"       — commit's snippet-recorded
    #                                     transcript_session_id matches
    #                                     this session's vendor_session_id
    #   - "strong_machine_repo_time"    — same machine + same repo +
    #                                     overlapping timestamps
    #   - "orchestrator_declared"       — explicit link via API/CLI
    # (weak heuristics deferred post-MVP)
    op.create_table(
        "commit_transcript_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("commit_id", sa.Uuid(), nullable=False),
        sa.Column("transcript_session_id", sa.Uuid(), nullable=False),
        sa.Column(
            "linkage_basis", sa.String(64), nullable=False,
            comment="Why this link exists — one of the four MVP-supported values (see model docstring)",
        ),
        sa.Column(
            "linkage_confidence", sa.String(16), nullable=False,
            comment="'high' | 'medium' | 'low' — coarse audit-facing confidence",
        ),
        sa.Column(
            "linkage_metadata", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
            comment="Debug info, matched fields, timestamps — free-form per linkage_basis",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["commit_id"], ["commits.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_session_id"], ["transcript_sessions.id"],
            ondelete="CASCADE",
        ),
        # Prevent duplicate links for the same commit/session/basis combo
        sa.UniqueConstraint(
            "commit_id", "transcript_session_id", "linkage_basis",
            name="uq_ctl_commit_session_basis",
        ),
    )
    op.create_index(
        "ix_ctl_commit", "commit_transcript_links", ["commit_id"],
    )
    op.create_index(
        "ix_ctl_transcript",
        "commit_transcript_links",
        ["transcript_session_id"],
    )


def downgrade():
    op.drop_index("ix_ctl_transcript", table_name="commit_transcript_links")
    op.drop_index("ix_ctl_commit", table_name="commit_transcript_links")
    op.drop_table("commit_transcript_links")
    op.drop_index(
        "ix_transcript_sessions_vendor_session",
        table_name="transcript_sessions",
    )
    op.drop_index(
        "ix_transcript_sessions_org_machine",
        table_name="transcript_sessions",
    )
    op.drop_table("transcript_sessions")
