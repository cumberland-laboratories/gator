"""Tests for the transcripts-first MVP ingest + read routes.

Covers:
- POST /api/v1/commits/ingest — upsert semantics, idempotency, per-item status
- POST /api/v1/transcripts/ingest — blob write, sha256, base64+gzip decode,
  session upsert, linkage algorithm (exact_sha_in_transcript + session_id_in_snippet)
- GET  /api/v1/transcripts — filters, paging, linked-commit counts
- GET  /api/v1/transcripts/{id} — links inline
- GET  /api/v1/transcripts/{id}/blob — content + integrity headers
- GET  /api/v1/commits/{sha}/transcripts — reverse lookup

All tests use in-memory SQLite (via conftest JSONB compile hook) and a
temporary blob-store root (via monkeypatched app.config.get_settings).
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_token
from app.db import get_db
from app.main import app
from app.models.api_token import ApiToken
from app.models.base import Base
from app.models.commit import Commit
from app.models.commit_transcript_link import CommitTranscriptLink
from app.models.organization import Organization
from app.models.transcript_session import TranscriptSession


# --- Fixtures ---


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    TestSession = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False,
    )
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def org(db_session):
    o = Organization(id=uuid.uuid4(), name="Org T", slug="org-t")
    db_session.add(o)
    db_session.commit()
    return o


@pytest.fixture
def api_token(db_session, org):
    raw = "test-secret-token-12345"
    token = ApiToken(
        id=uuid.uuid4(),
        organization_id=org.id,
        token_hash=hash_token(raw),
        label="test",
        scopes=["read", "write"],
    )
    db_session.add(token)
    db_session.commit()
    return {"raw": raw, "row": token}


@pytest.fixture
def blob_root(tmp_path, monkeypatch):
    """Override BLOB_STORE_ROOT so tests never touch the default /var path."""
    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setenv("BLOB_STORE_ROOT", str(root))
    # get_settings is called freshly per request, so the env is enough —
    # no need to patch a cached singleton.
    return root


@pytest.fixture
def client(db_engine, blob_root):
    TestSession = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False,
    )

    def _override_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _auth(api_token) -> dict:
    return {"Authorization": f"Bearer {api_token['raw']}"}


# ============================================================
# POST /api/v1/commits/ingest
# ============================================================


class TestCommitsIngest:
    def test_creates_new_commits(self, client, api_token):
        payload = {
            "machine_id": "m-1",
            "commits": [
                {
                    "repo_canonical_id": "local/sandbox",
                    "sha": "a" * 40,
                    "subject": "first",
                    "author": "Alan <a@example.com>",
                    "committed_at": "2026-08-07T10:00:00Z",
                    "branch": "main",
                    "transcript_session_id": "session-A",
                },
                {
                    "repo_canonical_id": "local/sandbox",
                    "sha": "b" * 40,
                    "subject": "second",
                    "committed_at": "2026-08-07T10:05:00Z",
                },
            ],
        }
        resp = client.post("/api/v1/commits/ingest", json=payload, headers=_auth(api_token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["commits_ingested"]) == 2
        statuses = {row["sha"]: row["status"] for row in body["commits_ingested"]}
        assert statuses == {"a" * 40: "created", "b" * 40: "created"}

    def test_reingest_is_unchanged(self, client, api_token):
        payload = {
            "machine_id": "m-1",
            "commits": [{
                "repo_canonical_id": "local/sandbox",
                "sha": "c" * 40,
                "subject": "one",
                "author": "a",
                "committed_at": "2026-08-07T10:00:00Z",
            }],
        }
        client.post("/api/v1/commits/ingest", json=payload, headers=_auth(api_token))
        # Second call — same payload, same body
        resp = client.post("/api/v1/commits/ingest", json=payload, headers=_auth(api_token))
        assert resp.status_code == 200
        assert resp.json()["commits_ingested"][0]["status"] == "unchanged"

    def test_reingest_with_richer_data_updates(self, client, api_token):
        # First insert with minimal fields
        client.post("/api/v1/commits/ingest", json={
            "machine_id": "m-1",
            "commits": [{
                "repo_canonical_id": "local/sandbox",
                "sha": "d" * 40,
                "subject": "one",
            }],
        }, headers=_auth(api_token))
        # Second call — adds author + transcript_session_id
        resp = client.post("/api/v1/commits/ingest", json={
            "machine_id": "m-1",
            "commits": [{
                "repo_canonical_id": "local/sandbox",
                "sha": "d" * 40,
                "subject": "one",
                "author": "Alan <a@example.com>",
                "transcript_session_id": "sess-XYZ",
            }],
        }, headers=_auth(api_token))
        assert resp.json()["commits_ingested"][0]["status"] == "updated"

    def test_org_isolation(self, client, api_token, db_session, org):
        # Second org with its own commit at the same SHA — must not
        # cross-contaminate.
        other_org = Organization(id=uuid.uuid4(), name="Other", slug="other")
        db_session.add(other_org)
        other_token = ApiToken(
            id=uuid.uuid4(),
            organization_id=other_org.id,
            token_hash=hash_token("other-token"),
            label="other",
            scopes=["read", "write"],
        )
        db_session.add(other_token)
        db_session.commit()

        payload = {
            "machine_id": "m-1",
            "commits": [{
                "repo_canonical_id": "local/x",
                "sha": "e" * 40,
                "subject": "org-a",
            }],
        }
        r1 = client.post("/api/v1/commits/ingest", json=payload, headers=_auth(api_token))
        assert r1.json()["commits_ingested"][0]["status"] == "created"

        # Same SHA in second org — should be a distinct row, also "created"
        r2 = client.post(
            "/api/v1/commits/ingest", json=payload,
            headers={"Authorization": "Bearer other-token"},
        )
        assert r2.json()["commits_ingested"][0]["status"] == "created"
        assert r1.json()["commits_ingested"][0]["commit_id"] != r2.json()["commits_ingested"][0]["commit_id"]


# ============================================================
# POST /api/v1/transcripts/ingest
# ============================================================


def _make_transcript_body(content_bytes: bytes, **overrides) -> dict:
    payload = {
        "machine_id": "m-1",
        "vendor": "anthropic",
        "vendor_session_id": "ba565a28-171b-4a8a-986d-b43a41bdbe2b",
        "model": "claude-opus-4-7",
        "workspace_hint": "C:\\repo",
        "started_at": "2026-08-07T10:00:00Z",
        "content_encoding": "raw",
        "content": base64.b64encode(content_bytes).decode("ascii"),
    }
    payload.update(overrides)
    return payload


class TestTranscriptsIngest:
    def test_creates_new_session_and_stores_blob(self, client, api_token, blob_root):
        content = b'{"type":"mode","sessionId":"s"}\n{"type":"user"}\n'
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(content),
            headers=_auth(api_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "created"
        assert body["blob_sha256"] == hashlib.sha256(content).hexdigest()
        assert body["blob_size_bytes"] == len(content)
        # Blob physically present
        key_parts = body["blob_key"].split("/")
        assert key_parts[0] == "transcripts"
        stored = (blob_root / body["blob_key"]).read_bytes()
        assert stored == content

    def test_gzip_content_encoding(self, client, api_token, blob_root):
        content = b'{"type":"mode"}\n' * 100
        compressed = gzip.compress(content)
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(compressed, content_encoding="gzip"),
            headers=_auth(api_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        # blob_sha256 is on the DECOMPRESSED payload
        assert body["blob_sha256"] == hashlib.sha256(content).hexdigest()
        assert body["blob_size_bytes"] == len(content)
        stored = (blob_root / body["blob_key"]).read_bytes()
        assert stored == content

    def test_idempotent_reingest_same_content(self, client, api_token, blob_root):
        content = b'{"foo":"bar"}\n'
        r1 = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(content),
            headers=_auth(api_token),
        )
        r2 = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(content),
            headers=_auth(api_token),
        )
        assert r1.json()["transcript_session_id"] == r2.json()["transcript_session_id"]
        assert r2.json()["status"] == "updated"
        assert r1.json()["blob_key"] == r2.json()["blob_key"]

    def test_reingest_different_content_rewrites_blob(self, client, api_token, blob_root):
        r1 = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"content-v1"),
            headers=_auth(api_token),
        )
        r2 = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"content-v2-longer"),
            headers=_auth(api_token),
        )
        assert r1.json()["blob_sha256"] != r2.json()["blob_sha256"]
        stored = (blob_root / r2.json()["blob_key"]).read_bytes()
        assert stored == b"content-v2-longer"

    def test_bad_base64_returns_400(self, client, api_token):
        payload = _make_transcript_body(b"x")
        payload["content"] = "not-valid-base64!!!"
        resp = client.post(
            "/api/v1/transcripts/ingest", json=payload,
            headers=_auth(api_token),
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_parameter"

    def test_missing_fields_return_400(self, client, api_token):
        payload = _make_transcript_body(b"x")
        payload["vendor"] = ""
        resp = client.post(
            "/api/v1/transcripts/ingest", json=payload,
            headers=_auth(api_token),
        )
        assert resp.status_code == 400


# ============================================================
# Linkage algorithm — ingest-time
# ============================================================


class TestLinkageAlgorithm:
    def test_exact_sha_in_transcript_creates_link(self, client, api_token):
        # Seed a commit
        client.post("/api/v1/commits/ingest", json={
            "machine_id": "m-1",
            "commits": [{
                "repo_canonical_id": "local/x",
                "sha": "abc1234567890abc1234567890abc1234567890a",
                "subject": "test",
            }],
        }, headers=_auth(api_token))

        # Transcript body mentions the commit SHA (7-char prefix)
        content = b'we just landed commit abc12345\n{"type":"user"}\n'
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(content),
            headers=_auth(api_token),
        )
        body = resp.json()
        assert len(body["commits_linked"]) == 1
        assert body["commits_linked"][0]["linkage_basis"] == "exact_sha_in_transcript"
        assert body["commits_linked"][0]["commit_sha"] == "abc1234567890abc1234567890abc1234567890a"

    def test_ambiguous_sha_prefix_creates_no_link(self, client, api_token):
        # Seed two commits with the same 7-char prefix
        client.post("/api/v1/commits/ingest", json={
            "commits": [
                {"repo_canonical_id": "local/x", "sha": "abcdefa" + "0" * 33},
                {"repo_canonical_id": "local/x", "sha": "abcdefa" + "1" * 33},
            ],
        }, headers=_auth(api_token))

        content = b"see abcdefa for context\n"
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(content),
            headers=_auth(api_token),
        )
        # Ambiguous → skip rather than link to the wrong one
        assert resp.json()["commits_linked"] == []

    def test_session_id_in_snippet_creates_link(self, client, api_token):
        # Seed a commit whose snippet carried transcript_session_id = the vendor id
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/x",
                "sha": "f" * 40,
                "transcript_session_id": "ba565a28-171b-4a8a-986d-b43a41bdbe2b",
            }],
        }, headers=_auth(api_token))

        # Transcript body doesn't mention the SHA
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"no shas here"),
            headers=_auth(api_token),
        )
        bases = [link["linkage_basis"] for link in resp.json()["commits_linked"]]
        assert "session_id_in_snippet" in bases

    def test_same_sha_multiple_times_in_transcript_dedups(self, client, api_token):
        """Regression: a real Claude transcript hits the same commit's
        SHA multiple times (full 40-char + several prefix forms). Without
        per-call dedup, the second occurrence blows up on the unique
        constraint because we don't flush between iterations."""
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/x",
                "sha": "955cb7823fb002ea23f354194697470f6cb9d96c",
            }],
        }, headers=_auth(api_token))

        # Same commit referenced 3 ways in one transcript
        content = (
            b"see 955cb782 for context\n"
            b"actually 955cb7823fb00\n"
            b"full sha is 955cb7823fb002ea23f354194697470f6cb9d96c\n"
        )
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(content),
            headers=_auth(api_token),
        )
        assert resp.status_code == 200, resp.text
        # Only ONE exact_sha_in_transcript link — not three
        exact_links = [
            l for l in resp.json()["commits_linked"]
            if l["linkage_basis"] == "exact_sha_in_transcript"
        ]
        assert len(exact_links) == 1

    def test_reingest_does_not_duplicate_links(self, client, api_token):
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/x",
                "sha": "abc1234567890abc1234567890abc1234567890a",
            }],
        }, headers=_auth(api_token))

        body = _make_transcript_body(b"see abc12345\n")
        r1 = client.post("/api/v1/transcripts/ingest", json=body, headers=_auth(api_token))
        r2 = client.post("/api/v1/transcripts/ingest", json=body, headers=_auth(api_token))
        # r2's response only counts NEW links — repeated ingest yields 0 new links
        assert len(r1.json()["commits_linked"]) == 1
        assert len(r2.json()["commits_linked"]) == 0


