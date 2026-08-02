"""008 — Add transcript_session_id to commits.

Stores vendor session ID from snippet for direct evidence quality measurement.

Revision ID: 008
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("commits", sa.Column(
        "transcript_session_id", sa.String(255), nullable=True,
        comment="Vendor session ID from snippet. Null = vendor hook not installed or human-only.",
    ))


def downgrade():
    op.drop_column("commits", "transcript_session_id")
