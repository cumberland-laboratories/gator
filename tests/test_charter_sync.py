"""Dashboard charter sync check (`dashboard/charter_sync.py`).

Each test proves one risk named by the approved plan: the verifier JSON
gains `charters` additively; the roll-up produces the sketch's counts and
state; the commit signal is conservative and glob-aware; a report is never
overwritten; a failed run writes nothing; the Git-private record is
untrusted input; and the report carries the four sketch sections.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dashboard import charter_sync

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "src" / "gator_command" / "scripts"
NOW = datetime(2026, 10, 29, 12, 34, 56, tzinfo=timezone.utc)
CHARTERS = [{"name": "mod", "path": ".gator/charters/mod.md", "covers": ["src/*.py"]},
            {"name": "other", "path": ".gator/charters/other.md", "covers": ["lib/x.py"]}]


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _commit(repo, files, message):
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    (tmp_path / ".gator" / "charters").mkdir(parents=True)
    (tmp_path / ".gator" / "charters" / "mod.md").write_text(
        "# Charter: mod\n\n**Covers**: `src/*.py`\n", encoding="utf-8")
    return tmp_path


def _stub(findings, charters=CHARTERS):
    return lambda _repo: {"version": "x", "finding_count": len(findings),
                          "summary": {}, "findings": findings, "charters": charters}


def _artifacts(repo):
    d = repo / ".gator" / "artifacts"
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def test_verifier_json_adds_charters_additively(repo):
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "gator-charter-verify.py"), "--path", str(repo), "--json"],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    assert list(data) == ["version", "finding_count", "summary", "findings", "charters"]
    assert data["charters"] == [{"name": "mod", "path": ".gator/charters/mod.md",
                                 "covers": ["src/*.py"]}]
    for f in data["findings"]:
        assert {"class", "severity", "file", "message"} <= set(f)


@pytest.mark.parametrize("findings, state, counts", [
    ([], "current", {"current": 2, "needs_review": 0, "missing": 0}),
    ([{"class": "stale-structure", "severity": "info", "file": "src/a.py",
       "function": "gone", "message": "m", "charter": "mod"},
      {"class": "complexity-mismatch", "severity": "warn", "file": "src/a.py", "message": "m"},
      {"class": "coverage-gap", "severity": "warn", "file": "tools/u.py", "message": "m"}],
     "needs-review", {"current": 1, "needs_review": 1, "missing": 1}),
])
def test_roll_up_counts_and_state(repo, findings, state, counts):
    result, status = charter_sync.run_sync(repo, now=NOW, verify_fn=_stub(findings))
    assert status == 200
    assert result["state"] == state and result["counts"] == counts
    if findings:
        # Stale structure first; the mod charter group holds both attributed findings.
        first = result["findings"][0]
        assert (first["kind"], first["label"], first["count"]) == ("stale-structure", "mod", 2)
        assert first["charter_path"] == ".gator/charters/mod.md"
        assert result["findings"][1]["label"] == "tools/u.py"
    else:
        assert result["headline"].startswith("Current")


def test_commit_coverage_is_conservative_and_glob_aware(repo):
    _commit(repo, {}, "charter only")                                    # not governed
    _commit(repo, {"src/a.py": "a"}, "code only")                      # flagged
    _commit(repo, {"src/b.py": "b", ".gator/charters/mod.md": "# Charter: mod\n\n**Covers**: `src/*.py`\nmore\n"},
            "code with charter")                                         # charter updated
    _commit(repo, {"docs/x.txt": "x"}, "ungoverned")                     # not governed
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, {"docs/y.txt": "y"}, "side")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, {"docs/z.txt": "z"}, "main again")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")    # excluded
    result, status = charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))
    assert status == 200
    assert result["recent_commits"] == {"examined": 6, "without_charter_update": 1, "reason": None}
    assert result["state"] == "needs-review"
    assert charter_sync.covers_match("src/a.py", "src/*.py")
    assert not charter_sync.covers_match("x/src/a.py", "src/*.py")   # never basename-only
    assert charter_sync.covers_match("enterprise/app/m.py", "enterprise/app/**")
    assert charter_sync.covers_match("lib/d/e.py", "lib/d/")


def test_same_day_report_is_never_overwritten(repo):
    first, _ = charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))
    original = (repo / first["artifact_path"]).read_text(encoding="utf-8")
    second, _ = charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))
    third, _ = charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))
    assert [first["artifact_path"], second["artifact_path"], third["artifact_path"]] == [
        ".gator/artifacts/2026-10-29-charter-sync-report.md",
        ".gator/artifacts/2026-10-29-charter-sync-report-123456Z.md",
        ".gator/artifacts/2026-10-29-charter-sync-report-123456Z-2.md",
    ]
    assert (repo / first["artifact_path"]).read_text(encoding="utf-8") == original


@pytest.mark.parametrize("output", [
    {"error": "gator-charter-verify timed out after 60s"},
    None,
    {"findings": "not a list"},
    {"findings": [{"class": 1, "file": "a.py"}]},
])
def test_failed_run_writes_nothing(repo, output):
    charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))
    record = charter_sync._record_path(repo)
    before_record = record.read_bytes()
    before_artifacts = _artifacts(repo)
    result, status = charter_sync.run_sync(repo, now=NOW, verify_fn=lambda _r: output)
    assert status == 500 and result["state"] == "failed" and result["error"]
    assert _artifacts(repo) == before_artifacts
    assert record.read_bytes() == before_record


def _valid_record(repo):
    result, _ = charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))
    assert result.pop("persisted") is True
    assert charter_sync.read_last(repo) == result
    return json.loads(charter_sync._record_path(repo).read_text(encoding="utf-8"))


@pytest.mark.parametrize("mutate", [
    lambda rec: "{not json",
    lambda rec: json.dumps({**rec, "headline": "x" * (70 * 1024)}),
    lambda rec: json.dumps({**rec, "extra": 1}),
    lambda rec: json.dumps({**rec, "artifact_path": "../../etc/passwd"}),
    lambda rec: json.dumps({**rec, "counts": {**rec["counts"], "missing": -1}}),
])
def test_read_last_rejects_untrusted_records(repo, mutate):
    record = _valid_record(repo)
    charter_sync._record_path(repo).write_text(mutate(record), encoding="utf-8")
    assert charter_sync.read_last(repo) is None


def test_report_has_four_sections_and_revision(repo):
    _commit(repo, {"src/a.py": "a"}, "code only")
    findings = [{"class": "function-gap", "severity": "info", "file": "src/a.py",
                 "function": "a", "message": "Public function `a()` not documented", "charter": "mod"}]
    result, _ = charter_sync.run_sync(repo, now=NOW, verify_fn=_stub(findings))
    text = (repo / result["artifact_path"]).read_text(encoding="utf-8")
    for heading in ("## Executive summary", "## Structural findings",
                    "## Recent commit coverage", "## Repair sketch"):
        assert heading in text
    assert result["revision"] and f"`{result['revision']}`" in text
    assert "charter update not observed" in text
    assert "Add, combine, or explicitly exclude the responsibility." in text


def _fail_git_when(monkeypatch, needle):
    real = charter_sync.git_run

    def fake(*args, cwd=None):
        if needle in args:
            return "fatal: unable to read git data", False
        return real(*args, cwd=cwd)
    monkeypatch.setattr(charter_sync, "git_run", fake)


@pytest.mark.parametrize("needle", ["--is-inside-work-tree", "--verify", "status", "log"])
def test_git_read_failure_fails_before_writing(repo, monkeypatch, needle):
    _commit(repo, {"src/a.py": "a"}, "code")
    charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))
    record = charter_sync._record_path(repo)
    before = (record.read_bytes(), _artifacts(repo))
    _fail_git_when(monkeypatch, needle)
    result, status = charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))
    assert (status, result["state"]) == (500, "failed")
    assert "Git could not be read" in result["error"]
    assert (record.read_bytes(), _artifacts(repo)) == before


def test_repository_without_commits_is_supported(repo):
    result, status = charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))
    assert (status, result["state"], result["revision"]) == (200, "current", None)
    assert result["recent_commits"]["reason"] == "This repository has no commits yet."


class _BrokenWrite:
    def __init__(self, fh):
        self.fh = fh

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fh.close()

    def write(self, _text):
        self.fh.write("partial")
        raise OSError("disk full")


@pytest.mark.parametrize("break_it", ["write", "validate"])
def test_failed_publication_leaves_no_report(repo, monkeypatch, break_it):
    charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))   # takes the plain name
    record = charter_sync._record_path(repo)
    before = (record.read_bytes(), _artifacts(repo))
    if break_it == "write":
        monkeypatch.setattr(charter_sync, "open",
                            lambda *a, **k: _BrokenWrite(open(*a, **k)), raising=False)
    else:
        monkeypatch.setattr(charter_sync, "_sanitize", lambda _obj: None)
    result, status = charter_sync.run_sync(repo, now=NOW, verify_fn=_stub([]))
    assert (status, result["state"]) == (500, "failed")
    assert (record.read_bytes(), _artifacts(repo)) == before


def test_unavailable_without_gator(tmp_path):
    result, status = charter_sync.run_sync(tmp_path, now=NOW, verify_fn=_stub([]))
    assert (status, result["state"]) == (200, "unavailable")