# ============================================================
# GET /api/v1/transcripts
# ============================================================


class TestListTranscripts:
    def test_lists_with_commit_count(self, client, api_token):
        # Seed a commit + transcript that links to it
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/x",
                "sha": "abc1234567890abc1234567890abc1234567890a",
            }],
        }, headers=_auth(api_token))
        client.post("/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"see abc12345\n"),
            headers=_auth(api_token))

        resp = client.get("/api/v1/transcripts", headers=_auth(api_token))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["linked_commit_count"] == 1

    def test_filter_by_vendor(self, client, api_token):
        client.post("/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"x", vendor="anthropic",
                vendor_session_id="A"),
            headers=_auth(api_token))
        client.post("/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"y", vendor="openai",
                vendor_session_id="B"),
            headers=_auth(api_token))

        resp = client.get("/api/v1/transcripts?vendor=openai", headers=_auth(api_token))
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["vendor"] == "openai"

    def test_pagination_has_more(self, client, api_token):
        for i in range(3):
            client.post(
                "/api/v1/transcripts/ingest",
                json=_make_transcript_body(b"x", vendor_session_id=f"s-{i}"),
                headers=_auth(api_token),
            )
        resp = client.get("/api/v1/transcripts?limit=2", headers=_auth(api_token))
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["pagination"]["has_more"] is True

        resp2 = client.get("/api/v1/transcripts?limit=2&offset=2", headers=_auth(api_token))
        assert len(resp2.json()["items"]) == 1
        assert resp2.json()["pagination"]["has_more"] is False


