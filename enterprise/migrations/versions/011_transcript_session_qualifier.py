"""011 — Session qualifier for duplicate-raw-ID transcript coexistence.

Phase 4 of the 2026-08-14 Enterprise audit-surface tranche (Gemini
adapter), substrate path (b) ratified at parent plan §10 item 6.

Gemini CLI is the only known vendor that can produce two DIFFERENT
transcript files carrying the same internal ``sessionId``. Under the
Migration 009 uniqueness contract
(`organization_id, machine_id, vendor, vendor_session_id`) the second
file's ingest upserts over the first — silent evidence loss.

This migration widens the storage substrate so duplicate-raw-ID
transcripts coexist as distinct rows:

- New ``session_qualifier VARCHAR(255) NOT NULL DEFAULT ''`` column on
  ``transcript_sessions``. The Gemini adapter populates it with a
  16-hex-char SHA-256 of the transcript's source path; every other
  vendor adapter sends ``''`` (their raw session IDs are unique).
- The uniqueness constraint is dropped and recreated with the
  qualifier as a fifth column.

Deliberately NOT NULL (the parent plan's prose said "nullable ...
defaulting to ''"): in Postgres, NULLs never collide inside a unique
constraint, so a nullable qualifier would let EVERY vendor ingest
duplicate rows (NULL != NULL) and silently break upsert idempotency.
Empty string preserves the intended "no qualifier" semantics while
keeping the constraint effective.

TRIPWIRE — Migration 010's views read `transcript_sessions` columns by
name; this migration only ADDS a column and renames no existing one,
so the views are unaffected. Any future rename here must be paired
with a view migration (see 010's header TRIPWIRE).

TRIPWIRE — `enterprise/app/routes/ingest.py::ingest_transcript`'s
upsert lookup and `enterprise/app/services/blob_store.py::build_blob_key`
must stay in sync with this constraint shape: the lookup matches on all
five columns, and the blob key appends ``__{session_qualifier}`` when
the qualifier is non-empty so duplicate-raw-ID blobs don't overwrite.

Revision ID: 011
"""

import sqlalchemy as sa
from alembic import op


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

_UQ_NAME = "uq_transcript_sessions_org_machine_vendor_session"


def upgrade() -> None:
    op.add_column(
        "transcript_sessions",
        sa.Column(
            "session_qualifier",
            sa.String(255),
            nullable=False,
            server_default="",
            comment=(
                "Disambiguator for vendors whose raw session IDs can "
                "repeat across files (Gemini): 16-hex SHA-256 of the "
                "source path. Empty string for all other vendors."
            ),
        ),
    )
    op.drop_constraint(_UQ_NAME, "transcript_sessions", type_="unique")
    op.create_unique_constraint(
        _UQ_NAME,
        "transcript_sessions",
        ["organization_id", "machine_id", "vendor", "vendor_session_id",
         "session_qualifier"],
    )


def downgrade() -> None:
    # Downgrade collapses duplicate-raw-ID rows back into collision
    # range; refuse silently losing data is out of scope for a dev-run
    # downgrade — operators must resolve duplicates first if any exist.
    op.drop_constraint(_UQ_NAME, "transcript_sessions", type_="unique")
    op.drop_column("transcript_sessions", "session_qualifier")
    op.create_unique_constraint(
        _UQ_NAME,
        "transcript_sessions",
        ["organization_id", "machine_id", "vendor", "vendor_session_id"],
    )
