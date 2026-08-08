"""Tests for TranscriptSession and CommitTranscriptLink models — Phase 1
of the 2026-08-08 transcripts-first MVP plan.

Uses in-memory SQLite (same pattern as test_views.py). Covers:
- Basic insert + read shape for both models
- TranscriptSession uniqueness contract: (org, machine, vendor, session_id)
- CommitTranscriptLink uniqueness contract: (commit, session, basis)
- FK cascade behavior: deleting a commit or transcript session cascades to links
- linkage_basis vocabulary tolerance (any string accepted at DB layer)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.organization import Organization
from app.models.commit import Commit
from app.models.transcript_session import TranscriptSession
from app.models.commit_transcript_link import CommitTranscriptLink


@pytest.fixture
def db():
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")

    # SQLite needs foreign-key enforcement enabled per-connection so
    # cascade delete + IntegrityError tests actually behave like Postgres.
    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def org(db):
    o = Organization(id=uuid.uuid4(), name="Org A", slug="org-a")
    db.add(o)
    db.commit()
    return o


@pytest.fixture
def commit_row(db, org):
    c = Commit(
        id=uuid.uuid4(),
        organization_id=org.id,
        repo_identifier="local/sandbox",
        commit_sha="a" * 40,
        commit_message="test commit",
        committed_at=datetime.now(timezone.utc),
        ingested_at=datetime.now(timezone.utc),
    )
    db.add(c)
    db.commit()
    return c


def _make_session(org, **overrides) -> TranscriptSession:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=org.id,
        machine_id="machine-abc",
        vendor="anthropic",
        vendor_session_id="ba565a28-171b-4a8a-986d-b43a41bdbe2b",
        model="claude-opus-4-7",
        blob_key="transcripts/o/machine-abc/anthropic/2026-08-08/ba565a28.jsonl",
        blob_sha256="0" * 64,
        last_seen_at=now,
        ingested_at=now,
    )
    defaults.update(overrides)
    return TranscriptSession(**defaults)


class TestTranscriptSessionShape:
    def test_insert_and_read(self, db, org):
        s = _make_session(org)
        db.add(s)
        db.commit()
        db.refresh(s)
        got = db.query(TranscriptSession).one()
        assert got.vendor == "anthropic"
        assert got.model == "claude-opus-4-7"
        assert got.blob_sha256 == "0" * 64
        # Server-default retention_class + timestamps present
        assert got.retention_class == "default"
        assert got.created_at is not None
        assert got.updated_at is not None

    def test_uniqueness_org_machine_vendor_session(self, db, org):
        db.add(_make_session(org))
        db.commit()
        # Same 4-tuple → violation
        with pytest.raises(IntegrityError):
            db.add(_make_session(org))
            db.commit()

    def test_different_vendor_same_session_id_ok(self, db, org):
        """The unique key includes vendor, so the same session_id in
        different vendors is allowed. (Unlikely in practice but shouldn't
        be prevented by the schema.)"""
        db.add(_make_session(org, vendor="anthropic"))
        db.commit()
        db.add(_make_session(
            org,
            vendor="openai",
            vendor_session_id="ba565a28-171b-4a8a-986d-b43a41bdbe2b",
        ))
        db.commit()  # no violation
        assert db.query(TranscriptSession).count() == 2

    def test_different_machine_same_session_ok(self, db, org):
        """Multi-machine within one org — same vendor_session_id on
        different machines is allowed."""
        db.add(_make_session(org, machine_id="m1"))
        db.commit()
        db.add(_make_session(org, machine_id="m2"))
        db.commit()
        assert db.query(TranscriptSession).count() == 2


class TestCommitTranscriptLinkShape:
    def _link(self, org, commit, ts, **overrides):
        defaults = dict(
            id=uuid.uuid4(),
            organization_id=org.id,
            commit_id=commit.id,
            transcript_session_id=ts.id,
            linkage_basis="exact_sha_in_transcript",
            linkage_confidence="high",
            linkage_metadata={},
            created_at=datetime.now(timezone.utc),
        )
        defaults.update(overrides)
        return CommitTranscriptLink(**defaults)

    def test_insert_and_read(self, db, org, commit_row):
        ts = _make_session(org)
        db.add(ts)
        db.commit()
        db.add(self._link(org, commit_row, ts, linkage_metadata={"matched_sha": "a" * 40}))
        db.commit()
        got = db.query(CommitTranscriptLink).one()
        assert got.linkage_basis == "exact_sha_in_transcript"
        assert got.linkage_confidence == "high"
        assert got.linkage_metadata == {"matched_sha": "a" * 40}

    def test_uniqueness_commit_session_basis(self, db, org, commit_row):
        ts = _make_session(org)
        db.add(ts)
        db.commit()
        db.add(self._link(org, commit_row, ts))
        db.commit()
        # Same (commit, session, basis) → violation
        with pytest.raises(IntegrityError):
            db.add(self._link(org, commit_row, ts))
            db.commit()

    def test_same_commit_session_different_basis_ok(self, db, org, commit_row):
        """A commit + session pair can be linked by MULTIPLE bases (e.g.,
        both exact-SHA AND session-id-in-snippet). Represents richer audit
        signal, not duplicate linkage."""
        ts = _make_session(org)
        db.add(ts)
        db.commit()
        db.add(self._link(org, commit_row, ts, linkage_basis="exact_sha_in_transcript"))
        db.commit()
        db.add(self._link(org, commit_row, ts, linkage_basis="session_id_in_snippet"))
        db.commit()  # no violation
        assert db.query(CommitTranscriptLink).count() == 2

    def test_deleting_commit_cascades_to_links(self, db, org, commit_row):
        ts = _make_session(org)
        db.add(ts)
        db.commit()
        db.add(self._link(org, commit_row, ts))
        db.commit()
        assert db.query(CommitTranscriptLink).count() == 1
        db.delete(commit_row)
        db.commit()
        assert db.query(CommitTranscriptLink).count() == 0
        # The transcript session survives — cascade is commit → link only
        assert db.query(TranscriptSession).count() == 1

    def test_deleting_session_cascades_to_links(self, db, org, commit_row):
        ts = _make_session(org)
        db.add(ts)
        db.commit()
        db.add(self._link(org, commit_row, ts))
        db.commit()
        assert db.query(CommitTranscriptLink).count() == 1
        db.delete(ts)
        db.commit()
        assert db.query(CommitTranscriptLink).count() == 0
        # The commit survives — cascade is session → link only
        assert db.query(Commit).count() == 1

    def test_linkage_basis_is_string_not_enum(self, db, org, commit_row):
        """The DB accepts any string. Vocabulary discipline lives in
        docs/CLI/API, not in a check constraint (see model docstring)."""
        ts = _make_session(org)
        db.add(ts)
        db.commit()
        db.add(self._link(
            org, commit_row, ts,
            linkage_basis="future_hypothetical_ml_match",
            linkage_confidence="low",
        ))
        db.commit()  # no violation
        assert db.query(CommitTranscriptLink).count() == 1
