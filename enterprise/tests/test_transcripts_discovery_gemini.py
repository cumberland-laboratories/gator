"""Phase 4 (2026-08-15) — Gemini adapter + Migration 011 regression pins.

Three layers, per the parent audit-surface plan §6:

- Discovery: `_parse_gemini_json_metadata` + `discover_gemini_transcripts`
  + root accessor + vendor dispatch (parallel to the Codex Phase 3 pins).
- Qualifier: `session_qualifier` derivation (source-path hash) and its
  wire-through from discovery record to ingest payload.
- `TestDuplicateSessionIdAcrossFiles` — the plan-mandated three
  assertions for the duplicate-raw-ID case: two rows (storage), two
  blob keys (blob storage), and TWO `session_id_in_snippet` links each
  at `medium` confidence (linkage under ratified §10 item 7 = β
  multi-link fan-out), regardless of ingest order.

End-to-end tests use in-memory SQLite + a temp blob root, mirroring
`test_ingest_routes.py`'s fixtures.
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_token
from app.db import get_db
from app.main import app
from app.models.api_token import ApiToken
from app.models.base import Base
from app.models.commit_transcript_link import CommitTranscriptLink
from app.models.organization import Organization
from app.models.transcript_session import TranscriptSession
from app.services.blob_store import build_blob_key

from gator_enterprise_cli.transcripts_discovery import (
    _gemini_session_qualifier,
    _parse_gemini_json_metadata,
    discover,
    discover_gemini_transcripts,
    gemini_root_path,
)


# --- Gemini file helpers ---


def _write_gemini_session(
    root: Path,
    project: str,
    filename: str,
    session_id: str | None = "sess-0001",
    start: str | None = "2026-08-01T10:00:00Z",
    end: str | None = "2026-08-01T11:00:00Z",
    messages: list | None = None,
    raw_text: str | None = None,
) -> Path:
    chats = root / project / "chats"
    chats.mkdir(parents=True, exist_ok=True)
    p = chats / filename
    if raw_text is not None:
        p.write_text(raw_text, encoding="utf-8")
        return p
    doc: dict = {
        "projectHash": "abc123",
        "startTime": start,
        "lastUpdated": end,
        "kind": "chat",
        "messages": messages if messages is not None else [
            {"type": "user", "content": [{"type": "text", "text": "hi"}]},
            {"type": "gemini", "model": "gemini-2.5-pro",
             "content": [{"type": "text", "text": "hello"}],
             "tokens": {"input": 3, "output": 5}},
            {"type": "info", "content": []},
            {"type": "user", "content": [{"type": "text", "text": "more"}]},
            {"type": "gemini", "model": "gemini-2.5-pro", "content": []},
        ],
    }
    if session_id is not None:
        doc["sessionId"] = session_id
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


# ============================================================
# Discovery-level pins
# ============================================================


class TestParseSingleGeminiTranscript:
    def test_extracts_core_metadata(self, tmp_path):
        p = _write_gemini_session(tmp_path, "projA", "session-2026-08-01T10-00-00-aaa.json")
        r = _parse_gemini_json_metadata(p)
        assert r.vendor == "google"
        assert r.vendor_session_id == "sess-0001"
        assert r.model == "gemini-2.5-pro"
        assert r.turn_count == 4  # 2 user + 2 gemini; info excluded
        assert r.started_at == datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
        assert r.ended_at == datetime(2026, 8, 1, 11, 0, tzinfo=timezone.utc)
        assert r.parse_error is None
        assert r.unreadable is False

    def test_missing_session_id_falls_back_to_stem(self, tmp_path):
        p = _write_gemini_session(
            tmp_path, "projA", "session-2026-08-01T10-00-00-bbb.json",
            session_id=None,
        )
        r = _parse_gemini_json_metadata(p)
        assert r.vendor_session_id == p.stem
        assert r.parse_error is not None
        assert "fell back to filename stem" in r.parse_error
        assert r.unreadable is False

    def test_malformed_json_is_degraded_not_unreadable(self, tmp_path):
        p = _write_gemini_session(
            tmp_path, "projA", "session-2026-08-01T10-00-00-ccc.json",
            raw_text="{not valid json",
        )
        r = _parse_gemini_json_metadata(p)
        assert r.vendor_session_id == p.stem
        assert r.unreadable is False
        assert "malformed JSON" in (r.parse_error or "")

    def test_oserror_sets_unreadable(self, tmp_path, monkeypatch):
        p = _write_gemini_session(tmp_path, "projA", "session-2026-08-01T10-00-00-ddd.json")
        original_open = Path.open

        def _raise_on_target(self, *args, **kwargs):
            if self == p:
                raise OSError("Permission denied (simulated)")
            return original_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", _raise_on_target)
        r = _parse_gemini_json_metadata(p)
        assert r.unreadable is True
        assert "read failed" in (r.parse_error or "")

    def test_workspace_hint_reverse_maps_projects_json(self, tmp_path):
        p = _write_gemini_session(tmp_path, "gator", "session-2026-08-01T10-00-00-eee.json")
        projects_map = {"C:\\Users\\x\\code\\gator": "gator"}
        r = _parse_gemini_json_metadata(p, projects_map)
        assert r.workspace_hint == "C:\\Users\\x\\code\\gator"

    def test_workspace_hint_falls_back_to_project_dirname(self, tmp_path):
        p = _write_gemini_session(tmp_path, "solo-proj", "session-2026-08-01T10-00-00-fff.json")
        r = _parse_gemini_json_metadata(p, {})
        assert r.workspace_hint == "solo-proj"


class TestGeminiQualifier:
    def test_qualifier_is_16_hex_of_source_path(self, tmp_path):
        p = _write_gemini_session(tmp_path, "projA", "session-2026-08-01T10-00-00-aaa.json")
        q = _gemini_session_qualifier(p)
        assert len(q) == 16
        int(q, 16)  # raises if not hex
        assert _parse_gemini_json_metadata(p).session_qualifier == q

    def test_same_session_id_different_files_get_distinct_qualifiers(self, tmp_path):
        p1 = _write_gemini_session(tmp_path, "projA", "session-2026-08-01T10-00-00-aaa.json",
                                   session_id="dup-raw")
        p2 = _write_gemini_session(tmp_path, "projA", "session-2026-08-02T10-00-00-bbb.json",
                                   session_id="dup-raw")
        r1 = _parse_gemini_json_metadata(p1)
        r2 = _parse_gemini_json_metadata(p2)
        assert r1.vendor_session_id == r2.vendor_session_id == "dup-raw"
        assert r1.session_qualifier != r2.session_qualifier

    def test_non_gemini_records_have_empty_qualifier(self, tmp_path, monkeypatch):
        # Claude discovery path — records must carry "" so pre-011 blob
        # keys and upsert identity stay byte-identical for other vendors.
        proj = tmp_path / "claude-projects" / "hash1"
        proj.mkdir(parents=True)
        (proj / "abc.jsonl").write_text(
            '{"sessionId":"c1","timestamp":"2026-08-01T10:00:00Z"}\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("CLAUDE_TRANSCRIPTS_ROOT", str(tmp_path / "claude-projects"))
        records = list(discover("claude"))
        assert records and all(r.session_qualifier == "" for r in records)


class TestDiscoverGemini:
    def test_yields_all_sessions_across_projects(self, tmp_path):
        _write_gemini_session(tmp_path, "projA", "session-2026-08-01T10-00-00-aaa.json",
                              session_id="s-a")
        _write_gemini_session(tmp_path, "projB", "session-2026-08-02T10-00-00-bbb.json",
                              session_id="s-b")
        got = {r.vendor_session_id for r in discover_gemini_transcripts(tmp_path)}
        assert got == {"s-a", "s-b"}

    def test_since_filters_older_sessions(self, tmp_path):
        _write_gemini_session(tmp_path, "projA", "session-2026-07-01T10-00-00-old.json",
                              session_id="s-old",
                              start="2026-07-01T10:00:00Z", end="2026-07-01T11:00:00Z")
        _write_gemini_session(tmp_path, "projA", "session-2026-08-02T10-00-00-new.json",
                              session_id="s-new",
                              start="2026-08-02T10:00:00Z", end="2026-08-02T11:00:00Z")
        since = datetime(2026, 8, 1, tzinfo=timezone.utc)
        got = {r.vendor_session_id
               for r in discover_gemini_transcripts(tmp_path, since=since)}
        assert got == {"s-new"}

    def test_no_timestamps_always_yielded(self, tmp_path):
        _write_gemini_session(tmp_path, "projA", "session-x-none.json",
                              session_id="s-nots", start=None, end=None)
        since = datetime(2026, 8, 1, tzinfo=timezone.utc)
        got = {r.vendor_session_id
               for r in discover_gemini_transcripts(tmp_path, since=since)}
        assert "s-nots" in got

    def test_missing_root_yields_nothing(self, tmp_path):
        assert list(discover_gemini_transcripts(tmp_path / "nope")) == []

    def test_ignores_non_session_files(self, tmp_path):
        _write_gemini_session(tmp_path, "projA", "session-2026-08-01T10-00-00-aaa.json",
                              session_id="s-a")
        (tmp_path / "projA" / "chats" / "notes.json").write_text("{}", encoding="utf-8")
        (tmp_path / "projA" / "logs.json").write_text("{}", encoding="utf-8")
        got = [r.vendor_session_id for r in discover_gemini_transcripts(tmp_path)]
        assert got == ["s-a"]

    def test_projects_json_read_from_root_parent(self, tmp_path):
        root = tmp_path / "tmp"
        _write_gemini_session(root, "gator", "session-2026-08-01T10-00-00-aaa.json")
        (tmp_path / "projects.json").write_text(
            json.dumps({"projects": {"/home/u/code/gator": "gator"}}),
            encoding="utf-8",
        )
        records = list(discover_gemini_transcripts(root))
        assert records[0].workspace_hint == "/home/u/code/gator"


class TestGeminiRootAccessor:
    def test_default_root(self, monkeypatch):
        monkeypatch.delenv("GEMINI_TRANSCRIPTS_ROOT", raising=False)
        assert gemini_root_path() == Path(os.path.expanduser("~/.gemini/tmp"))

    def test_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEMINI_TRANSCRIPTS_ROOT", str(tmp_path))
        assert gemini_root_path() == tmp_path


class TestGeminiVendorDispatch:
    def test_gemini_and_google_aliases_resolve(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GEMINI_TRANSCRIPTS_ROOT", str(tmp_path))
        _write_gemini_session(tmp_path, "projA", "session-2026-08-01T10-00-00-aaa.json",
                              session_id="s-a")
        for vendor in ("gemini", "google"):
            got = [r.vendor_session_id for r in discover(vendor)]
            assert got == ["s-a"], vendor


# ============================================================
# End-to-end: Migration 011 substrate + β fan-out
# (fixtures mirror test_ingest_routes.py)
# ============================================================


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
    o = Organization(id=uuid.uuid4(), name="Org G", slug="org-g")
    db_session.add(o)
    db_session.commit()
    return o


@pytest.fixture
def api_token(db_session, org):
    raw = "test-secret-token-gemini"
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
    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setenv("BLOB_STORE_ROOT", str(root))
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


def _gemini_body(content: bytes, qualifier: str, **overrides) -> dict:
    payload = {
        "machine_id": "m-g",
        "vendor": "google",
        "vendor_session_id": "dup-raw-id",
        "session_qualifier": qualifier,
        "model": "gemini-2.5-pro",
        "workspace_hint": "/home/u/code/gator",
        "started_at": "2026-08-10T10:00:00Z",
        "content_encoding": "raw",
        "content": base64.b64encode(content).decode("ascii"),
    }
    payload.update(overrides)
    return payload


class TestBuildBlobKeyQualifier:
    def test_qualifier_appended_when_present(self):
        key = build_blob_key(
            org_uuid="o", machine_id="m-1", vendor="google",
            started_at_iso="2026-08-10T10:00:00Z",
            vendor_session_id="dup", session_qualifier="abcd1234abcd1234",
        )
        assert key.endswith("/dup__abcd1234abcd1234.jsonl")

    def test_empty_qualifier_preserves_pre_011_shape(self):
        key = build_blob_key(
            org_uuid="o", machine_id="m-1", vendor="anthropic",
            started_at_iso="2026-08-10T10:00:00Z",
            vendor_session_id="sess",
        )
        assert key.endswith("/sess.jsonl")
        assert "__" not in key


class TestDuplicateSessionIdAcrossFiles:
    """Parent plan §6 three-assertion contract for the duplicate-ID case."""

    def test_storage_two_rows_not_one_upsert(self, client, api_token, db_session):
        r1 = client.post("/api/v1/transcripts/ingest",
                         json=_gemini_body(b"file one", "q1" * 8),
                         headers=_auth(api_token))
        r2 = client.post("/api/v1/transcripts/ingest",
                         json=_gemini_body(b"file two", "q2" * 8),
                         headers=_auth(api_token))
        assert r1.json()["status"] == "created"
        assert r2.json()["status"] == "created"
        rows = db_session.execute(
            select(TranscriptSession).where(
                TranscriptSession.vendor_session_id == "dup-raw-id")
        ).scalars().all()
        assert len(rows) == 2
        assert {r.session_qualifier for r in rows} == {"q1" * 8, "q2" * 8}

    def test_blob_two_distinct_keys_no_overwrite(self, client, api_token, blob_root):
        r1 = client.post("/api/v1/transcripts/ingest",
                         json=_gemini_body(b"file one", "q1" * 8),
                         headers=_auth(api_token))
        r2 = client.post("/api/v1/transcripts/ingest",
                         json=_gemini_body(b"file two", "q2" * 8),
                         headers=_auth(api_token))
        k1, k2 = r1.json()["blob_key"], r2.json()["blob_key"]
        assert k1 != k2
        assert (blob_root / k1).read_bytes() == b"file one"
        assert (blob_root / k2).read_bytes() == b"file two"

    def test_linkage_beta_fanout_two_links_both_medium(
        self, client, api_token, db_session,
    ):
        # Commit whose snippet carried the RAW (ambiguous) session id.
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/gator",
                "sha": "a" * 40,
                "transcript_session_id": "dup-raw-id",
            }],
        }, headers=_auth(api_token))

        # First duplicate ingests while it is still the ONLY row → its
        # link is created at high confidence...
        client.post("/api/v1/transcripts/ingest",
                    json=_gemini_body(b"file one", "q1" * 8),
                    headers=_auth(api_token))
        # ...second duplicate arrives → fan-out + retroactive downgrade.
        client.post("/api/v1/transcripts/ingest",
                    json=_gemini_body(b"file two", "q2" * 8),
                    headers=_auth(api_token))

        links = db_session.execute(
            select(CommitTranscriptLink).where(
                CommitTranscriptLink.linkage_basis == "session_id_in_snippet")
        ).scalars().all()
        assert len(links) == 2
        assert {l.transcript_session_id for l in links} != {None}
        assert len({l.transcript_session_id for l in links}) == 2
        assert all(l.linkage_confidence == "medium" for l in links)
        # Ambiguity metadata must be order-independent (whiteboard
        # 2026-08-16 Finding 1): the FIRST sibling's link — created at
        # high confidence before the duplicate existed — must carry the
        # same `raw_id_ambiguous_across` marker the second one gets.
        assert all(
            (l.linkage_metadata or {}).get("raw_id_ambiguous_across") == 2
            for l in links
        )

    def test_third_sibling_refreshes_ambiguity_count(
        self, client, api_token, db_session,
    ):
        # The retroactive convergence re-stamps ALL sibling links on
        # every ambiguous ingest, so earlier links don't keep a stale
        # count when more duplicates arrive.
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/gator",
                "sha": "a" * 40,
                "transcript_session_id": "dup-raw-id",
            }],
        }, headers=_auth(api_token))
        for content, qualifier in (
            (b"file one", "q1" * 8),
            (b"file two", "q2" * 8),
            (b"file three", "q3" * 8),
        ):
            client.post("/api/v1/transcripts/ingest",
                        json=_gemini_body(content, qualifier),
                        headers=_auth(api_token))
        links = db_session.execute(
            select(CommitTranscriptLink).where(
                CommitTranscriptLink.linkage_basis == "session_id_in_snippet")
        ).scalars().all()
        assert len(links) == 3
        assert all(l.linkage_confidence == "medium" for l in links)
        assert all(
            (l.linkage_metadata or {}).get("raw_id_ambiguous_across") == 3
            for l in links
        )

    def test_reingest_same_file_still_upserts(self, client, api_token, db_session):
        body = _gemini_body(b"file one", "q1" * 8)
        first = client.post("/api/v1/transcripts/ingest", json=body,
                            headers=_auth(api_token))
        again = client.post("/api/v1/transcripts/ingest", json=body,
                            headers=_auth(api_token))
        assert first.json()["status"] == "created"
        assert again.json()["status"] == "updated"
        rows = db_session.execute(
            select(TranscriptSession).where(
                TranscriptSession.vendor_session_id == "dup-raw-id")
        ).scalars().all()
        assert len(rows) == 1

    def test_non_duplicate_vendor_link_stays_high(self, client, api_token, db_session):
        # Single-row (non-ambiguous) snippet linkage keeps high confidence —
        # the β downgrade must ONLY fire under genuine duplicates.
        client.post("/api/v1/commits/ingest", json={
            "commits": [{
                "repo_canonical_id": "local/gator",
                "sha": "b" * 40,
                "transcript_session_id": "unique-raw-id",
            }],
        }, headers=_auth(api_token))
        client.post("/api/v1/transcripts/ingest",
                    json=_gemini_body(b"solo", "qs" * 8,
                                      vendor_session_id="unique-raw-id"),
                    headers=_auth(api_token))
        links = db_session.execute(
            select(CommitTranscriptLink).where(
                CommitTranscriptLink.linkage_basis == "session_id_in_snippet")
        ).scalars().all()
        assert len(links) == 1
        assert links[0].linkage_confidence == "high"
        assert "raw_id_ambiguous_across" not in (links[0].linkage_metadata or {})
