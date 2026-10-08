"""
Tests for gator-state.py (schema gator-state-v2).

Covers constitution drift + source-repo exemption + version diagnostic, the
informational native-file view (never drift, never managed), the no-write
`repair` compatibility stub, and the *.local.md never-opened invariant.
"""

import json
import shutil
import types
from pathlib import Path

import pytest

from conftest import load_script

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "templates" / "gator-starter"

state_mod = load_script("gator-state", search_dir=SCRIPTS_DIR)


# ---------------------------------------------------------------------------

def _make_governed_repo(tmp_path, layout="v1"):
    """Create a minimal .gator/ tree so find_gator_root() works and
    resolve_template_source() finds the shipped templates."""
    repo = tmp_path / "repo"
    gator = repo / ".gator"
    gator.mkdir(parents=True)

    # product-source.json → points at our real shipped templates so baseline
    # resolution matches production.
    ps = {
        "gator_root": str(TEMPLATES_DIR.parent.parent),  # …/src/gator_command
        "template_dir": "templates/gator-starter",
        "installed": "2026-07-29",
        "updated": "2026-07-29",
    }
    (gator / "product-source.json").write_text(json.dumps(ps), encoding="utf-8")

    # constitution.md at the layout-appropriate path (defaults to v1 — flat root)
    constitution_src = TEMPLATES_DIR / "constitution.md"
    if layout == "v2":
        (gator / ".includes").mkdir()
        (gator / ".includes" / "constitution.md").write_bytes(constitution_src.read_bytes())
    else:
        (gator / "constitution.md").write_bytes(constitution_src.read_bytes())

    return repo


class TestSourceRepoDetection:
    def test_true_when_both_files_present(self, tmp_path):
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        (tmp_path / "constitution.md").write_text("y")
        assert state_mod.is_source_repo(tmp_path) is True

    def test_false_when_only_mission_present(self, tmp_path):
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        assert state_mod.is_source_repo(tmp_path) is False

    def test_false_when_only_constitution_present(self, tmp_path):
        (tmp_path / "constitution.md").write_text("y")
        assert state_mod.is_source_repo(tmp_path) is False

    def test_false_on_empty_repo(self, tmp_path):
        assert state_mod.is_source_repo(tmp_path) is False


class TestLocalCompanionPresent:
    def test_true_when_file_exists(self, tmp_path):
        (tmp_path / "CLAUDE.local.md").write_text("private notes")
        assert state_mod.local_companion_present(tmp_path, "CLAUDE.md") is True

    def test_false_when_missing(self, tmp_path):
        assert state_mod.local_companion_present(tmp_path, "CLAUDE.md") is False

    def test_derives_stem_from_filename(self, tmp_path):
        (tmp_path / "AGENTS.local.md").write_text("x")
        assert state_mod.local_companion_present(tmp_path, "AGENTS.md") is True
        assert state_mod.local_companion_present(tmp_path, "GEMINI.md") is False


class TestReadRepoGatorVersion:
    def test_reads_cli_version(self, tmp_path):
        (tmp_path / ".gator").mkdir()
        (tmp_path / ".gator" / ".gator-version").write_text(
            "generation: 2\ninstalled: 2026-07-01\ncli-version: 2.1.0\n"
        )
        assert state_mod.read_repo_gator_version(tmp_path) == "2.1.0"

    def test_none_when_file_missing(self, tmp_path):
        assert state_mod.read_repo_gator_version(tmp_path) is None

    def test_none_when_key_missing(self, tmp_path):
        (tmp_path / ".gator").mkdir()
        (tmp_path / ".gator" / ".gator-version").write_text("generation: 2\n")
        assert state_mod.read_repo_gator_version(tmp_path) is None


