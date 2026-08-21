"""Machine policy state — which policy version each machine/repo has applied.

Runtime-split Phase 5 (roadmap item 19, 2026-08-21): the state-tracking
half of the org/repo policy channel. E3's Policy/PolicyVersion own the
content and its content-addressed versions; this table records what is
ACTUALLY in force where, so "which machines/repos are on which policy
version, where is the drift" is one query (Enterprise = query surface)
while the repo-side policy pin keeps the proof in Git (Git = proof
surface).

One CURRENT row per (org, machine, repo_identifier, policy) — reports
upsert in place; history lives in git (the committed policy pin), not
here.

Scope semantics: ``repo_identifier = ""`` (empty string) is a
MACHINE-LEVEL row (the policy as pulled to ~/.gator/enterprise/);
non-empty is a repo-scoped application. Deliberately NOT NULL — the
Migration 011 lesson: NULLs never collide inside a Postgres unique
constraint, so a nullable scope column would break upsert idempotency
for every machine-level row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class MachinePolicyState(Base, TimestampMixin):
    __tablename__ = "machine_policy_states"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "machine_id", "repo_identifier", "policy_id",
            name="uq_machine_policy_state_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Plain varchar, not an FK — matches the `commits.machine_id`
    # precedent: machines report before/without machine_keys registration.
    machine_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # "" = machine-level scope; non-empty = repo canonical id. NOT NULL by
    # design (see module docstring).
    repo_identifier: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", server_default="",
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policy_versions.id", ondelete="CASCADE"), nullable=False,
    )
    # Denormalized from PolicyVersion.content_hash so the drift query
    # never needs the version row for the common comparison.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
