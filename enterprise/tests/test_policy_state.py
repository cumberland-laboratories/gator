"""Tests for the policy-state routes (runtime-split Phase 5, Migration 012).

The policy channel's state half: machines report applied policy versions;
the drift query answers "who is on what, where is the drift" in one call.
"""

from __future__ import annotations

import uuid

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
from app.models.organization import Organization


# Fixtures mirror test_ingest_routes.py / test_transcripts_discovery_gemini.py
# (per-file by house convention — no shared conftest fixtures).

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
    o = Organization(id=uuid.uuid4(), name="Org P", slug="org-p")
    db_session.add(o)
    db_session.commit()
    return o


@pytest.fixture
def api_token(db_session, org):
    raw = "test-secret-token-policy-state"
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
def client(db_engine):
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


def _auth(api_token):
    return {"Authorization": f"Bearer {api_token['raw']}"}


@pytest.fixture
def policy_with_versions(client, api_token):
    """A policy with v1 + v2, v2 active. Returns dict of useful ids/hashes."""
    r = client.post("/api/v1/policies",
                    json={"name": "Org Constitution", "slug": "org-constitution"},
                    headers=_auth(api_token))
    assert r.status_code == 200, r.text
    policy_id = r.json()["id"]

    r1 = client.post(f"/api/v1/policies/{policy_id}/versions",
                     json={"content": {"text": "version one"}},
                     headers=_auth(api_token))
    assert r1.status_code == 200, r1.text
    v1 = r1.json()
    r2 = client.post(f"/api/v1/policies/{policy_id}/versions",
                     json={"content": {"text": "version two"}},
                     headers=_auth(api_token))
    assert r2.status_code == 200, r2.text
    v2 = r2.json()
    r = client.post(f"/api/v1/policies/{policy_id}/activate/{v2['id']}",
                    headers=_auth(api_token))
    assert r.status_code == 200, r.text
    return {"policy_id": policy_id, "slug": "org-constitution",
            "v1": v1, "v2": v2}


def _report(client, api_token, machine="m-1", slug="org-constitution",
            content_hash=None, repo=""):
    return client.post("/api/v1/policy-state/report", json={
        "machine_id": machine,
        "entries": [{"policy_slug": slug, "content_hash": content_hash,
                     "repo_identifier": repo}],
    }, headers=_auth(api_token))


class TestReport:
    def test_report_active_version_is_in_sync(self, client, api_token,
                                              policy_with_versions):
        p = policy_with_versions
        r = _report(client, api_token, content_hash=p["v2"]["content_hash"])
        assert r.status_code == 200
        res = r.json()["results"][0]
        assert res["status"] == "created"
        assert res["in_sync"] is True

    def test_report_stale_version_flags_drift(self, client, api_token,
                                              policy_with_versions):
        p = policy_with_versions
        res = _report(client, api_token,
                      content_hash=p["v1"]["content_hash"]).json()["results"][0]
        assert res["status"] == "created"
        assert res["in_sync"] is False
        assert res["active_version_number"] == p["v2"]["version_number"]

    def test_reports_upsert_one_current_row(self, client, api_token,
                                            policy_with_versions, db_session):
        from app.models.machine_policy_state import MachinePolicyState
        from sqlalchemy import select
        p = policy_with_versions
        first = _report(client, api_token, content_hash=p["v1"]["content_hash"])
        assert first.json()["results"][0]["status"] == "created"
        second = _report(client, api_token, content_hash=p["v2"]["content_hash"])
        assert second.json()["results"][0]["status"] == "updated"
        rows = db_session.execute(select(MachinePolicyState)).scalars().all()
        assert len(rows) == 1
        assert rows[0].content_hash == p["v2"]["content_hash"]

    def test_machine_and_repo_scopes_are_distinct_rows(self, client, api_token,
                                                       policy_with_versions,
                                                       db_session):
        from app.models.machine_policy_state import MachinePolicyState
        from sqlalchemy import select
        p = policy_with_versions
        _report(client, api_token, content_hash=p["v2"]["content_hash"], repo="")
        _report(client, api_token, content_hash=p["v2"]["content_hash"],
                repo="local/repo-a")
        rows = db_session.execute(select(MachinePolicyState)).scalars().all()
        assert len(rows) == 2
        assert {r.repo_identifier for r in rows} == {"", "local/repo-a"}

    def test_unknown_slug_is_per_entry_error_not_500(self, client, api_token,
                                                     policy_with_versions):
        p = policy_with_versions
        r = client.post("/api/v1/policy-state/report", json={
            "machine_id": "m-1",
            "entries": [
                {"policy_slug": "nope", "content_hash": "x" * 64},
                {"policy_slug": p["slug"],
                 "content_hash": p["v2"]["content_hash"]},
            ],
        }, headers=_auth(api_token))
        assert r.status_code == 200
        results = r.json()["results"]
        assert results[0]["status"] == "error"
        assert results[1]["status"] == "created"

    def test_hash_matching_no_version_is_error(self, client, api_token,
                                               policy_with_versions):
        res = _report(client, api_token,
                      content_hash="f" * 64).json()["results"][0]
        assert res["status"] == "error"
        assert "no version" in res["detail"]

    def test_missing_machine_id_is_400(self, client, api_token):
        r = client.post("/api/v1/policy-state/report",
                        json={"entries": [{}]}, headers=_auth(api_token))
        assert r.status_code == 400


