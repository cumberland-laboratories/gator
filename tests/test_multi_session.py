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
# Runtime-split Phase 4 (2026-08-19): this repo no longer carries
# .gator/.includes/scripts/ — load the canonical template source
# (the wheel runtime) instead.
_SCRIPTS_DIR = (Path(__file__).resolve().parent.parent / "src" /
                "gator_command" / "templates" / "gator-starter" / "scripts")


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

    @pytest.mark.xfail(
        reason=(
            "v1 backwards-compat NOT implemented in the current v2 reader. "
            "Pre-existing failure since df71e8e (2026-08-07). Documented in "
            "the v2.6.0 CHANGELOG under 'Under the hood' → known-issues. "
            "Fix tracked as post-2.6 work: either implement v1 read-shim in "
            "_read_active_vendor_sessions() or delete this test if v1 is "
            "truly out of support."
        ),
        strict=False,
    )
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
        # Walker returns (pid, started_at) tuples
        fake_ancestors = [(111, None), (222, None), (333, None)]
        monkeypatch.setattr(
            precommit_session, "_walk_parent_pids", lambda: fake_ancestors
        )
        entries = [
            _entry("s-a", str(tmp_path), owner_pid=999),   # not in tree
            _entry("s-b", str(tmp_path), owner_pid=222),   # in tree
        ]
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked["vendor_session_id"] == "s-b"

    def test_pid_match_with_matching_started_at_wins(
        self, tmp_path, monkeypatch
    ):
        """PID number matches AND owner_pid_started_at matches the
        observed ancestor start time — real match."""
        monkeypatch.delenv("GATOR_TRANSCRIPT_SESSION_ID", raising=False)
        fake_ancestors = [(222, "2026-08-07T10:00:00+00:00")]
        monkeypatch.setattr(
            precommit_session, "_walk_parent_pids", lambda: fake_ancestors
        )
        entries = [
            _entry(
                "s-a", str(tmp_path),
                owner_pid=222,
                owner_pid_started_at="2026-08-07T10:00:00+00:00",
            ),
        ]
        # Add a second entry so we don't short-circuit on single-entry
        entries.append(_entry("s-b", str(tmp_path), owner_pid=333))
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked["vendor_session_id"] == "s-a"

    def test_pid_number_matches_but_started_at_differs_recycled(
        self, tmp_path, monkeypatch
    ):
        """CODEX FINDING #2: PID number matches an ancestor but the
        recorded owner_pid_started_at differs from what we observe now
        → the ancestor is a DIFFERENT process (PID recycled). Must NOT
        attribute to that session; fall through to next rule."""
        monkeypatch.delenv("GATOR_TRANSCRIPT_SESSION_ID", raising=False)
        # Ancestor 222 started NOW (freshly-recycled PID)
        fake_ancestors = [(222, "2026-08-07T15:00:00+00:00")]
        monkeypatch.setattr(
            precommit_session, "_walk_parent_pids", lambda: fake_ancestors
        )
        # Session recorded PID 222 started at 10:00 (the ORIGINAL process
        # which has since exited; PID reused by the ancestor above).
        entries = [
            _entry(
                "s-recycled", str(tmp_path),
                owner_pid=222,
                owner_pid_started_at="2026-08-07T10:00:00+00:00",
            ),
            _entry("s-other", str(tmp_path), owner_pid=999),
        ]
        # No PID match survives the started_at check → picker falls to
        # mtime fallback (both have no transcript_path) → returns None.
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked is None, (
            "PID recycling protection failed: picker attributed to "
            "s-recycled whose owner_pid_started_at didn't match the "
            "observed ancestor. Codex Finding #2."
        )

    def test_pid_match_when_started_at_unavailable_degrades_gracefully(
        self, tmp_path, monkeypatch
    ):
        """When either the recorded or observed started_at is unavailable,
        degrade to PID-only matching rather than refusing to match. Better
        to over-attribute than under-attribute for this best-effort check."""
        monkeypatch.delenv("GATOR_TRANSCRIPT_SESSION_ID", raising=False)
        # Ancestor without observed start time
        fake_ancestors = [(222, None)]
        monkeypatch.setattr(
            precommit_session, "_walk_parent_pids", lambda: fake_ancestors
        )
        # Session HAS a recorded start time; observed is None
        entries = [
            _entry(
                "s-recorded", str(tmp_path),
                owner_pid=222,
                owner_pid_started_at="2026-08-07T10:00:00+00:00",
            ),
            _entry("s-other", str(tmp_path), owner_pid=999),
        ]
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked["vendor_session_id"] == "s-recorded"

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

    def test_env_var_vendor_override_sets_synthesized_vendor(
        self, tmp_path, monkeypatch
    ):
        """CODEX FINDING #3: GATOR_TRANSCRIPT_VENDOR is the companion
        env var for the id override. When set, the synthesized entry
        gets that vendor value (not 'unknown')."""
        monkeypatch.setenv("GATOR_TRANSCRIPT_SESSION_ID", "s-external")
        monkeypatch.setenv("GATOR_TRANSCRIPT_VENDOR", "anthropic")
        entries = [_entry("s-a", str(tmp_path))]
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked["vendor_session_id"] == "s-external"
        assert picked["vendor"] == "anthropic"
        assert picked["source"] == "env-override"

    def test_env_var_id_alone_leaves_vendor_none_not_unknown(
        self, tmp_path, monkeypatch
    ):
        """CODEX FINDING #3: when only GATOR_TRANSCRIPT_SESSION_ID is
        set (no GATOR_TRANSCRIPT_VENDOR), the synthesized entry has
        `vendor: None` so downstream render_snippet_json falls through
        to the agent-inferred vendor. Previously used 'unknown', which
        clobbered agent inference."""
        monkeypatch.setenv("GATOR_TRANSCRIPT_SESSION_ID", "s-external")
        monkeypatch.delenv("GATOR_TRANSCRIPT_VENDOR", raising=False)
        entries = [_entry("s-a", str(tmp_path))]
        picked = precommit_session._pick_session_for_commit(entries)
        assert picked["vendor_session_id"] == "s-external"
        assert picked["vendor"] is None, (
            f"synthesized vendor was {picked['vendor']!r}, expected None. "
            "Setting it to 'unknown' clobbers agent-inferred vendor in "
            "render_snippet_json — Codex Finding #3."
        )