class TestGetTranscript:
    def test_returns_links_inline(self, client, api_token):
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/x",
                "sha": "abc1234567890abc1234567890abc1234567890a",
            }],
        }, headers=_auth(api_token))
        upload = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"see abc12345\n"),
            headers=_auth(api_token),
        )
        tid = upload.json()["transcript_session_id"]

        resp = client.get(f"/api/v1/transcripts/{tid}", headers=_auth(api_token))
        body = resp.json()
        assert body["id"] == tid
        assert len(body["links"]) == 1
        assert body["links"][0]["linkage_basis"] == "exact_sha_in_transcript"
        assert body["links"][0]["commit_sha"] == "abc1234567890abc1234567890abc1234567890a"

    def test_404_for_unknown_id(self, client, api_token):
        random_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/transcripts/{random_id}", headers=_auth(api_token))
        assert resp.status_code == 404


class TestGetBlob:
    def test_streams_content(self, client, api_token):
        content = b'{"type":"user"}\n' * 5
        upload = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(content),
            headers=_auth(api_token),
        )
        tid = upload.json()["transcript_session_id"]
        expected_sha = hashlib.sha256(content).hexdigest()

        resp = client.get(f"/api/v1/transcripts/{tid}/blob", headers=_auth(api_token))
        assert resp.status_code == 200
        assert resp.content == content
        assert resp.headers.get("x-blob-sha256") == expected_sha


