"""006 — Hook mode on repositories + org policy documents table.

Persists hook/org policy in PostgreSQL instead of process-local globals.

Revision ID: 006
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    # Hook mode per repo (default evidence_only)
    op.add_column("repositories", sa.Column(
        "hook_mode", sa.String(50), nullable=False, server_default="evidence_only",
        comment="Hook enforcement mode: evidence_only, warning, strict, off",
    ))

    # Org policy documents
    op.create_table(
        "org_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "slug", name="uq_org_policies_org_slug"),
    )


def downgrade():
    op.drop_table("org_policies")
    op.drop_column("repositories", "hook_mode")
