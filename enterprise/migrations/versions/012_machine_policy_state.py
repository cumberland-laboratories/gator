"""012 — Machine policy state: the policy channel's tracking table.

Runtime-split Phase 5 (roadmap item 19, 2026-08-21). E3's
``policies``/``policy_versions`` already own content-addressed policy
versioning; what was missing for the ~/.gator/ policy channel is the
STATE half — which policy version each machine (and each governed repo
on it) has actually applied, reported by ``gator-enterprise policies
pull``. With this table, "which machines/repos are on which policy
version, where is the drift" is one query, mirroring the
transcripts-first split: Enterprise is the query surface, the committed
repo-side policy pin is the proof surface.

Shape decisions:

- ``repo_identifier VARCHAR(512) NOT NULL DEFAULT ''`` — empty string
  means machine-level scope. Deliberately NOT NULL: the Migration 011
  lesson — NULLs never collide inside a Postgres unique constraint, so a
  nullable scope column would break upsert idempotency for every
  machine-level row.
- ``machine_id`` is a plain varchar (the ``commits.machine_id``
  precedent) — machines may report before machine-key registration.
- ``content_hash`` denormalized from ``policy_versions.content_hash``
  so drift comparison needs no join to the version row.
- One CURRENT row per (org, machine, repo, policy) — reports upsert;
  history is Git's job via the committed policy pin.

TRIPWIRE — the upsert in ``app/routes/policy_state.py::report_policy_state``
matches on exactly the four unique-constraint columns. Changing the
constraint shape requires changing that lookup in the same commit.

Revision ID: 012
Revises: 011
"""

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "machine_policy_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id", sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("machine_id", sa.String(255), nullable=False),
        sa.Column(
            "repo_identifier", sa.String(512),
            nullable=False, server_default="",
        ),
        sa.Column(
            "policy_id", sa.Uuid(),
            sa.ForeignKey("policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "policy_version_id", sa.Uuid(),
            sa.ForeignKey("policy_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "machine_id", "repo_identifier", "policy_id",
            name="uq_machine_policy_state_scope",
        ),
    )
    op.create_index(
        "ix_machine_policy_states_organization_id",
        "machine_policy_states", ["organization_id"],
    )
    op.create_index(
        "ix_machine_policy_states_machine_id",
        "machine_policy_states", ["machine_id"],
    )
    op.create_index(
        "ix_machine_policy_states_policy_id",
        "machine_policy_states", ["policy_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_machine_policy_states_policy_id",
                  table_name="machine_policy_states")
    op.drop_index("ix_machine_policy_states_machine_id",
                  table_name="machine_policy_states")
    op.drop_index("ix_machine_policy_states_organization_id",
                  table_name="machine_policy_states")
    op.drop_table("machine_policy_states")