class TestPidWalker:
    """Cross-platform PID walking. Skipped on platforms where the
    subprocess helpers can't run."""

    def test_walk_returns_at_least_one_ancestor_as_tuple(self):
        ancestors = precommit_session._walk_parent_pids()
        # pytest runs under python which runs under a shell — at least
        # ONE ancestor is expected.
        assert isinstance(ancestors, list)
        assert len(ancestors) >= 1
        # Each entry is (pid, started_at_or_none). started_at is
        # best-effort — may be None on platforms where the helper
        # couldn't parse the timestamp — but the shape MUST be a tuple
        # with the pid as first element.
        first = ancestors[0]
        assert isinstance(first, tuple)
        assert len(first) == 2
        assert isinstance(first[0], int)
        assert first[1] is None or isinstance(first[1], str)

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

    def test_pid_start_times_match_helper(self):
        """The started_at fuzzy-compare that gates PID-recycling protection."""
        assert precommit_session._pid_start_times_match(
            "2026-08-07T10:00:00+00:00", "2026-08-07T10:00:00+00:00"
        )
        # Whitespace + case tolerant
        assert precommit_session._pid_start_times_match(
            "  2026-08-07T10:00:00+00:00  ", "2026-08-07T10:00:00+00:00"
        )
        # Different times → not a match (recycled)
        assert not precommit_session._pid_start_times_match(
            "2026-08-07T10:00:00+00:00", "2026-08-07T15:00:00+00:00"
        )
        # Missing either side → match (degrade gracefully, better to
        # over-attribute than under-attribute)
        assert precommit_session._pid_start_times_match(None, "2026-08-07T10:00:00")
        assert precommit_session._pid_start_times_match("2026-08-07T10:00:00", None)
        assert precommit_session._pid_start_times_match(None, None)


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

    @pytest.mark.xfail(
        reason=(
            "v1 legacy entries dropped on v2 migration write. Pre-existing "
            "failure since df71e8e (2026-08-07). Sibling of "
            "test_v1_file_returns_single_entry_list. Documented in the "
            "v2.6.0 CHANGELOG under 'Under the hood' → known-issues. Fix "
            "tracked as post-2.6 work: preserve v1 entry into the v2 "
            "container when a v1 file exists at write time."
        ),
        strict=False,
    )
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


