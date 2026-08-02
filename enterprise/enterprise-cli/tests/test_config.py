"""Tests for CLI configuration — env var loading and precedence."""

import os
import sys

import pytest

from gator_enterprise_cli.config import CliConfig


class TestCliConfig:
    def test_loads_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("GATOR_ENTERPRISE_URL", "https://example.com")
        monkeypatch.setenv("GATOR_ENTERPRISE_TOKEN", "test-token-123")
        config = CliConfig.load()
        assert config.base_url == "https://example.com"
        assert config.token == "test-token-123"

    def test_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("GATOR_ENTERPRISE_URL", "https://example.com/")
        monkeypatch.setenv("GATOR_ENTERPRISE_TOKEN", "tok")
        config = CliConfig.load()
        assert config.base_url == "https://example.com"

    def test_flag_overrides_env(self, monkeypatch):
        monkeypatch.setenv("GATOR_ENTERPRISE_URL", "https://from-env.com")
        monkeypatch.setenv("GATOR_ENTERPRISE_TOKEN", "env-token")
        config = CliConfig.load(url_override="https://from-flag.com", token_override="flag-token")
        assert config.base_url == "https://from-flag.com"
        assert config.token == "flag-token"

    def test_missing_url_exits(self, monkeypatch):
        monkeypatch.delenv("GATOR_ENTERPRISE_URL", raising=False)
        monkeypatch.setenv("GATOR_ENTERPRISE_TOKEN", "tok")
        with pytest.raises(SystemExit):
            CliConfig.load()

    def test_missing_token_exits(self, monkeypatch):
        monkeypatch.setenv("GATOR_ENTERPRISE_URL", "https://example.com")
        monkeypatch.delenv("GATOR_ENTERPRISE_TOKEN", raising=False)
        with pytest.raises(SystemExit):
            CliConfig.load()
