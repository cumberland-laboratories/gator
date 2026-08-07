"""Regression tests for multi-session support in the vendor-session pipeline.

Covers the 2026-08-07 Issue B refactor: `.gator/active-vendor-session.json`
became a container of sessions (v2 schema) instead of a single entry,
with PID-based attribution and env-var override for cases where
multiple AI sessions coexist in the same repo.

Two files exercised:
- precommit_session.py:
    _read_active_vendor_sessions() — v1+v2 aware reader
    _pick_session_for_commit()      — attribution algorithm
    _walk_parent_pids() / _get_ppid — cross-platform PID walking
    _read_active_vendor_session()   — backwards-compat single-entry entry point
- gator-session-start.py:
    build_session_file()             — one v2 entry from vendor payload
    write_session_file()             — upsert into v2 container (migrates v1)

TRIPWIRE reminder from scripts-cross-cutting.md: attribution priority is
env var > PID walk > single-entry > transcript mtime > None. Changing
that order changes commit-to-session binding for every governed repo
and MUST come with a plan.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

# Load the two shipped modules by path so this test doesn't depend on
# them being installed as a package (they live under .gator/.includes/).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".gator" / ".includes" / "scripts"


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        module_name, _SCRIPTS_DIR / filename
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


precommit_session = _load("gator_precommit_session_mod", "precommit_session.py")
gator_session_start = _load("gator_session_start_mod", "gator-session-start.py")


def _write_avs_v1(gator_dir: Path, cwd: str, vendor_session_id: str = "s1"):
    """Write a legacy v1-schema active-vendor-session.json."""
    (gator_dir).mkdir(parents=True, exist_ok=True)
    path = gator_dir / "active-vendor-session.json"
    path.write_text(
        json.dumps(
            {
                "schema": "gator-active-vendor-session-v1",
                "vendor": "claude",
                "vendor_session_id": vendor_session_id,
                "model": "claude-opus-4-7",
                "transcript_path": "",
                "started_at": "2026-08-07T13:00:00Z",
                "cwd": cwd,
                "source": "session-start-hook",
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_avs_v2(gator_dir: Path, entries: list):
    """Write a v2-schema container with the given entries."""
    (gator_dir).mkdir(parents=True, exist_ok=True)
    path = gator_dir / "active-vendor-session.json"
    path.write_text(
        json.dumps(
            {"schema": "gator-active-vendor-sessions-v2", "sessions": entries}
        ),
        encoding="utf-8",
    )
    return path


def _entry(vendor_session_id, cwd, **extras):
    """Build a minimal v2 entry with `now` as the started_at default."""
    from datetime import datetime, timezone
    e = {
        "vendor": "claude",
        "vendor_session_id": vendor_session_id,
        "model": "claude-opus-4-7",
        "transcript_path": "",
        "started_at": datetime.now(timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd": cwd,
        "source": "session-start-hook",
    }
    e.update(extras)
    return e


class TestReadActiveVendorSessions:
    """The v1+v2 reader with cwd + freshness filtering."""

    def test_v1_file_returns_single_entry_list(self, tmp_path):
        repo = tmp_path / "repo"
        gd = repo / ".gator"
        _write_avs_v1(gd, str(repo), vendor_session_id="claude-abc")
        sessions = precommit_session._read_active_vendor_sessions(gd)
        assert len(sessions) == 1
        assert sessions[0]["vendor_session_id"] == "claude-abc"

    def test_v2_file_returns_all_valid_entries(self, tmp_path):
        repo = tmp_path / "repo"
        gd = repo / ".gator"
        _write_avs_v2(
            gd,
            [
                _entry("s-a", str(repo)),
                _entry("s-b", str(repo)),
            ],
        )
        sessions = precommit_session._read_active_vendor_sessions(gd)
        assert [s["vendor_session_id"] for s in sessions] == ["s-a", "s-b"]

    def test_missing_file_returns_empty(self, tmp_path):
        gd = tmp_path / "repo" / ".gator"
        gd.mkdir(parents=True)
        assert precommit_session._read_active_vendor_sessions(gd) == []

    def test_corrupt_file_returns_empty(self, tmp_path):
        gd = tmp_path / "repo" / ".gator"
        gd.mkdir(parents=True)
        (gd / "active-vendor-session.json").write_text("{ not json",
                                                       encoding="utf-8")
        assert precommit_session._read_active_vendor_sessions(gd) == []

    def test_unknown_schema_returns_empty(self, tmp_path):
        gd = tmp_path / "repo" / ".gator"
        gd.mkdir(parents=True)
        (gd / "active-vendor-session.json").write_text(
            json.dumps({"schema": "future-v99"}), encoding="utf-8"
        )
        assert precommit_session._read_active_vendor_sessions(gd) == []

    def test_wrong_repo_cwd_entry_dropped(self, tmp_path):
        repo = tmp_path / "repo_a"
        gd = repo / ".gator"
        # cwd points at a DIFFERENT repo — entry must be filtered out
        _write_avs_v2(
            gd,
            [_entry("s-wrong", str(tmp_path / "repo_b"))],
        )
        assert precommit_session._read_active_vendor_sessions(gd) == []

    def test_stale_started_at_dropped(self, tmp_path):
        repo = tmp_path / "repo"
        gd = repo / ".gator"
        _write_avs_v2(
            gd,
            [
                # 25 hours ago — outside the 24h window
                _entry(
                    "s-stale", str(repo),
                    started_at="2000-01-01T00:00:00Z",
                ),
                _entry("s-fresh", str(repo)),
            ],
        )
        ids = [s["vendor_session_id"]
               for s in precommit_session._read_active_vendor_sessions(gd)]
        assert ids == ["s-fresh"]

    def test_missing_vendor_session_id_dropped(self, tmp_path):
        repo = tmp_path / "repo"
        gd = repo / ".gator"
        e = _entry("keep-me", str(repo))
        # And one missing the id
        bad = _entry("", str(repo))
        del bad["vendor_session_id"]
        _write_avs_v2(gd, [e, bad])
        ids = [s["vendor_session_id"]
               for s in precommit_session._read_active_vendor_sessions(gd)]
        assert ids == ["keep-me"]


class TestPickSessionForCommit:
    """Attribution priority: env var > PID > single > mtime > None."""

    def test_empty_list_returns_none(self):
        assert precommit_session._pick_session_for_commit([]) is None

    def test_env_var_override_wins(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        entries = [
            _entry("s-a", str(repo)),
            _entry("s-b", str(repo)),
        ]
        monkeypatch.setenv("GATOR_TRANSCRIPT_SESSION_ID", "s-b")
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked["vendor_session_id"] == "s-b"

    def test_env_var_unknown_id_synthesizes_entry(self, tmp_path, monkeypatch):
        """Escape hatch for orchestrators managing session identity
        out-of-band: env var wins even if the id isn't in the file."""
        entries = [_entry("s-a", str(tmp_path))]
        monkeypatch.setenv("GATOR_TRANSCRIPT_SESSION_ID", "s-external")
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked["vendor_session_id"] == "s-external"
        assert picked["source"] == "env-override"

    def test_single_entry_short_circuits(self, tmp_path, monkeypatch):
        # No env var set
        monkeypatch.delenv("GATOR_TRANSCRIPT_SESSION_ID", raising=False)
        entries = [_entry("only-one", str(tmp_path))]
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked["vendor_session_id"] == "only-one"

    def test_two_entries_pid_match_wins(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GATOR_TRANSCRIPT_SESSION_ID", raising=False)
        # Fake the PID walker to return a known ancestor set
        fake_ancestors = [111, 222, 333]
        monkeypatch.setattr(
            precommit_session, "_walk_parent_pids", lambda: fake_ancestors
        )
        entries = [
            _entry("s-a", str(tmp_path), owner_pid=999),   # not in tree
            _entry("s-b", str(tmp_path), owner_pid=222),   # in tree
        ]
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked["vendor_session_id"] == "s-b"

    def test_two_entries_no_pid_match_falls_to_mtime(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("GATOR_TRANSCRIPT_SESSION_ID", raising=False)
        monkeypatch.setattr(
            precommit_session, "_walk_parent_pids", lambda: []
        )
        # Two transcript files, second one modified more recently
        t1 = tmp_path / "t1.jsonl"
        t2 = tmp_path / "t2.jsonl"
        t1.write_text("first", encoding="utf-8")
        t2.write_text("second", encoding="utf-8")
        # Force t2's mtime to be newer than t1's
        os.utime(str(t1), (time.time() - 1000, time.time() - 1000))
        os.utime(str(t2), (time.time(), time.time()))
        entries = [
            _entry("s-old", str(tmp_path), transcript_path=str(t1)),
            _entry("s-new", str(tmp_path), transcript_path=str(t2)),
        ]
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked["vendor_session_id"] == "s-new"

    def test_no_attribution_signal_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GATOR_TRANSCRIPT_SESSION_ID", raising=False)
        monkeypatch.setattr(
            precommit_session, "_walk_parent_pids", lambda: []
        )
        # 2+ entries, no PID match, no transcript_path anywhere
        entries = [
            _entry("s-a", str(tmp_path)),
            _entry("s-b", str(tmp_path)),
        ]
        assert precommit_session._pick_session_for_commit(entries) is None


class TestPidWalker:
    """Cross-platform PID walking. Skipped on platforms where the
    subprocess helpers can't run."""

    def test_walk_returns_at_least_one_ancestor(self):
        ancestors = precommit_session._walk_parent_pids()
        # pytest runs under python which runs under a shell — at least
        # ONE ancestor is expected. If empty, the walker's failing
        # (which itself would be worth catching).
        assert isinstance(ancestors, list)
        assert len(ancestors) >= 1

    def test_walk_respects_max_depth(self):
        ancestors = precommit_session._walk_parent_pids(max_depth=1)
        assert len(ancestors) <= 1

    def test_walker_bounds_infinite_chains(self):
        """The bounded depth is what protects us from a stuck loop —
        verify by asking for depth 0 (should be empty)."""
        assert precommit_session._walk_parent_pids(max_depth=0) == []

    def test_unreachable_pid_returns_none_or_zero(self):
        """PID 0 has slightly different semantics per-platform.
        Unix `ps` errors → None. Windows PowerShell's CIM query for
        the system idle process returns its ppid (0) as an integer.
        Either is fine — the loop in _walk_parent_pids terminates on
        both `None` and `0`."""
        result = precommit_session._get_ppid(0)
        assert result in (None, 0), (
            f"_get_ppid(0) returned unexpected value {result!r}; "
            "must be either None (Unix) or 0 (Windows)"
        )


class TestWriteSessionFile:
    """Upsert behavior of the v2 container writer."""

    def _read_container(self, gator_dir):
        return json.loads(
            (gator_dir / "active-vendor-session.json").read_text(encoding="utf-8")
        )

    def test_fresh_write_creates_v2_container(self, tmp_path):
        gd = tmp_path / ".gator"
        gd.mkdir()
        entry = _entry("s-first", str(tmp_path))
        gator_session_start.write_session_file(gd, entry)
        data = self._read_container(gd)
        assert data["schema"] == "gator-active-vendor-sessions-v2"
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["vendor_session_id"] == "s-first"

    def test_second_write_different_session_preserves_first(self, tmp_path):
        gd = tmp_path / ".gator"
        gd.mkdir()
        gator_session_start.write_session_file(
            gd, _entry("s-a", str(tmp_path))
        )
        gator_session_start.write_session_file(
            gd, _entry("s-b", str(tmp_path))
        )
        data = self._read_container(gd)
        ids = [s["vendor_session_id"] for s in data["sessions"]]
        assert ids == ["s-a", "s-b"]

    def test_second_write_same_session_id_upserts(self, tmp_path):
        gd = tmp_path / ".gator"
        gd.mkdir()
        gator_session_start.write_session_file(
            gd, _entry("s-a", str(tmp_path), model="claude-opus-4-7")
        )
        # Re-register same session with different model (upgrade path)
        gator_session_start.write_session_file(
            gd, _entry("s-a", str(tmp_path), model="claude-opus-5")
        )
        data = self._read_container(gd)
        # ONE entry, updated model
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["model"] == "claude-opus-5"

    def test_v1_file_migrates_to_v2_on_write(self, tmp_path):
        gd = tmp_path / ".gator"
        _write_avs_v1(gd, str(tmp_path), vendor_session_id="v1-legacy")
        gator_session_start.write_session_file(
            gd, _entry("v2-new", str(tmp_path))
        )
        data = self._read_container(gd)
        assert data["schema"] == "gator-active-vendor-sessions-v2"
        ids = sorted(s["vendor_session_id"] for s in data["sessions"])
        assert ids == ["v1-legacy", "v2-new"]

    def test_stale_entries_dropped_on_write(self, tmp_path):
        gd = tmp_path / ".gator"
        # Pre-seed a stale v2 container
        _write_avs_v2(
            gd,
            [
                _entry(
                    "s-stale", str(tmp_path),
                    started_at="2000-01-01T00:00:00Z",
                ),
                _entry("s-fresh-existing", str(tmp_path)),
            ],
        )
        gator_session_start.write_session_file(
            gd, _entry("s-new", str(tmp_path))
        )
        data = self._read_container(gd)
        ids = sorted(s["vendor_session_id"] for s in data["sessions"])
        assert ids == ["s-fresh-existing", "s-new"]
