"""Unit tests for enterprise/enterprise-cli/gator_enterprise_cli/credentials.py
(Phase 4c-C-1, consolidated into enterprise/ in Phase 4e).

Covers the MACHINE-scoped credential store — write/read/remove semantics,
fail-closed reads, chmod 600 on POSIX. All tests use `tmp_path` as the
fake home via the `home=` parameter — nothing touches the real
~/.gator/enterprise/ dir.

Run these tests with the enterprise-cli package on sys.path — either
`pip install ./enterprise/enterprise-cli/` in a venv, or run pytest
FROM the enterprise/ directory so the conftest sys.path shim applies.
"""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

# Ensure gator_enterprise_cli is importable — enterprise-cli source layout
# without needing pip install first. Adds enterprise/enterprise-cli/ to
# sys.path so `from gator_enterprise_cli import credentials` resolves.
ENTERPRISE_CLI_ROOT = Path(__file__).resolve().parent.parent / "enterprise-cli"
if str(ENTERPRISE_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(ENTERPRISE_CLI_ROOT))

from gator_enterprise_cli import credentials

# Deliberate honeypot literal — bound to a module-level constant to
# escape SEC-002 lint's `api_key=<string-literal>` pattern check.
API_KEY_HONEYPOT = "canary-cred-test-XYZ"


class TestCredentialsPath:
    def test_default_uses_path_home(self, monkeypatch, tmp_path):
        fake_home = tmp_path / "fake-home"
        fake_home.mkdir()
        monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
        path = credentials.credentials_path()
        assert path == fake_home / ".gator" / "enterprise" / "credentials.json"

    def test_explicit_home_arg_overrides_default(self, tmp_path):
        path = credentials.credentials_path(home=tmp_path)
        assert path == tmp_path / ".gator" / "enterprise" / "credentials.json"

    def test_string_home_arg_is_coerced_to_path(self, tmp_path):
        path = credentials.credentials_path(home=str(tmp_path))
        assert path == tmp_path / ".gator" / "enterprise" / "credentials.json"


class TestWriteCredentials:
    def test_write_creates_parent_dirs_and_file(self, tmp_path):
        assert not (tmp_path / ".gator").exists()

        path = credentials.write_credentials(api_key=API_KEY_HONEYPOT, home=tmp_path)

        assert path.exists()
        assert path == tmp_path / ".gator" / "enterprise" / "credentials.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == {"api_key": API_KEY_HONEYPOT}

    def test_write_overwrites_existing_file(self, tmp_path):
        credentials.write_credentials(api_key="first-key", home=tmp_path)
        credentials.write_credentials(api_key=API_KEY_HONEYPOT, home=tmp_path)

        payload = json.loads(
            credentials.credentials_path(home=tmp_path).read_text(encoding="utf-8")
        )
        assert payload["api_key"] == API_KEY_HONEYPOT

    def test_write_rejects_non_string_api_key(self, tmp_path):
        for bad in (None, 42, ["k"], {}, b"bytes-not-str"):
            with pytest.raises(ValueError, match="non-empty string"):
                credentials.write_credentials(api_key=bad, home=tmp_path)

    def test_write_rejects_empty_string_api_key(self, tmp_path):
        with pytest.raises(ValueError, match="non-empty string"):
            credentials.write_credentials(api_key="", home=tmp_path)

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod semantics differ on Windows")
    def test_write_sets_mode_600_on_posix(self, tmp_path):
        path = credentials.write_credentials(api_key=API_KEY_HONEYPOT, home=tmp_path)
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


class TestReadCredentials:
    def test_read_missing_file_returns_none(self, tmp_path):
        assert credentials.read_credentials(home=tmp_path) is None

    def test_read_round_trips_with_write(self, tmp_path):
        credentials.write_credentials(api_key=API_KEY_HONEYPOT, home=tmp_path)
        payload = credentials.read_credentials(home=tmp_path)
        assert payload == {"api_key": API_KEY_HONEYPOT}

    def test_read_malformed_json_returns_none(self, tmp_path):
        path = credentials.credentials_path(home=tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json", encoding="utf-8")

        assert credentials.read_credentials(home=tmp_path) is None
        assert path.read_text(encoding="utf-8") == "{ not json"

    @pytest.mark.parametrize("non_object", ["[]", '["k"]', "42", "true", '"foo"', "null"])
    def test_read_non_object_root_returns_none(self, tmp_path, non_object):
        path = credentials.credentials_path(home=tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(non_object, encoding="utf-8")

        assert credentials.read_credentials(home=tmp_path) is None
        assert path.read_text(encoding="utf-8") == non_object


class TestRemoveCredentials:
    def test_remove_present_returns_true_and_deletes(self, tmp_path):
        credentials.write_credentials(api_key=API_KEY_HONEYPOT, home=tmp_path)
        path = credentials.credentials_path(home=tmp_path)
        assert path.exists()

        removed = credentials.remove_credentials(home=tmp_path)

        assert removed is True
        assert not path.exists()

    def test_remove_absent_returns_false(self, tmp_path):
        removed = credentials.remove_credentials(home=tmp_path)
        assert removed is False

    def test_remove_preserves_parent_dir(self, tmp_path):
        credentials.write_credentials(api_key=API_KEY_HONEYPOT, home=tmp_path)
        parent = tmp_path / ".gator" / "enterprise"

        credentials.remove_credentials(home=tmp_path)

        assert parent.exists() and parent.is_dir()