class TestCommitTranscripts:
    def test_reverse_lookup(self, client, api_token):
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/x",
                "sha": "abc1234567890abc1234567890abc1234567890a",
            }],
        }, headers=_auth(api_token))
        client.post("/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"see abc12345\n"),
            headers=_auth(api_token))

        # Full SHA
        resp = client.get(
            "/api/v1/commits/abc1234567890abc1234567890abc1234567890a/transcripts",
            headers=_auth(api_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["commits"]) == 1
        assert len(body["links"]) == 1
        assert body["links"][0]["linkage_basis"] == "exact_sha_in_transcript"

    def test_prefix_lookup(self, client, api_token):
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/x",
                "sha": "abc1234567890abc1234567890abc1234567890a",
            }],
        }, headers=_auth(api_token))
        client.post("/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"see abc12345\n"),
            headers=_auth(api_token))

        resp = client.get(
            "/api/v1/commits/abc12345/transcripts",
            headers=_auth(api_token),
        )
        assert resp.status_code == 200
        assert len(resp.json()["commits"]) == 1

    def test_404_for_unknown_sha(self, client, api_token):
        resp = client.get(
            "/api/v1/commits/deadbeefdeadbeef/transcripts",
            headers=_auth(api_token),
        )
        assert resp.status_code == 404

    def test_rejects_short_sha(self, client, api_token):
        # 6 chars — below the 7-char floor. Route asserts hex+length
        # to prevent accidental LIKE-pattern widening even though
        # SQLAlchemy parameterizes the bind variable.
        resp = client.get("/api/v1/commits/abc123/transcripts", headers=_auth(api_token))
        assert resp.status_code == 400
        assert "7-40 hex chars" in resp.json()["error"]["message"]

    def test_rejects_wildcard_in_sha(self, client, api_token):
        # `%` would silently widen the match without the hex check
        resp = client.get(
            "/api/v1/commits/abc12%25/transcripts", headers=_auth(api_token),
        )
        # 400 either from route validation (preferred) or from starlette's
        # path parser rejecting an oddly-shaped segment.
        assert resp.status_code == 400


