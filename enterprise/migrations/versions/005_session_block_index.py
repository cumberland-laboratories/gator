"""005 — Session block index + machine identity on commits.

A. Adds columns to commit_evidence_blocks for session block metadata indexing.
B. Adds machine_id, machine_label, snippet_agent to commits table.

Revision ID: 005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    # A. Session block index columns on commit_evidence_blocks
    op.add_column("commit_evidence_blocks", sa.Column(
        "artifact_path", sa.String(500), nullable=True,
        comment=".gator/session-blocks/<stem>.json.gz",
    ))
    op.add_column("commit_evidence_blocks", sa.Column(
        "indexed_from_ref", sa.String(255), nullable=True,
        comment="Bare branch name where block was discovered (e.g., main, feature-branch). Upgraded to default branch on merge.",
    ))
    op.add_column("commit_evidence_blocks", sa.Column(
        "target_commit_sha", sa.String(64), nullable=True,
        comment="Commit SHA this block describes (from target_commit in payload)",
    ))
    op.add_column("commit_evidence_blocks", sa.Column(
        "capture_quality", sa.String(50), nullable=True,
        comment="exact, best_effort, partial, missing_head, missing_tail",
    ))
    op.add_column("commit_evidence_blocks", sa.Column(
        "vendor", sa.String(50), nullable=True,
        comment="anthropic, openai, google, unknown",
    ))
    op.add_column("commit_evidence_blocks", sa.Column(
        "turn_count", sa.Integer(), nullable=True,
    ))
    op.add_column("commit_evidence_blocks", sa.Column(
        "indexed_at", sa.DateTime(timezone=True), nullable=True,
    ))
    op.add_column("commit_evidence_blocks", sa.Column(
        "plaintext_size_bytes", sa.BigInteger(), nullable=True,
    ))

    # B. Machine identity + snippet agent on commits
    op.add_column("commits", sa.Column(
        "machine_id", sa.String(255), nullable=True,
        comment="Gator machine identifier from snippet machine_id field",
    ))
    op.add_column("commits", sa.Column(
        "machine_label", sa.String(255), nullable=True,
        comment="Human-readable machine name from snippet machine_label field",
    ))
    op.add_column("commits", sa.Column(
        "snippet_agent", sa.String(255), nullable=True,
        comment="AI agent from snippet. Null = human-only commit. Key discriminator for pending block detection.",
    ))

    # Index for fleet-level machine queries
    op.create_index(
        "ix_commits_org_machine",
        "commits",
        ["organization_id", "machine_id"],
    )


def downgrade():
    op.drop_index("ix_commits_org_machine", table_name="commits")
    op.drop_column("commits", "snippet_agent")
    op.drop_column("commits", "machine_label")
    op.drop_column("commits", "machine_id")
    op.drop_column("commit_evidence_blocks", "plaintext_size_bytes")
    op.drop_column("commit_evidence_blocks", "indexed_at")
    op.drop_column("commit_evidence_blocks", "turn_count")
    op.drop_column("commit_evidence_blocks", "vendor")
    op.drop_column("commit_evidence_blocks", "capture_quality")
    op.drop_column("commit_evidence_blocks", "target_commit_sha")
    op.drop_column("commit_evidence_blocks", "indexed_from_ref")
    op.drop_column("commit_evidence_blocks", "artifact_path")