class TestStateAndDrift:
    def test_list_shows_in_sync_flags(self, client, api_token,
                                      policy_with_versions):
        p = policy_with_versions
        _report(client, api_token, machine="m-sync",
                content_hash=p["v2"]["content_hash"])
        _report(client, api_token, machine="m-stale",
                content_hash=p["v1"]["content_hash"])
        items = client.get("/api/v1/policy-state",
                           headers=_auth(api_token)).json()["items"]
        by_machine = {i["machine_id"]: i for i in items}
        assert by_machine["m-sync"]["in_sync"] is True
        assert by_machine["m-stale"]["in_sync"] is False

    def test_drift_returns_only_stale_rows(self, client, api_token,
                                           policy_with_versions):
        p = policy_with_versions
        _report(client, api_token, machine="m-sync",
                content_hash=p["v2"]["content_hash"])
        _report(client, api_token, machine="m-stale",
                content_hash=p["v1"]["content_hash"])
        body = client.get("/api/v1/policy-state/drift",
                          headers=_auth(api_token)).json()
        assert body["total"] == 1
        assert body["reported_total"] == 2
        assert body["items"][0]["machine_id"] == "m-stale"

    def test_activation_change_flips_drift_without_new_reports(
            self, client, api_token, policy_with_versions):
        """The core channel property: activating a NEW version instantly
        reclassifies every reported machine as drifted — no re-report
        needed. This is the policy-update-landed-who-is-behind query."""
        p = policy_with_versions
        _report(client, api_token, machine="m-1",
                content_hash=p["v2"]["content_hash"])
        assert client.get("/api/v1/policy-state/drift",
                          headers=_auth(api_token)).json()["total"] == 0
        v3 = client.post(f"/api/v1/policies/{p['policy_id']}/versions",
                         json={"content": {"text": "version three"}},
                         headers=_auth(api_token)).json()
        act = client.post(
            f"/api/v1/policies/{p['policy_id']}/activate/{v3['id']}",
            headers=_auth(api_token))
        assert act.status_code == 200, act.text
        drift = client.get("/api/v1/policy-state/drift",
                           headers=_auth(api_token)).json()
        assert drift["total"] == 1
        assert drift["items"][0]["active_version_number"] == v3["version_number"]

    def test_filters(self, client, api_token, policy_with_versions):
        p = policy_with_versions
        _report(client, api_token, machine="m-1",
                content_hash=p["v2"]["content_hash"], repo="local/a")
        _report(client, api_token, machine="m-2",
                content_hash=p["v2"]["content_hash"])
        items = client.get("/api/v1/policy-state?machine_id=m-1",
                           headers=_auth(api_token)).json()["items"]
        assert {i["machine_id"] for i in items} == {"m-1"}
        items = client.get("/api/v1/policy-state?repo=local/a",
                           headers=_auth(api_token)).json()["items"]
        assert len(items) == 1 and items[0]["repo_identifier"] == "local/a"