# ============================================================
# Cross-cutting: token auth
# ============================================================


class TestAuthEnforced:
    def test_ingest_commits_needs_auth(self, client):
        resp = client.post("/api/v1/commits/ingest", json={"commits": []})
        assert resp.status_code == 401

    def test_ingest_transcript_needs_auth(self, client):
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"x"),
        )
        assert resp.status_code == 401

    def test_list_needs_auth(self, client):
        resp = client.get("/api/v1/transcripts")
        assert resp.status_code == 401


# ============================================================
# Phase 3: strong_machine_repo_time linkage basis
# ============================================================


def _ts_body_with_workspace(
    content_bytes: bytes,
    workspace: str,
    started: str = "2026-08-07T10:00:00Z",
    ended: str | None = "2026-08-07T11:00:00Z",
    machine_id: str = "m-1",
    vendor_session_id: str = "sess-strong",
    **overrides,
) -> dict:
    payload = _make_transcript_body(
        content_bytes,
        workspace_hint=workspace,
        started_at=started,
        vendor_session_id=vendor_session_id,
        machine_id=machine_id,
        **overrides,
    )
    if ended is not None:
        payload["ended_at"] = ended
    return payload


class TestStrongMachineRepoTimeLinkage:
    """§8 Step 3 — same machine + basename(workspace_hint) matches
    basename(repo_identifier) + committed_at within 24h of started_at
    → medium-confidence link."""

    def test_positive_match(self, client, api_token):
        # Commit on machine m-1, repo local/gator, committed within the
        # session's time window.
        client.post("/api/v1/commits/ingest", json={
            "machine_id": "m-1",
            "commits": [{
                "repo_canonical_id": "local/gator",
                "sha": "aa" + "0" * 38,
                "committed_at": "2026-08-07T10:30:00Z",
                "machine_id": "m-1",
            }],
        }, headers=_auth(api_token))
        # Transcript with workspace whose basename == "gator"
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_ts_body_with_workspace(
                b"no sha or session id here",
                workspace="C:\\Users\\dev\\code\\gator",
            ),
            headers=_auth(api_token),
        )
        bases = [l["linkage_basis"] for l in resp.json()["commits_linked"]]
        assert "strong_machine_repo_time" in bases

    def test_skipped_when_higher_confidence_link_exists(self, client, api_token):
        # Same setup, but the transcript ALSO mentions the SHA prefix
        # → exact_sha wins, strong_machine_repo_time skipped for this commit.
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/gator",
                "sha": "bb1234567890" + "0" * 28,
                "committed_at": "2026-08-07T10:30:00Z",
                "machine_id": "m-1",
            }],
        }, headers=_auth(api_token))
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_ts_body_with_workspace(
                b"we landed bb123456\n",
                workspace="C:\\Users\\dev\\code\\gator",
                vendor_session_id="sess-strong-A",
            ),
            headers=_auth(api_token),
        )
        bases = {l["linkage_basis"] for l in resp.json()["commits_linked"]}
        assert "exact_sha_in_transcript" in bases
        assert "strong_machine_repo_time" not in bases

    def test_workspace_mismatch_no_link(self, client, api_token):
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/foo",
                "sha": "cc" + "0" * 38,
                "committed_at": "2026-08-07T10:30:00Z",
                "machine_id": "m-1",
            }],
        }, headers=_auth(api_token))
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_ts_body_with_workspace(
                b"x",
                workspace="C:\\code\\bar",  # basename "bar", repo basename "foo"
                vendor_session_id="sess-mismatch",
            ),
            headers=_auth(api_token),
        )
        assert resp.json()["commits_linked"] == []

    def test_time_outside_24h_no_link(self, client, api_token):
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/gator",
                "sha": "dd" + "0" * 38,
                "committed_at": "2026-08-05T00:00:00Z",  # 2+ days before
                "machine_id": "m-1",
            }],
        }, headers=_auth(api_token))
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_ts_body_with_workspace(
                b"x",
                workspace="C:\\code\\gator",
                vendor_session_id="sess-far",
            ),
            headers=_auth(api_token),
        )
        assert resp.json()["commits_linked"] == []

    def test_different_machine_id_no_link(self, client, api_token):
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/gator",
                "sha": "ee" + "0" * 38,
                "committed_at": "2026-08-07T10:30:00Z",
                "machine_id": "m-OTHER",
            }],
        }, headers=_auth(api_token))
        resp = client.post(
            "/api/v1/transcripts/ingest",
            json=_ts_body_with_workspace(
                b"x",
                workspace="C:\\code\\gator",
                vendor_session_id="sess-other-machine",
            ),
            headers=_auth(api_token),
        )
        assert resp.json()["commits_linked"] == []


