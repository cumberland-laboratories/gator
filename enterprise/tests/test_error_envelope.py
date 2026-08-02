"""Tests for error envelope consistency and request ID propagation.

Uses FastAPI TestClient to verify the full HTTP layer.
The auth-dependent tests override get_db to use an in-memory SQLite
database so verify_token() runs its real code path.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.base import Base


@pytest.fixture
def client():
    """TestClient with get_db overridden to use in-memory SQLite.

    Uses StaticPool to share a single connection across threads —
    required because TestClient runs requests in a different thread
    and SQLite in-memory DBs are per-connection.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _override_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestErrorEnvelope:
    """Every error response follows the envelope format."""

    def test_unmatched_path_returns_envelope_404(self, client):
        """Router-level 404 — proves starlette.exceptions.HTTPException handler."""
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "not_found"
        assert "request_id" in body

    def test_wrong_method_returns_envelope_405(self, client):
        """Starlette 405 — proves framework-level normalization."""
        resp = client.delete("/api/v1/views/fleet")
        assert resp.status_code == 405
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "method_not_allowed"
        assert "request_id" in body

    def test_no_auth_returns_envelope_401(self, client):
        """Missing Authorization header via HTTPBearer(auto_error=False)."""
        resp = client.get("/api/v1/views/fleet")
        assert resp.status_code == 401
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "unauthorized"
        assert "request_id" in body

    def test_bad_token_returns_envelope_401(self, client):
        """Invalid bearer token — token hash not found in DB.
        Uses in-memory SQLite so verify_token() runs its real code path
        and returns 401 (not 500 from missing DB).
        """
        resp = client.get(
            "/api/v1/views/fleet",
            headers={"Authorization": "Bearer invalid-token-value"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "unauthorized"
        assert "Invalid or expired token" in body["error"]["message"]
        assert "request_id" in body


class TestRequestId:
    """X-Request-ID header propagation."""

    def test_response_includes_request_id_header(self, client):
        resp = client.get("/healthz")
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) > 0

    def test_echoes_provided_request_id(self, client):
        resp = client.get("/healthz", headers={"X-Request-ID": "trace-abc-123"})
        assert resp.headers["X-Request-ID"] == "trace-abc-123"

    def test_error_response_includes_request_id_in_body(self, client):
        resp = client.get("/api/v1/nonexistent")
        body = resp.json()
        assert "request_id" in body
        assert len(body["request_id"]) > 0

    def test_request_id_matches_header_and_body(self, client):
        """The request_id in the error body should match X-Request-ID header."""
        resp = client.get("/api/v1/nonexistent")
        header_id = resp.headers.get("X-Request-ID", "")
        body_id = resp.json().get("request_id", "")
        assert header_id == body_id
