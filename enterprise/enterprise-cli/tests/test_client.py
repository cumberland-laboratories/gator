"""Tests for CLI HTTP client — auth headers, error mapping, response handling."""

import json

import pytest
import httpx

from gator_enterprise_cli.client import CliError, EnterpriseClient
from gator_enterprise_cli.config import CliConfig


@pytest.fixture
def config():
    return CliConfig(base_url="https://test.example.com", token="test-token")


@pytest.fixture
def client(config):
    return EnterpriseClient(config)


class TestAuthHeaderInjection:
    def test_headers_include_bearer_token(self, client):
        assert client._headers["Authorization"] == "Bearer test-token"

    def test_headers_include_content_type(self, client):
        assert client._headers["Content-Type"] == "application/json"


class TestErrorMapping:
    def test_maps_error_envelope(self, client, httpx_mock):
        """API error envelope is extracted into CliError message."""
        # We can't easily mock httpx here without httpx-mock, so test
        # the _handle_response method directly with a mock response.
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {
            "error": {"code": "unauthorized", "message": "Invalid token"},
            "request_id": "abc-123",
        }
        resp.text = '{"error": ...}'

        with pytest.raises(CliError) as exc_info:
            client._handle_response(resp)
        assert "401" in exc_info.value.message
        assert "unauthorized" in exc_info.value.message
        assert "Invalid token" in exc_info.value.message

    def test_maps_non_json_error(self, client):
        """Non-JSON error response falls back to raw text."""
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.status_code = 502
        resp.json.side_effect = ValueError("not json")
        resp.text = "Bad Gateway"

        with pytest.raises(CliError) as exc_info:
            client._handle_response(resp)
        assert "502" in exc_info.value.message

    def test_success_returns_json(self, client):
        """2xx responses return parsed JSON."""
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "ok"}

        result = client._handle_response(resp)
        assert result == {"status": "ok"}


# Remove httpx_mock fixture since we're not using pytest-httpx
@pytest.fixture
def httpx_mock():
    """Dummy fixture — real HTTP mocking not needed for _handle_response tests."""
    return None