# ============================================================
# Phase 3: POST /transcripts/{id}/link (orchestrator_declared)
# ============================================================


def _seed_commit_and_transcript(client, api_token, sha=None, vendor_session_id=None):
    sha = sha or ("f" * 40)
    vsid = vendor_session_id or "sess-for-link"
    client.post("/api/v1/commits/ingest", json={
        "commits": [{
            "repo_canonical_id": "local/x",
            "sha": sha,
            "committed_at": "2026-08-07T10:00:00Z",
        }],
    }, headers=_auth(api_token))
    upload = client.post(
        "/api/v1/transcripts/ingest",
        json=_make_transcript_body(b"no linkage", vendor_session_id=vsid),
        headers=_auth(api_token),
    )
    return sha, upload.json()["transcript_session_id"]


class TestOrchestratorDeclaredLink:
    def test_creates_link(self, client, api_token):
        sha, tid = _seed_commit_and_transcript(client, api_token)
        resp = client.post(
            f"/api/v1/transcripts/{tid}/link",
            json={"commit_sha": sha},
            headers=_auth(api_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "created"
        assert body["linkage_basis"] == "orchestrator_declared"
        assert body["linkage_confidence"] == "high"
        assert body["commit_sha"] == sha

    def test_idempotent(self, client, api_token):
        sha, tid = _seed_commit_and_transcript(client, api_token)
        client.post(f"/api/v1/transcripts/{tid}/link",
            json={"commit_sha": sha}, headers=_auth(api_token))
        resp2 = client.post(f"/api/v1/transcripts/{tid}/link",
            json={"commit_sha": sha}, headers=_auth(api_token))
        assert resp2.json()["status"] == "unchanged"

    def test_link_visible_via_commits_transcripts(self, client, api_token):
        sha, tid = _seed_commit_and_transcript(client, api_token)
        client.post(f"/api/v1/transcripts/{tid}/link",
            json={"commit_sha": sha, "linkage_metadata": {"note": "operator saw slack"}},
            headers=_auth(api_token))
        resp = client.get(f"/api/v1/commits/{sha}/transcripts", headers=_auth(api_token))
        bases = [l["linkage_basis"] for l in resp.json()["links"]]
        assert "orchestrator_declared" in bases

    def test_prefix_sha_accepted(self, client, api_token):
        sha, tid = _seed_commit_and_transcript(client, api_token, sha="0abc1234" + "0" * 32)
        # 8-char prefix
        resp = client.post(f"/api/v1/transcripts/{tid}/link",
            json={"commit_sha": "0abc1234"}, headers=_auth(api_token))
        assert resp.status_code == 200
        assert resp.json()["commit_sha"] == "0abc1234" + "0" * 32

    def test_ambiguous_sha_returns_409(self, client, api_token):
        # Two commits with same 7-char prefix but different suffixes
        client.post("/api/v1/commits/ingest", json={
            "commits": [
                {"repo_canonical_id": "local/x", "sha": "abcdef1" + "0" * 33},
                {"repo_canonical_id": "local/x", "sha": "abcdef1" + "1" * 33},
            ],
        }, headers=_auth(api_token))
        upload = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"x", vendor_session_id="ambiguous"),
            headers=_auth(api_token),
        )
        tid = upload.json()["transcript_session_id"]
        resp = client.post(f"/api/v1/transcripts/{tid}/link",
            json={"commit_sha": "abcdef1"}, headers=_auth(api_token))
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "ambiguous_commit"

    def test_unknown_commit_404(self, client, api_token):
        _, tid = _seed_commit_and_transcript(client, api_token)
        resp = client.post(f"/api/v1/transcripts/{tid}/link",
            json={"commit_sha": "deadbeef" + "0" * 32}, headers=_auth(api_token))
        assert resp.status_code == 404

    def test_bad_sha_400(self, client, api_token):
        _, tid = _seed_commit_and_transcript(client, api_token)
        resp = client.post(f"/api/v1/transcripts/{tid}/link",
            json={"commit_sha": "not-hex-here!"}, headers=_auth(api_token))
        assert resp.status_code == 400

    def test_unknown_transcript_404(self, client, api_token):
        random_tid = str(uuid.uuid4())
        resp = client.post(f"/api/v1/transcripts/{random_tid}/link",
            json={"commit_sha": "a" * 40}, headers=_auth(api_token))
        assert resp.status_code == 404


