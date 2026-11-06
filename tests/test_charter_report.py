"""Charter health report (`charter_report.py`, `gator charters report`).

Each test proves one risk named by the approved plan: the report carries
the `gator-charters-report-v1` field set within its bounds; its coverage
equals the verifier's on the same tree; each degraded state is reported
honestly; the input fingerprint changes for every input kind and only then;
and the CLI parses both argument orders and prints the key figures.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import charter_report

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "src" / "gator_command" / "scripts"
CLI = SCRIPTS_DIR / "gator-charters.py"


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout


def _write(repo, rel, text):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    _write(tmp_path, ".gator/charters/mod.md",
           "# Charter: mod\n\n**Covers**: `src/*.py`\n\n### build_widget()\nFile: src/a.py\n")
    _write(tmp_path, ".gator/charters/lib.md", "# Charter: lib\n\n**Covers**: `lib/`\n")
    _write(tmp_path, "src/a.py", "def build_widget():\n    return 1\n")
    _write(tmp_path, "src/b.py", "B = 1\n")
    _write(tmp_path, "lib/d/c.py", "C = 1\nD = 2\nE = 3\n")
    _write(tmp_path, "tools/u.py", "U = 1")          # no trailing newline: still one line
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_field_set_and_bounds(repo, monkeypatch):
    monkeypatch.setattr(charter_report, "UNCOVERED_MAX", 0)
    monkeypatch.setattr(charter_report, "LARGEST_MAX", 2)
    r = charter_report.build_report(repo)
    assert r["schema"] == "gator-charters-report-v1" and r["status"] == "complete"
    assert set(r) == {"schema", "status", "generated_at", "gator_version", "inputs", "charters",
                      "coverage", "code", "sync", "measurement", "problems"}
    assert len(r["inputs"]["fingerprint"]) == 64 and r["inputs"]["revision"] == r["inputs"]["head"][:12]
    ch = r["charters"]
    assert (ch["count"], ch["documented_functions"], ch["charter_dir"]) == (2, 1, ".gator/charters")
    assert {i["name"]: (i["covered_files"], i["covered_lines"]) for i in ch["items"]} == \
        {"lib": (1, 3), "mod": (2, 3)}
    cov = r["coverage"]
    assert (cov["source_files"], cov["covered_files"], cov["uncovered_files"]) == (4, 3, 1)
    assert cov["percent"] == 75.0 and cov["uncovered"] == [] and cov["uncovered_truncated"]
    code = r["code"]
    assert code["product_lines"] == 7 and code["uncovered_module"] == {"files": 1, "lines": 1}
    assert [m["charter"] for m in code["modules"]] == ["lib", "mod"]   # ties broken by name
    assert code["largest_files"] == [{"path": "lib/d/c.py", "lines": 3, "charters": ["lib"]},
                                     {"path": "src/a.py", "lines": 2, "charters": ["mod"]}]
    assert code["band"] in ("below", "within", "above") and code["target"]["min"] == 3
    assert r["sync"] == {"state": "none"} and r["problems"] == []


def test_uncovered_count_equals_the_verifier(repo):
    out = subprocess.run([sys.executable, str(SCRIPTS_DIR / "gator-charter-verify.py"),
                          "--path", str(repo), "--json"],
                         capture_output=True, text=True, check=True).stdout
    gaps = [f["file"] for f in json.loads(out)["findings"] if f["class"] == "coverage-gap"]
    cov = charter_report.build_report(repo)["coverage"]
    assert cov["uncovered_files"] == len(gaps) and cov["uncovered"] == sorted(gaps)


def _no_charters(repo, monkeypatch):
    for p in (repo / ".gator" / "charters").iterdir():
        p.unlink()


def _no_commits(repo, monkeypatch):
    _git(repo, "update-ref", "-d", "HEAD")


def _unreadable_file(repo, monkeypatch):
    real = charter_report._count_lines
    def count(path):
        if Path(path).name == "b.py":
            raise OSError(13, "Permission denied")
        return real(path)
    monkeypatch.setattr(charter_report, "_count_lines", count)


def _no_sync_reader(repo, monkeypatch):
    monkeypatch.setitem(sys.modules, "dashboard.charter_sync", None)


@pytest.mark.parametrize("arrange, status, check", [
    (_no_charters, "complete",
     lambda r: r["charters"]["count"] == 0 and r["coverage"]["uncovered_files"] == 4),
    (_no_commits, "complete",
     lambda r: r["inputs"]["head"] is None and r["inputs"]["revision"] is None),
    (_unreadable_file, "partial",
     lambda r: r["problems"][0]["section"] == "code" and "src/b.py" in r["problems"][0]["message"]),
    (_no_sync_reader, "partial",
     lambda r: r["sync"] == {"state": "unavailable"} and r["problems"][0]["section"] == "sync"),
])
def test_degraded_states(repo, monkeypatch, arrange, status, check):
    arrange(repo, monkeypatch)
    r = charter_report.build_report(repo)
    assert r["status"] == status and check(r)


def test_ungatorized_repository_is_unavailable(tmp_path):
    r = charter_report.build_report(tmp_path)
    assert r["status"] == "unavailable" and set(r) == {"schema", "status", "generated_at",
                                                       "gator_version", "reason"}


def _commit(repo):
    _write(repo, "src/a.py", "def build_widget():\n    return 2\n")
    _git(repo, "commit", "-qam", "change")


def _stage(repo):
    _write(repo, "src/a.py", "X = 1\n")
    before = charter_report.input_fingerprint(repo)
    _git(repo, "add", "src/a.py")
    return before


def _edit_modified(repo):
    _write(repo, "src/a.py", "X = 1\n")
    before = charter_report.input_fingerprint(repo)
    _write(repo, "src/a.py", "X = 1\nY = 22\n")
    return before


def _new_charter(repo):
    _write(repo, ".gator/charters/new.md", "# Charter: new\n")


def _sync_record(repo):
    path = Path(_git(repo, "rev-parse", "--git-path", "gator-charter-sync.json").strip())
    (path if path.is_absolute() else repo / path).write_text("{}", encoding="utf-8")


@pytest.mark.parametrize("mutate", [_commit, _stage, _edit_modified, _new_charter, _sync_record])
def test_fingerprint_changes_for_each_input_kind(repo, mutate):
    first = charter_report.input_fingerprint(repo)
    assert charter_report.input_fingerprint(repo) == first          # stable when nothing changed
    before = mutate(repo) or first
    after = charter_report.input_fingerprint(repo)
    assert after is not None and after != before


def test_fingerprint_is_none_outside_a_work_tree(tmp_path):
    assert charter_report.input_fingerprint(tmp_path) is None


def _cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True)


def test_cli_argument_orders_and_text(repo):
    a, b = _cli("report", "--json", "--path", str(repo)), _cli("--json", "report", "--path", str(repo))
    assert a.returncode == b.returncode == 0
    ja, jb = json.loads(a.stdout), json.loads(b.stdout)
    ja.pop("generated_at"), jb.pop("generated_at")
    assert ja == jb
    text = _cli("report", "--path", str(repo))
    assert text.returncode == 0
    for needle in ("Charters:   2", "3 of 4 source files (75.0%)", "Last sync:  never run"):
        assert needle in text.stdout
