"""
#43 M1 — Architect brief persistence, validation, integrity, and the
coding-successor carry-forward choices (CLI/host path).
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import host as loop_host  # noqa: E402
import session as loop_session  # noqa: E402

from test_loop_coding_mode import (  # noqa: E402,F401
    PLAN_TEXT, git, repo, start_coding)

GATOR_LOOP = SCRIPTS_DIR / "gator-loop.py"
BRIEF = "# Brief\n\nPrioritize Windows paths. Read scripts-loop.md.\n".encode()
MAX = loop_session.MAX_BRIEF_BYTES


def loop_dirs(repo):
    base = repo / ".gator" / "loops"
    return sorted(p.name for p in base.iterdir() if p.is_dir()) \
        if base.is_dir() else []


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def make_writable(path):
    os.chmod(str(path), 0o666)


def planning(repo, brief=None, brief_text=None, approved=True,
             feature="source-feature"):
    sketch = repo.parent / "sketch.md"
    sketch.write_text("# Sketch\n", encoding="utf-8")
    brief_path = None
    if brief is not None:
        brief_path = str(write_bytes(repo.parent / "brief.md", brief))
    loop_id, loop_dir = loop_host.init_loop(
        feature, str(sketch), repo_root=repo, brief_path=brief_path,
        brief_text=brief_text)
    if approved:
        s = loop_session.load_session(loop_dir)
        s["status"].update(stage="plan_approved", next_role=None)
        loop_session.save_session(loop_dir, s)
        (loop_dir / "plan.current.md").write_bytes(PLAN_TEXT)
    return loop_id, loop_dir


def first_event(loop_dir):
    return json.loads((loop_dir / "events.jsonl").read_text(
        encoding="utf-8").splitlines()[0])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid(self):
        assert loop_session.validate_brief_bytes(BRIEF) == BRIEF

    @pytest.mark.parametrize("bad", [b"", b"   \n\t", b"a\x00b",
                                     b"\xff\xfe bad", "x".encode() * (MAX + 1)],
                             ids=["empty", "blank", "nul", "not-utf8",
                                  "oversize"])
    def test_rejected(self, bad):
        with pytest.raises(ValueError):
            loop_session.validate_brief_bytes(bad)

    def test_multibyte_byte_boundary(self):
        ch = "\u00e9".encode("utf-8")  # 2 bytes
        exact = ch * (MAX // 2)
        assert len(exact) == MAX
        assert loop_session.validate_brief_bytes(exact) == exact
        with pytest.raises(ValueError):
            loop_session.validate_brief_bytes(exact + b"x")

    def test_text_normalization(self):
        assert loop_session.brief_bytes_from_text("   ") is None
        assert loop_session.brief_bytes_from_text("a\r\nb\rc") == b"a\nb\nc"
        with pytest.raises(ValueError):
            loop_session.brief_bytes_from_text(42)

    def test_read_file_rules(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            loop_session.read_brief_file(tmp_path / "nope.md")
        with pytest.raises(ValueError):
            loop_session.read_brief_file(tmp_path)
        big = write_bytes(tmp_path / "big.md", b"x" * (MAX + 1))
        with pytest.raises(ValueError) as ei:
            loop_session.read_brief_file(big)
        assert "limit" in str(ei.value)

    def test_read_file_rejects_symlink(self, tmp_path):
        real = write_bytes(tmp_path / "real.md", BRIEF)
        link = tmp_path / "link.md"
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not creatable here")
        with pytest.raises(ValueError):
            loop_session.read_brief_file(link)

    @pytest.mark.skipif(sys.platform != "win32",
                        reason="Windows reparse points (junctions)")
    def test_read_file_rejects_real_reparse_point(self, tmp_path):
        """Whiteboard M1-1: a real reparse point (an unprivileged directory
        junction) is rejected as an indirection, not merely as 'not a file'."""
        target = tmp_path / "target"
        target.mkdir()
        write_bytes(target / "architect-brief.md", BRIEF)
        junction = tmp_path / "junction"
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction),
                            str(target)], capture_output=True, text=True)
        if r.returncode != 0 or not junction.exists():
            pytest.skip("junctions not creatable here")
        assert loop_session._is_reparse_point(junction)
        with pytest.raises(ValueError) as ei:
            loop_session.read_brief_file(junction)
        assert "reparse point" in str(ei.value)

    def test_reparse_guard_runs_before_any_file_access(self, tmp_path,
                                                       monkeypatch):
        """A reparse-point FILE (needs privilege to create for real) is
        refused before exists()/is_file()/stat()/open() ever run."""
        f = write_bytes(tmp_path / "brief.md", BRIEF)
        monkeypatch.setattr(loop_session, "_is_reparse_point",
                            lambda p: Path(p) == f)
        touched = []
        real_stat = Path.stat

        def tracking_stat(self, *a, **k):
            # An lstat (follow_symlinks=False) is the permitted probe; any
            # stat that follows the indirection is a violation.
            if k.get("follow_symlinks", True) and Path(self) == f:
                touched.append("stat")
            return real_stat(self, *a, **k)
        monkeypatch.setattr(Path, "stat", tracking_stat)
        import builtins
        real_open = builtins.open
        monkeypatch.setattr(builtins, "open", lambda p, *a, **k: (
            touched.append("open") if str(p) == str(f) else None,
            real_open(p, *a, **k))[1])
        with pytest.raises(ValueError) as ei:
            loop_session.read_brief_file(f)
        assert "reparse point" in str(ei.value)
        assert "open" not in touched
        assert "stat" not in touched  # no following stat before refusal

    def test_start_rejects_reparse_brief_atomically(self, repo, monkeypatch):
        brief = write_bytes(repo.parent / "brief.md", BRIEF)
        monkeypatch.setattr(loop_session, "_is_reparse_point",
                            lambda p: Path(p) == brief)
        sketch = repo.parent / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        before = loop_dirs(repo)
        with pytest.raises(ValueError):
            loop_host.init_loop("f", str(sketch), repo_root=repo,
                                brief_path=str(brief))
        assert loop_dirs(repo) == before


# ---------------------------------------------------------------------------
# Integrity: verify_brief / read_verified_brief / brief_status_view
# ---------------------------------------------------------------------------

def brief_dir(tmp_path, name=loop_session.BRIEF_FILENAME, data=BRIEF):
    d = tmp_path / "loop"
    write_bytes(d / name, data)
    return d, loop_session.brief_meta(data, name)


class TestVerify:
    def test_absent(self, tmp_path):
        assert loop_session.verify_brief(tmp_path, None,
                                         loop_session.BRIEF_FILENAME) == "absent"

    def test_ok_and_read(self, tmp_path):
        d, ref = brief_dir(tmp_path)
        assert loop_session.verify_brief(d, ref, ref["artifact"]) == "ok"
        assert loop_session.read_verified_brief(d, ref, ref["artifact"]) == \
            ("ok", BRIEF)

    def test_missing(self, tmp_path):
        d, ref = brief_dir(tmp_path)
        (d / ref["artifact"]).unlink()
        assert loop_session.verify_brief(d, ref, ref["artifact"]) == "missing"

    @pytest.mark.parametrize("tamper", ["size", "digest"])
    def test_mismatch(self, tmp_path, tamper):
        d, ref = brief_dir(tmp_path)
        data = BRIEF + b"!" if tamper == "size" else BRIEF.replace(b"B", b"b", 1)
        write_bytes(d / ref["artifact"], data)
        assert loop_session.verify_brief(d, ref, ref["artifact"]) == "mismatch"
        assert loop_session.read_verified_brief(d, ref, ref["artifact"])[1] is None

    @pytest.mark.parametrize("mutate", [
        lambda r: "not-a-dict",
        lambda r: dict(r, artifact="source-architect-brief.md"),  # swapped
        lambda r: dict(r, artifact="../architect-brief.md"),
        lambda r: dict(r, artifact="C:/abs/architect-brief.md"),
        lambda r: dict(r, sha256="ABC"),
        lambda r: dict(r, sha256=r["sha256"].upper()),
        lambda r: dict(r, bytes="12"),
        lambda r: dict(r, bytes=True),
        lambda r: dict(r, bytes=-1),
        lambda r: {k: v for k, v in r.items() if k != "sha256"},
    ])
    def test_invalid_ref(self, tmp_path, mutate):
        d, ref = brief_dir(tmp_path)
        assert loop_session.verify_brief(d, mutate(ref),
                                         ref["artifact"]) == "invalid_ref"

    def test_unsafe_symlink(self, tmp_path):
        d, ref = brief_dir(tmp_path)
        outside = write_bytes(tmp_path / "outside.md", BRIEF)
        target = d / ref["artifact"]
        target.unlink()
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not creatable here")
        assert loop_session.verify_brief(d, ref, ref["artifact"]) == "unsafe"

    def test_unreadable(self, tmp_path, monkeypatch):
        d, ref = brief_dir(tmp_path)
        import builtins
        real_open = builtins.open

        def boom(path, *a, **k):
            if str(path).endswith(ref["artifact"]):
                raise PermissionError("locked")
            return real_open(path, *a, **k)
        monkeypatch.setattr(builtins, "open", boom)
        assert loop_session.verify_brief(d, ref, ref["artifact"]) == "unreadable"

    def test_status_view_strict_and_positional(self, tmp_path):
        _, ref = brief_dir(tmp_path)
        noisy = dict(ref, content="SECRET", path="../x", extra=1)
        assert loop_session.brief_status_view(noisy, ref["artifact"]) == ref
        assert loop_session.brief_status_view(
            ref, loop_session.SOURCE_BRIEF_FILENAME) is None
        assert loop_session.brief_status_view(None, ref["artifact"]) is None
        assert loop_session.brief_status_view(dict(ref, bytes="1"),
                                              ref["artifact"]) is None


# ---------------------------------------------------------------------------
# Planning start
# ---------------------------------------------------------------------------

class TestPlanningStart:
    def test_no_brief_keeps_shape(self, repo):
        _, loop_dir = planning(repo, approved=False)
        s = loop_session.load_session(loop_dir)
        assert "brief" not in s
        assert s["contract"] == {"context_evidence": 1}
        assert not (loop_dir / loop_session.BRIEF_FILENAME).exists()
        ev = first_event(loop_dir)
        assert "brief_sha256" not in ev

    def test_brief_file_stored_immutably(self, repo):
        _, loop_dir = planning(repo, brief=BRIEF, approved=False)
        s = loop_session.load_session(loop_dir)
        dest = loop_dir / loop_session.BRIEF_FILENAME
        assert dest.read_bytes() == BRIEF
        assert s["brief"] == {"artifact": "architect-brief.md",
                              "sha256": hashlib.sha256(BRIEF).hexdigest(),
                              "bytes": len(BRIEF)}
        assert loop_session.verify_brief(loop_dir, s["brief"],
                                         "architect-brief.md") == "ok"
        if sys.platform != "win32":
            # _make_readonly is POSIX-only by design; on Windows immutability
            # is enforced by the digest check (verify_brief), pinned above.
            assert not os.access(str(dest), os.W_OK)
        ev = first_event(loop_dir)
        assert ev["brief_sha256"] == s["brief"]["sha256"]
        assert ev["brief_bytes"] == len(BRIEF)
        assert "Prioritize" not in json.dumps(ev)  # never content

    def test_brief_text_normalized(self, repo):
        _, loop_dir = planning(repo, brief_text="line1\r\nline2\r\n",
                               approved=False)
        assert (loop_dir / "architect-brief.md").read_bytes() == b"line1\nline2\n"

    def test_blank_text_means_no_brief(self, repo):
        _, loop_dir = planning(repo, brief_text="  \n", approved=False)
        assert "brief" not in loop_session.load_session(loop_dir)

    @pytest.mark.parametrize("make", [
        lambda tmp: str(tmp / "missing.md"),
        lambda tmp: str(tmp),
        lambda tmp: str(write_bytes(tmp / "empty.md", b"  ")),
        lambda tmp: str(write_bytes(tmp / "nul.md", b"a\x00")),
        lambda tmp: str(write_bytes(tmp / "bin.md", b"\xff\xfe")),
        lambda tmp: str(write_bytes(tmp / "big.md", b"x" * (MAX + 1))),
    ])
    def test_rejections_leave_no_partial_dir(self, repo, make):
        before = loop_dirs(repo)
        sketch = repo.parent / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        with pytest.raises((ValueError, FileNotFoundError)):
            loop_host.init_loop("f", str(sketch), repo_root=repo,
                                brief_path=make(repo.parent))
        assert loop_dirs(repo) == before

    def test_failure_after_mkdir_is_atomic(self, repo, monkeypatch):
        before = loop_dirs(repo)
        sketch = repo.parent / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        write_bytes(repo.parent / "brief.md", BRIEF)

        def boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(loop_host, "save_session", boom)
        with pytest.raises(OSError):
            loop_host.init_loop("f", str(sketch), repo_root=repo,
                                brief_path=str(repo.parent / "brief.md"))
        assert loop_dirs(repo) == before

    def test_both_inputs_and_source_brief_rejected(self, repo):
        sketch = repo.parent / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        write_bytes(repo.parent / "brief.md", BRIEF)
        with pytest.raises(ValueError):
            loop_host.init_loop("f", str(sketch), repo_root=repo,
                                brief_path=str(repo.parent / "brief.md"),
                                brief_text="x")
        with pytest.raises(ValueError):
            loop_host.init_loop("f", str(sketch), repo_root=repo,
                                source_brief="keep")

    def test_cli_source_brief_on_planning_rejected(self, repo):
        sketch = repo.parent / "sketch.md"
        sketch.write_text("# Sketch\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(GATOR_LOOP), "start",
                            "--feature", "x", "--sketch", str(sketch),
                            "--source-brief", "drop"], cwd=str(repo),
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 1 and "--source-brief" in r.stderr
        assert loop_dirs(repo) == []


# ---------------------------------------------------------------------------
# Coding successor: all four arrangements + corrupt source
# ---------------------------------------------------------------------------

NEW = "# Coding brief\n\nKeep commits small.\n".encode()


def coding(repo, src_id, source_brief=None, new_brief=None):
    path = None
    if new_brief is not None:
        path = str(write_bytes(repo.parent / "coding-brief.md", new_brief))
    return loop_host.init_loop("coding-feature", None, repo_root=repo,
                               mode="coding", from_loop=src_id,
                               brief_path=path, source_brief=source_brief)


class TestCodingSuccessor:
    def test_keep_default_none(self, repo):
        src_id, src_dir = planning(repo, brief=BRIEF)
        _, d = coding(repo, src_id)
        s = loop_session.load_session(d)
        c = s["coding"]
        assert c["source_brief_decision"] == "kept"
        assert (d / "source-architect-brief.md").read_bytes() == BRIEF
        assert c["source_brief"] == loop_session.brief_meta(
            BRIEF, "source-architect-brief.md")
        assert loop_session.verify_brief(d, c["source_brief"],
                                         "source-architect-brief.md") == "ok"
        assert "brief" not in s and not (d / "architect-brief.md").exists()
        ev = first_event(d)
        assert ev["source_brief_decision"] == "kept"
        assert ev["source_brief_sha256"] == c["source_brief"]["sha256"]
        assert "contract" not in s  # Context Checked is planning-only

    def test_keep_and_new(self, repo):
        src_id, _ = planning(repo, brief=BRIEF)
        _, d = coding(repo, src_id, "keep", NEW)
        s = loop_session.load_session(d)
        assert (d / "source-architect-brief.md").read_bytes() == BRIEF
        assert (d / "architect-brief.md").read_bytes() == NEW
        assert s["brief"]["artifact"] == "architect-brief.md"
        assert s["coding"]["source_brief_decision"] == "kept"

    def test_drop_and_new(self, repo):
        src_id, _ = planning(repo, brief=BRIEF)
        _, d = coding(repo, src_id, "drop", NEW)
        s = loop_session.load_session(d)
        assert s["coding"]["source_brief_decision"] == "dropped"
        assert s["coding"]["source_brief"] is None
        assert not (d / "source-architect-brief.md").exists()
        assert (d / "architect-brief.md").read_bytes() == NEW

    def test_drop_and_none(self, repo):
        src_id, _ = planning(repo, brief=BRIEF)
        _, d = coding(repo, src_id, "drop")
        s = loop_session.load_session(d)
        assert s["coding"]["source_brief_decision"] == "dropped"
        assert "brief" not in s
        assert not any(p.name.endswith("architect-brief.md") for p in d.iterdir())

    @pytest.mark.parametrize("choice", [None, "keep", "drop"])
    def test_source_without_brief_is_none_available(self, repo, choice):
        src_id, _ = planning(repo)
        _, d = coding(repo, src_id, choice)
        c = loop_session.load_session(d)["coding"]
        assert c["source_brief_decision"] == "none_available"
        assert c["source_brief"] is None

    @pytest.mark.parametrize("corrupt", ["bytes", "missing", "ref"])
    def test_corrupt_source_keep_fails_atomically_drop_succeeds(self, repo,
                                                                 corrupt):
        src_id, src_dir = planning(repo, brief=BRIEF)
        f = src_dir / "architect-brief.md"
        if corrupt == "bytes":
            make_writable(f)
            f.write_bytes(BRIEF + b"tampered")
        elif corrupt == "missing":
            make_writable(f)
            f.unlink()
        else:  # a swapped/invalid reference in the source session
            s = loop_session.load_session(src_dir)
            s["brief"]["artifact"] = "source-architect-brief.md"
            loop_session.save_session(src_dir, s)
        before = loop_dirs(repo)
        with pytest.raises(ValueError) as ei:
            coding(repo, src_id)  # default keep
        assert "--source-brief drop" in str(ei.value)
        assert loop_dirs(repo) == before
        _, d = coding(repo, src_id, "drop")
        assert loop_session.load_session(d)["coding"][
            "source_brief_decision"] == "dropped"
        assert not (d / "source-architect-brief.md").exists()

    def test_new_brief_validation_is_atomic(self, repo):
        src_id, _ = planning(repo, brief=BRIEF)
        before = loop_dirs(repo)
        with pytest.raises(ValueError):
            coding(repo, src_id, "keep", b"\x00bad")
        assert loop_dirs(repo) == before

    def test_bad_source_brief_choice(self, repo):
        src_id, _ = planning(repo, brief=BRIEF)
        with pytest.raises(ValueError):
            coding(repo, src_id, "maybe")