# ============================================================
# Phase 3: POST /transcripts/{id}/relink
# ============================================================


class TestRelink:
    def test_adds_new_link_when_commit_ingested_after_transcript(self, client, api_token):
        # Ingest transcript FIRST — no commits exist yet, so no links
        upload = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(
                b"we landed 1234abc today\n",
                vendor_session_id="sess-relink",
            ),
            headers=_auth(api_token),
        )
        tid = upload.json()["transcript_session_id"]
        assert upload.json()["commits_linked"] == []

        # NOW ingest the commit
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/x",
                "sha": "1234abc" + "0" * 33,
            }],
        }, headers=_auth(api_token))

        # Relink discovers the new link
        resp = client.post(f"/api/v1/transcripts/{tid}/relink", headers=_auth(api_token))
        assert resp.status_code == 200
        links = resp.json()["commits_linked"]
        assert any(l["linkage_basis"] == "exact_sha_in_transcript" for l in links)

    def test_idempotent(self, client, api_token):
        client.post("/api/v1/commits/ingest", json={
            "commits": [{"repo_canonical_id": "local/x", "sha": "5678def" + "0" * 33}],
        }, headers=_auth(api_token))
        upload = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(
                b"see 5678def\n", vendor_session_id="idem-relink",
            ),
            headers=_auth(api_token),
        )
        tid = upload.json()["transcript_session_id"]
        # Relink: no NEW links (already linked at ingest)
        resp = client.post(f"/api/v1/transcripts/{tid}/relink", headers=_auth(api_token))
        assert resp.json()["commits_linked"] == []

    def test_preserves_orchestrator_declared_links(self, client, api_token):
        client.post("/api/v1/commits/ingest", json={
            "commits": [{"repo_canonical_id": "local/x", "sha": "77" + "0" * 38}],
        }, headers=_auth(api_token))
        upload = client.post(
            "/api/v1/transcripts/ingest",
            json=_make_transcript_body(b"no linkage", vendor_session_id="preserve-orch"),
            headers=_auth(api_token),
        )
        tid = upload.json()["transcript_session_id"]
        # Operator-declared link
        client.post(f"/api/v1/transcripts/{tid}/link",
            json={"commit_sha": "77" + "0" * 38}, headers=_auth(api_token))
        # Relink runs — should NOT delete the orchestrator link
        client.post(f"/api/v1/transcripts/{tid}/relink", headers=_auth(api_token))
        detail = client.get(f"/api/v1/transcripts/{tid}", headers=_auth(api_token))
        bases = [l["linkage_basis"] for l in detail.json()["links"]]
        assert "orchestrator_declared" in bases

    def test_unknown_transcript_404(self, client, api_token):
        random_tid = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/transcripts/{random_tid}/relink",
            headers=_auth(api_token),
        )
        assert resp.status_code == 404