class TestCheckConstitution:
    def test_source_repo_exemption_short_circuits(self, tmp_path):
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        (tmp_path / "constitution.md").write_text("y")
        # Even with no templates_dir, source-repo exemption wins
        result = state_mod.check_constitution(tmp_path, None)
        assert result == {"status": "source-repo-exempt"}

    def test_no_baseline_when_templates_dir_none(self, tmp_path):
        result = state_mod.check_constitution(tmp_path, None)
        assert result == {"status": "no-baseline"}

    def test_no_baseline_when_template_constitution_missing(self, tmp_path):
        empty_templates = tmp_path / "empty-templates"
        empty_templates.mkdir()
        result = state_mod.check_constitution(tmp_path, empty_templates)
        assert result == {"status": "no-baseline"}

    def test_no_repo_constitution(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        # remove the constitution we just wrote
        (repo / ".gator" / "constitution.md").unlink()
        result = state_mod.check_constitution(repo, TEMPLATES_DIR)
        assert result == {"status": "no-repo-constitution"}

    def test_clean_when_bytes_match(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        result = state_mod.check_constitution(repo, TEMPLATES_DIR)
        assert result == {"status": "clean"}

    def test_modified_when_bytes_differ(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        (repo / ".gator" / "constitution.md").write_text("locally edited", encoding="utf-8")
        result = state_mod.check_constitution(repo, TEMPLATES_DIR)
        assert result == {"status": "modified"}


class TestVersionDiagnostic:
    def test_no_repo_version_only_host(self):
        line = state_mod._format_version_diagnostic("2.2.2", None)
        assert line == "host: gator 2.2.2"

    def test_matching_versions_suppresses_repo_half(self):
        line = state_mod._format_version_diagnostic("2.2.2", "2.2.2")
        assert line == "host: gator 2.2.2"

    def test_mismatched_versions_shows_both(self):
        line = state_mod._format_version_diagnostic("2.2.2", "2.1.0")
        assert "host: gator 2.2.2" in line
        assert "repo: gatorized with gator 2.1.0" in line


class TestSourceRepoExemption:
    def test_constitution_reports_exempt(self, tmp_path):
        # A repo that IS a source repo (both signature files) + a .gator/ so
        # find_gator_root() succeeds. Templates_dir intentionally left None.
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        (tmp_path / "constitution.md").write_text("y")
        (tmp_path / ".gator").mkdir()

        report = state_mod.collect_status(tmp_path)
        assert report["constitution"]["status"] == "source-repo-exempt"


class TestCheckConstitutionDrift:
    def test_returns_clean_on_pristine_governed_repo(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        result = state_mod.check_constitution_drift(repo)
        assert result == {"status": "clean"}

    def test_returns_modified_when_repo_constitution_edited(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        (repo / ".gator" / "constitution.md").write_text("locally edited", encoding="utf-8")
        result = state_mod.check_constitution_drift(repo)
        assert result == {"status": "modified"}

    def test_returns_source_repo_exempt_on_source_repo(self, tmp_path):
        (tmp_path / "gator-command").mkdir()
        (tmp_path / "gator-command" / "mission.md").write_text("x")
        (tmp_path / "constitution.md").write_text("y")
        (tmp_path / ".gator").mkdir()
        result = state_mod.check_constitution_drift(tmp_path)
        assert result == {"status": "source-repo-exempt"}

    def test_returns_no_baseline_when_product_source_missing(self, tmp_path):
        # .gator/ exists but no product-source.json and no template source
        (tmp_path / ".gator").mkdir()
        result = state_mod.check_constitution_drift(tmp_path)
        assert result == {"status": "no-baseline"}

    def test_never_raises_on_broken_gator_dir(self, tmp_path):
        """Best-effort — no .gator/ at all should still return a status dict,
        not raise. gator init calls this on every session open."""
        result = state_mod.check_constitution_drift(tmp_path)
        assert isinstance(result, dict)
        assert "status" in result

    def test_signature_takes_only_repo_root(self):
        """The wrapper's API is deliberately flat — one positional arg.
        Callers must not need to know about template-source resolution."""
        import inspect
        sig = inspect.signature(state_mod.check_constitution_drift)
        assert list(sig.parameters.keys()) == ["repo_root"]


# ---------------------------------------------------------------------------
# gator-state-v2 — native agent files are informational, never managed
# (gator-native entry point, 2026-10-08)
# ---------------------------------------------------------------------------

NATIVE_FILES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md")

_NATIVE_CASES = {
    "team-owned": (b"# Team rules\r\nUse ruff.\r\n", False),
    "sentinel": (b"# Claude\n\n<!-- GATOR:BEGIN -->\nold\n<!-- GATOR:END -->\n", True),
    "corrupted": (b"<!-- GATOR:BEGIN -->\nA\n<!-- GATOR:BEGIN -->\n", True),
    "legacy": (b"# --- Gator Navigation Coding ---\nRead .gator/constitution.md\n", True),
}

_RETIRED_VOCABULARY = ("modified", "corrupted", "legacy", "foreign", "drift",
                       "repair", "missing", "unhealthy")


def _seed_native_files(repo, case):
    data, _historical = _NATIVE_CASES[case]
    for name in NATIVE_FILES:
        (repo / name).write_bytes(data)
    (repo / "CLAUDE.local.md").write_bytes(b"private\n")


def _snapshot(repo):
    return {p.name: p.read_bytes() for p in repo.iterdir() if p.is_file()}


class TestStatusV2:
    def test_schema_and_shape(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        report = state_mod.collect_status(repo)
        assert report["schema"] == "gator-state-v2"
        assert "entry_points" not in report
        assert "entry_point_baseline_kind" not in report
        assert report["constitution_baseline_source"] is not None
        assert report["constitution"]["status"] == "clean"
        assert [r["filename"] for r in report["native_files"]] == list(NATIVE_FILES)
        assert json.loads(state_mod.render_status_json(report))["schema"] == "gator-state-v2"

    def test_absent_files_are_normal(self, tmp_path):
        repo = _make_governed_repo(tmp_path)
        report = state_mod.collect_status(repo)
        for rec in report["native_files"]:
            assert rec == {"filename": rec["filename"], "present": False, "managed": False,
                           "historical_gator_block": False, "local_companion": "absent"}
        text = state_mod.render_status_text(report)
        assert "native agent files (not managed by Gator):" in text
        assert "constitution: matches baseline" in text

    @pytest.mark.parametrize("case", sorted(_NATIVE_CASES))
    def test_present_files_are_informational(self, tmp_path, case):
        repo = _make_governed_repo(tmp_path)
        _seed_native_files(repo, case)
        report = state_mod.collect_status(repo)
        expected_historical = _NATIVE_CASES[case][1]
        for rec in report["native_files"]:
            assert rec["present"] is True
            assert rec["managed"] is False
            assert rec["historical_gator_block"] is expected_historical
        claude = report["native_files"][0]
        assert claude["local_companion"] == "present"
        native_section = state_mod.render_status_text(report).split("constitution:")[0].lower()
        for word in _RETIRED_VOCABULARY:
            assert word not in native_section, word
        if expected_historical:
            assert "historical gator block (not refreshed)" in native_section


class TestRepairStub:
    """`gator state repair` is a no-write compatibility stub."""

    @pytest.mark.parametrize("argv", [
        ["repair"], ["repair", "--dry-run"], ["repair", "CLAUDE.md"], ["repair", "--json"],
    ])
    def test_repair_writes_nothing_and_exits_zero(self, tmp_path, monkeypatch, capfd, argv):
        repo = _make_governed_repo(tmp_path)
        _seed_native_files(repo, "sentinel")
        before = _snapshot(repo)
        monkeypatch.setattr("sys.argv", ["gator-state.py", *argv, "--path", str(repo)])
        with pytest.raises(SystemExit) as exc:
            state_mod.main()
        assert exc.value.code == 0
        assert _snapshot(repo) == before
        out = capfd.readouterr().out
        if "--json" in argv:
            payload = json.loads(out)
            assert payload["schema"] == "gator-state-v2"
            assert payload["actions"] == []
            assert payload["native_files"] == "not-managed"
        else:
            assert "Nothing to repair" in out

    def test_local_companion_is_never_opened(self, tmp_path, monkeypatch):
        repo = _make_governed_repo(tmp_path)
        _seed_native_files(repo, "legacy")
        real_read_text = Path.read_text
        real_read_bytes = Path.read_bytes

        def guard(fn):
            def wrapped(self, *a, **k):
                assert not self.name.endswith(".local.md"), f"opened {self}"
                return fn(self, *a, **k)
            return wrapped

        monkeypatch.setattr(Path, "read_text", guard(real_read_text))
        monkeypatch.setattr(Path, "read_bytes", guard(real_read_bytes))
        report = state_mod.collect_status(repo)
        assert report["native_files"][0]["local_companion"] == "present"


class TestStateCliSurface:
    def test_status_subparser_has_no_source_flag(self):
        parser = state_mod._build_parser()
        sub_action = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
        flags = {opt for a in sub_action.choices["status"]._actions for opt in a.option_strings}
        assert "--source" not in flags
        assert {"--path", "--json"} <= flags

    def test_collect_status_takes_only_repo_root(self):
        import inspect
        assert list(inspect.signature(state_mod.collect_status).parameters) == ["repo_root"]
