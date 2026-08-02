"""007 — Encryption key registry + evidence block crypto columns.

A. org_encryption_keys — org-scoped asymmetric keypairs for envelope encryption.
B. machine_keys — developer machine public keys registered during activate.
C. Extend commit_evidence_blocks with encryption metadata.

Revision ID: 007
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    # A. Org encryption keys
    op.create_table(
        "org_encryption_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("key_id", sa.String(100), nullable=False),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("private_key_pem", sa.Text(), nullable=False),
        sa.Column("algorithm", sa.String(50), nullable=False, server_default="rsa-oaep"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # B. Machine keys
    op.create_table(
        "machine_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("machine_id", sa.String(255), nullable=False),
        sa.Column("machine_label", sa.String(255), nullable=False, server_default=""),
        sa.Column("key_id", sa.String(100), nullable=False),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("algorithm", sa.String(50), nullable=False, server_default="rsa-oaep"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "machine_id", name="uq_machine_keys_org_machine"),
    )

    # C. Extend commit_evidence_blocks
    op.add_column("commit_evidence_blocks", sa.Column(
        "encryption_mode", sa.String(50), nullable=True,
        comment="plaintext or aes-256-gcm",
    ))
    op.add_column("commit_evidence_blocks", sa.Column(
        "org_key_id", sa.String(100), nullable=True,
        comment="Which org key encrypted this block",
    ))
    op.add_column("commit_evidence_blocks", sa.Column(
        "origin_machine_key_id", sa.String(100), nullable=True,
        comment="Which machine key is a recipient",
    ))


def downgrade():
    op.drop_column("commit_evidence_blocks", "origin_machine_key_id")
    op.drop_column("commit_evidence_blocks", "org_key_id")
    op.drop_column("commit_evidence_blocks", "encryption_mode")
    op.drop_table("machine_keys")
    op.drop_table("org_encryption_keys")