class TestActivePolicies:
    """GET /policies/active — the Phase 5b pull payload."""

    def test_returns_content_and_hash(self, client, api_token,
                                      policy_with_versions):
        p = policy_with_versions
        body = client.get("/api/v1/policies/active",
                          headers=_auth(api_token)).json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["slug"] == p["slug"]
        assert item["content_hash"] == p["v2"]["content_hash"]
        assert item["content"] == {"text": "version two"}
        assert item["version_number"] == p["v2"]["version_number"]

    def test_active_route_not_shadowed_by_policy_id(self, client, api_token):
        """ROUTE-ORDER TRIPWIRE pin: /policies/active must not be captured
        by /policies/{policy_id} (which would 400 on parse_uuid)."""
        r = client.get("/api/v1/policies/active", headers=_auth(api_token))
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0}

    def test_policy_without_activated_version_is_skipped(self, client,
                                                         api_token):
        r = client.post("/api/v1/policies",
                        json={"name": "Draft", "slug": "draft-policy"},
                        headers=_auth(api_token))
        assert r.status_code == 200
        body = client.get("/api/v1/policies/active",
                          headers=_auth(api_token)).json()
        assert body["total"] == 0


class TestClientPinWriters:
    """Phase 5b client half: the pin/landing writers, unit-tested directly
    (the pull command itself is smoke-tested against the live stack)."""

    _ITEMS = [{"policy_id": "x", "slug": "org-constitution", "name": "C",
               "version_number": 3,
               "content_hash": "a" * 64,
               "content": {"text": "hello"}}]

    def test_org_policies_landing_file(self, tmp_path):
        from gator_enterprise_cli.commands.policies import _write_org_policies
        import json as _json
        dest = _write_org_policies(tmp_path / "enterprise", self._ITEMS)
        data = _json.loads(dest.read_text(encoding="utf-8"))
        assert data["policies"][0]["content"] == {"text": "hello"}
        assert data["pulled_at"].endswith("Z")

    def test_policy_pin_shape_and_no_content(self, tmp_path):
        from gator_enterprise_cli.commands.policies import _write_policy_pin
        import json as _json
        gator = tmp_path / ".gator"
        gator.mkdir()
        dest = _write_policy_pin(gator, self._ITEMS, "machine-1")
        pin = _json.loads(dest.read_text(encoding="utf-8"))
        assert pin["schema"] == "gator-policy-pin-v1"
        assert pin["pulled_by_machine"] == "machine-1"
        assert pin["policies"] == [{"slug": "org-constitution",
                                    "version_number": 3,
                                    "content_hash": "a" * 64}]
        assert all(set(p.keys()) == {"slug", "version_number", "content_hash"}
                   for p in pin["policies"]), (
            "pin must carry hashes, never content")

    def test_pin_validates_against_contract(self, tmp_path):
        jsonschema = pytest.importorskip("jsonschema")
        import json as _json
        from pathlib import Path as _P
        from gator_enterprise_cli.commands.policies import _write_policy_pin
        gator = tmp_path / ".gator"
        gator.mkdir()
        dest = _write_policy_pin(gator, self._ITEMS, None)
        pin = _json.loads(dest.read_text(encoding="utf-8"))
        schema = _json.loads(
            (_P(__file__).resolve().parents[2] / "contracts" / "schemas" /
             "gator-policy-pin-v1.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(pin)