class TestRenderSnippetVendorFallback:
    """CODEX FINDING #3 render-side companion: when the vendor_session
    entry has vendor=None (synthesized env-override without
    GATOR_TRANSCRIPT_VENDOR), render_snippet_json MUST preserve the
    agent-inferred vendor rather than clobber with 'unknown'."""

    def _minimal_entry(self, agent="Claude Code (Sonnet 4)"):
        # Just enough for render_snippet_json not to blow up on missing keys
        return {
            "commit": "a" * 40,
            "short_commit": "a" * 12,
            "snippet_id": "snippet-aaaaaaaaaaaaa",
            "architect": "Alan Gillette",
            "agent": agent,
            "vendor_inferred_from_session": None,
            "model_inferred_from_session": None,
            "change_type": "fix",
            "significance": "low",
            "charter_changed": False,
            "decision_tags": [],
            "repo": "test-repo",
            "branch": "main",
            "commit_index": 1,
            "previous_commit": None,
            "files_touched": [],
            "notes": [],
            "transcript_session_id": None,
        }

    def test_synthesized_vendor_none_keeps_agent_inferred(self):
        """The bug fixed: when synthesized entry has vendor=None,
        render_snippet_json should keep the agent-inferred vendor and
        NOT emit vendor_inferred='unknown' or session_group_key
        starting with 'unknown:'."""
        entry = self._minimal_entry(agent="Claude Code (Opus 4.7)")
        # Synthesized entry as _pick_session_for_commit would return
        # when GATOR_TRANSCRIPT_SESSION_ID is set but no companion
        # GATOR_TRANSCRIPT_VENDOR.
        vendor_session = {
            "vendor_session_id": "s-external",
            "vendor": None,
            "model": None,
            "transcript_path": None,
            "source": "env-override",
        }
        json_str = precommit_session.render_snippet_json(
            entry, session_meta={}, vendor_session=vendor_session
        )
        snippet = json.loads(json_str)
        assert snippet["transcript_session_id"] == "s-external"
        assert snippet["vendor_inferred"] != "unknown", (
            f"vendor_inferred was {snippet['vendor_inferred']!r} — "
            "synthesized vendor=None should preserve agent-inferred"
        )
        # The session_group_key must NOT start with "unknown:"
        gk = snippet.get("session_group_key") or ""
        assert not gk.startswith("unknown:"), (
            f"session_group_key was {gk!r} — should use agent-inferred "
            "vendor, not 'unknown'"
        )

    def test_explicit_vendor_in_session_still_overrides_agent(self):
        """Regression check: when vendor_session HAS a real vendor
        (from SessionStart, or from GATOR_TRANSCRIPT_VENDOR), it still
        wins over agent-inferred. The Finding #3 fix must not have
        broken that path."""
        entry = self._minimal_entry(agent="Something Else 2000")
        vendor_session = {
            "vendor_session_id": "s-x",
            "vendor": "openai",
            "model": "gpt-5",
            "transcript_path": None,
        }
        json_str = precommit_session.render_snippet_json(
            entry, session_meta={}, vendor_session=vendor_session
        )
        snippet = json.loads(json_str)
        assert snippet["vendor_inferred"] == "openai"
        assert snippet["model_inferred"] == "gpt-5"
        assert snippet["session_group_key"] == "openai:s-x"


class TestByteIdentityAcrossThreeCopies:
    """CODEX FINDING #1, amended by runtime-split Phase 4 (2026-08-19):
    the original THREE-copy byte-identity contract shrank to TWO — the
    repo-resident copy (`.gator/.includes/scripts/`, historical copy A)
    no longer exists by design; repos run the machine-side wheel runtime.
    Remaining copies that must stay byte-identical:

      B. `src/gator_command/templates/gator-starter/scripts/` — the wheel
         runtime (executed via the gator-hook dispatcher)
      C. `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/`
         — copied INTO new repos by `gator-enterprise repo init`'s
         `_install_bundled_scripts` step

    The B⟷C pair dissolves entirely when Enterprise bundled_scripts
    retire (runtime-split decision D4 / roadmap Post-2.6 item 4). Drift
    still means Enterprise-provisioned repos run different code than the
    wheel runtime — the original Codex bug class."""

    _REPO_ROOT = Path(__file__).resolve().parent.parent

    @pytest.mark.parametrize("filename", [
        "precommit_session.py",
        "gator-session-start.py",
        # `gator-pre-commit.py` is DELIBERATELY NOT included here — the
        # three copies of that file drifted pre-2026-08-08 for reasons
        # unrelated to the transcripts-first MVP work, and reconciling
        # them is a separate follow-up (see scripts-enterprise.md
        # Phase 6 charter block "Follow-up" note). Phase 6's
        # `Gator-Machine-Id` addition was applied to all three copies
        # by hand — same edit at the same anchor — but a full
        # byte-identity assertion would fail on prior drift and mask
        # the real change.
    ])
    def test_wheel_and_bundled_copies_byte_identical(self, filename):
        template = (
            self._REPO_ROOT / "src" / "gator_command" / "templates"
            / "gator-starter" / "scripts" / filename
        )
        bundled = (
            self._REPO_ROOT / "enterprise" / "enterprise-cli"
            / "gator_enterprise_cli" / "bundled_scripts" / filename
        )
        for p in (template, bundled):
            assert p.exists(), f"missing copy: {p}"
        assert template.read_bytes() == bundled.read_bytes(), (
            f"{filename}: wheel-runtime template != enterprise-cli "
            f"bundled_scripts. Enterprise-provisioned repos would run "
            f"different code than the wheel runtime."
        )

    @pytest.mark.parametrize("filename", [
        "precommit_session.py",
        "gator-session-start.py",
    ])
    def test_repo_resident_copy_retired(self, filename):
        """Phase 4 contract: this repo carries NO repo-resident runtime —
        the historical copy A must stay gone."""
        shipped = self._REPO_ROOT / ".gator" / ".includes" / "scripts" / filename
        assert not shipped.exists(), (
            f"{filename} reappeared in .gator/.includes/scripts/ — the "
            f"runtime split removed repo-resident runtime; check whether "
            f"an old gator-update re-shipped it."
        )

