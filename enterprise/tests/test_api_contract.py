"""Tests for centralized API contract — parsers and error types."""

import uuid
from datetime import datetime

import pytest

from app.api_contract import (
    ApiError,
    RateLimitError,
    parse_enum,
    parse_iso_datetime,
    parse_uuid,
)


class TestParseUuid:
    def test_valid_uuid(self):
        result = parse_uuid("550e8400-e29b-41d4-a716-446655440000")
        assert isinstance(result, uuid.UUID)

    def test_invalid_string(self):
        with pytest.raises(ApiError) as exc_info:
            parse_uuid("not-a-uuid")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_parameter"
        assert "not-a-uuid" in exc_info.value.message

    def test_empty_string(self):
        with pytest.raises(ApiError):
            parse_uuid("")

    def test_custom_label(self):
        with pytest.raises(ApiError) as exc_info:
            parse_uuid("bad", "repo_id")
        assert "repo_id" in exc_info.value.message


class TestParseIsoDatetime:
    def test_valid_date(self):
        result = parse_iso_datetime("2026-07-11T14:30:00Z")
        assert isinstance(result, datetime)

    def test_none_returns_none(self):
        assert parse_iso_datetime(None) is None

    def test_invalid_date(self):
        with pytest.raises(ApiError) as exc_info:
            parse_iso_datetime("not-a-date")
        assert exc_info.value.status_code == 400

    def test_custom_label(self):
        with pytest.raises(ApiError) as exc_info:
            parse_iso_datetime("bad", "since")
        assert "since" in exc_info.value.message


class TestParseEnum:
    def test_valid_value(self):
        result = parse_enum("aligned", {"aligned", "drifting"})
        assert result == "aligned"

    def test_none_returns_none(self):
        assert parse_enum(None, {"a", "b"}) is None

    def test_invalid_value(self):
        with pytest.raises(ApiError) as exc_info:
            parse_enum("bad", {"aligned", "drifting"}, "compliance")
        assert exc_info.value.status_code == 400
        assert "compliance" in exc_info.value.message


class TestApiError:
    def test_basic(self):
        err = ApiError(400, "invalid_parameter", "Bad input")
        assert err.status_code == 400
        assert err.code == "invalid_parameter"
        assert err.headers is None

    def test_with_headers(self):
        err = ApiError(429, "rate_limited", "Too fast", headers={"Retry-After": "5"})
        assert err.headers == {"Retry-After": "5"}


class TestRateLimitError:
    def test_creates_retry_after_header(self):
        err = RateLimitError(retry_after=4.7, bucket="views.timeline")
        assert err.status_code == 429
        assert err.code == "rate_limited"
        assert err.headers == {"Retry-After": "4"}
        assert "views.timeline" in err.message
