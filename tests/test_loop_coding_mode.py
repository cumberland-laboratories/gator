"""
#41 Module 1 — coding-loop mode, mode-indexed stage table, guarded
successor start, and host-level reopen.

Covers: loop_mode normalization (absent / "planning-only" / "planning" /
"coding" / unknown), byte-identical planning behavior, coding-stage
categorization and action rules, mode-aware unblock and extension target,
reopen transition + host guard + watcher contract, guarded start success
and every rejection (atomic: no partial directory), coding timeouts,
single-active detection, liveness projection, and Dashboard adoption.
"""

import hashlib
import json
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import events as loop_events  # noqa: E402
import host as loop_host  # noqa: E402
import liveness as lv  # noqa: E402
import session as loop_session  # noqa: E402
import state_machine as sm  # noqa: E402
import submit as loop_submit  # noqa: E402

GATOR_LOOP = SCRIPTS_DIR / "gator-loop.py"
PLAN_TEXT = b"# Implementation Plan\n\n## Executive Summary\n\n- approved\n"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), check=True,
                          capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "T")
    (r / ".gator").mkdir()
    with open(r / "README.md", "w", encoding="utf-8", newline="\n") as f:
        f.write("hello\n")
    git(r, "add", "README.md")
    git(r, "commit", "-q", "-m", "base")
    monkeypatch.chdir(r)
    return r


def _tokens(loop_dir):
    return {k: v["token"] for k, v in
            loop_session.load_tokens(loop_dir).items()}


def make_planning_source(repo, stage="plan_approved", plan=PLAN_TEXT,
                         mode="planning-only", feature="source-feature"):
    # Outside the repo, so it never shows up as untracked residue.
    sketch = repo.parent / "sketch.md"
    sketch.write_text("# Sketch\n", encoding="utf-8")
    loop_id, loop_dir = loop_host.init_loop(feature, str(sketch),
                                            repo_root=repo)
    s = loop_session.load_session(loop_dir)
    s["status"]["stage"] = stage
    s["status"]["next_role"] = None
    if mode is None:
        s.pop("mode", None)
    else:
        s["mode"] = mode
    loop_session.save_session(loop_dir, s)
    if plan is not None:
        (loop_dir / "plan.current.md").write_bytes(plan)
    return loop_id, loop_dir


def start_coding(repo, source_id, feature="coding-feature", **kw):
    return loop_host.init_loop(feature, None, repo_root=repo, mode="coding",
                               from_loop=source_id, **kw)


def coding_session(stage="implementation_drafting", **status):
    s = loop_session.create_session(
        "f", "f-loop", mode="coding",
        coding={"source_loop_id": "src", "plan_sha256": "0" * 64,
                "base_head": "1" * 40, "base_tree": "2" * 40})
    s["status"]["stage"] = stage
    s["status"]["next_role"] = sm.STAGES["coding"]["role_by_stage"].get(stage)
    s["status"].update(status)
    return s


def planning_session(stage="plan_drafting"):
    s = loop_session.create_session("f", "f-loop")
    s["status"]["stage"] = stage
    return s


def loop_dirs(repo):
    return sorted(p.name for p in (repo / ".gator" / "loops").iterdir()
                  if p.is_dir())


def set_session(loop_dir, **status):
    s = loop_session.load_session(loop_dir)
    s["status"].update(status)
    loop_session.save_session(loop_dir, s)
    return s


# ---------------------------------------------------------------------------
# loop_mode + planning compatibility
# ---------------------------------------------------------------------------

class TestLoopMode:
    @pytest.mark.parametrize("raw", [None, "planning", "planning-only"])
    def test_planning_values(self, raw):
        s = {"mode": raw} if raw is not None else {}
        assert loop_session.loop_mode(s) == "planning"

    def test_coding(self):
        assert loop_session.loop_mode({"mode": "coding"}) == "coding"

    def test_unknown_fails_closed(self):
        with pytest.raises(ValueError):
            loop_session.loop_mode({"mode": "weird"})
        with pytest.raises(ValueError):
            sm.is_terminal({"mode": "weird", "status": {"stage": "x"}})

    def test_planning_session_unchanged(self):
        s = loop_session.create_session("feat", "feat-id", 3, 300)
        assert s["mode"] == "planning-only" and "coding" not in s
        assert s["status"]["stage"] == "plan_drafting"
        assert set(s["current"]) == {"draft", "findings"}

    def test_coding_session_shape(self):
        s = coding_session()
        assert s["mode"] == "coding"
        assert s["status"]["stage"] == "implementation_drafting"
        assert s["status"]["next_role"] == "draftor"
        assert s["coding"]["generations"] == [] and s["coding"]["approval"] is None
        assert "implementation" in s["current"]
        with pytest.raises(ValueError):
            loop_session.create_session("f", "id", mode="coding")
        with pytest.raises(ValueError):
            loop_session.create_session("f", "id", mode="other")


class TestStageTable:
    def test_planning_entries_are_the_pre_41_sets(self):
        p = sm.STAGES["planning"]
        assert p["active"] == frozenset({"plan_drafting", "plan_review",
                                         "plan_revision"})
        assert p["terminal"] == frozenset({"plan_approved", "max_rounds_exceeded",
                                           "turn_timed_out", "ended_by_architect"})
        assert p["paused"] == frozenset({"blocked_on_architect",
                                         "paused_by_architect"})
        assert sm.ALL_STAGES == p["active"] | p["paused"] | p["terminal"]
        assert p["extension_resume_stage"] == "plan_revision"

    @pytest.mark.parametrize("stage", sorted(sm.ALL_STAGES))
    @pytest.mark.parametrize("mode", [None, "planning-only"])
    def test_planning_categorization_identical(self, stage, mode):
        s = {"status": {"stage": stage}}
        if mode:
            s["mode"] = mode
        assert sm.is_active(s) == (stage in sm.ACTIVE_STAGES)
        assert sm.is_paused(s) == (stage in sm.PAUSED_STAGES)
        assert sm.is_terminal(s) == (stage in sm.TERMINAL_STAGES)

    @pytest.mark.parametrize("stage,cat", [
        ("implementation_drafting", "active"),
        ("implementation_review", "active"),
        ("implementation_revision", "active"),
        ("blocked_on_architect", "paused"),
        ("paused_by_architect", "paused"),
        ("implementation_approved", "terminal"),
        ("max_rounds_exceeded", "terminal"),
        ("turn_timed_out", "terminal"),
        ("ended_by_architect", "terminal"),
    ])
    def test_coding_categorization(self, stage, cat):
        s = coding_session(stage)
        assert (sm.is_active(s), sm.is_paused(s), sm.is_terminal(s)) == (
            cat == "active", cat == "paused", cat == "terminal")

    def test_cross_mode_stages_are_not_categorized(self):
        assert not sm.is_terminal(coding_session("plan_approved"))
        assert not sm.is_active(planning_session("implementation_review"))


class TestActionRules:
    def test_coding_draftor_submits_implementation(self):
        s = coding_session("implementation_drafting")
        assert sm.validate_action(s, "draftor", "submit_implementation") == (True, "ok")
        ok, why = sm.validate_action(s, "draftor", "submit_draft")
        assert not ok and "not valid in a coding loop" in why

    def test_coding_reviewer_only_in_review(self):
        assert sm.validate_action(coding_session("implementation_review"),
                                  "reviewer", "submit_review")[0]
        assert not sm.validate_action(coding_session("implementation_drafting"),
                                      "reviewer", "submit_review")[0]

    def test_planning_rejects_coding_actions(self):
        ok, why = sm.validate_action(planning_session(), "draftor",
                                     "submit_implementation")
        assert not ok and "not valid in a planning loop" in why
        assert sm.validate_action(planning_session(), "draftor",
                                  "submit_draft") == (True, "ok")

    def test_escalate_from_coding_active(self):
        s = coding_session("implementation_review")
        assert sm.validate_action(s, "draftor", "escalate")[0]

    def test_reopen_rules(self):
        assert sm.validate_action(coding_session("implementation_approved"),
                                  "architect", "reopen") == (True, "ok")
        ok, why = sm.validate_action(coding_session("implementation_review"),
                                     "architect", "reopen")
        assert not ok and "approved coding loop" in why
        ok, why = sm.validate_action(planning_session("plan_approved"),
                                     "architect", "reopen")
        assert not ok and "coding loop" in why
        assert not sm.validate_action(coding_session("implementation_approved"),
                                      "draftor", "reopen")[0]


class TestModeAwareTransitions:
    def test_unblock_resumes_coding_stage(self):
        s = coding_session("implementation_review")
        sm.advance_escalated(s, "need a call")
        sm.advance_unblocked(s, turn_timeout=300)
        assert s["status"]["stage"] == "implementation_review"
        assert s["status"]["next_role"] == "reviewer"

    def test_unblock_rejects_cross_mode_targets(self):
        s = coding_session("implementation_review")
        sm.advance_escalated(s, "x")
        with pytest.raises(ValueError):
            sm.advance_unblocked(s, stage="plan_review", turn_timeout=300)
        p = planning_session("plan_review")
        sm.advance_escalated(p, "x")
        with pytest.raises(ValueError):
            sm.advance_unblocked(p, stage="implementation_review",
                                 turn_timeout=300)

    def test_unblock_role_from_table(self):
        s = coding_session("implementation_review")
        sm.advance_escalated(s, "x")
        with pytest.raises(ValueError):
            sm.advance_unblocked(s, stage="implementation_revision",
                                 next_role="reviewer", turn_timeout=300)

    @pytest.mark.parametrize("make,resume", [
        (lambda: planning_session("max_rounds_exceeded"), "plan_revision"),
        (lambda: coding_session("max_rounds_exceeded"), "implementation_revision"),
    ])
    def test_extension_target_by_mode(self, make, resume):
        s = make()
        s["status"].update(round=3, max_rounds=3)
        assert sm.advance_extended(s, 2, turn_timeout=300) == (3, 5)
        assert s["status"]["stage"] == resume
        assert s["status"]["next_role"] == "draftor"
        assert s["status"]["turn_deadline"]

    def test_advance_reopened(self):
        s = coding_session("implementation_approved", round=2)
        s["coding"]["approval"] = {"tree": "a" * 40, "head": "b" * 40,
                                   "ts": "2026-10-01T00:00:00+00:00"}
        sm.advance_reopened(s, turn_timeout=300, message="tests failed")
        st = s["status"]
        assert st["stage"] == "implementation_revision"
        assert st["next_role"] == "draftor" and st["round"] == 2
        assert st["architect_message"] == "tests failed"
        assert st["turn_deadline"] and st["blocked"] is False
        assert s["coding"]["approval"]["invalidated_at"]

    def test_advance_reopened_rejects(self):
        with pytest.raises(ValueError):
            sm.advance_reopened(coding_session("implementation_review"), 300)
        with pytest.raises(ValueError):
            sm.advance_reopened(planning_session("plan_approved"), 300)


# ---------------------------------------------------------------------------
# Guarded successor start
# ---------------------------------------------------------------------------

class TestGuardedStart:
    def test_success_binds_plan_and_base(self, repo):
        src_id, src_dir = make_planning_source(repo)
        src_before = (src_dir / "session.json").read_bytes()
        loop_id, loop_dir = start_coding(repo, src_id, max_rounds=4,
                                         turn_timeout=600)
        s = loop_session.load_session(loop_dir)
        assert loop_session.loop_mode(s) == "coding"
        assert s["status"]["stage"] == "implementation_drafting"
        assert s["status"]["next_role"] == "draftor"
        assert s["status"]["max_rounds"] == 4
        assert s["status"]["turn_timeout_seconds"] == 600
        c = s["coding"]
        assert c["source_loop_id"] == src_id
        assert c["plan_sha256"] == hashlib.sha256(PLAN_TEXT).hexdigest()
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        assert c["base_head"] == head
        assert c["base_tree"] == git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
        assert (loop_dir / "approved-plan.md").read_bytes() == PLAN_TEXT
        assert not (loop_dir / "sketch.md").exists()
        assert set(_tokens(loop_dir)) == {"draftor", "reviewer", "architect"}
        ev = json.loads((loop_dir / "events.jsonl").read_text(
            encoding="utf-8").splitlines()[0])
        assert ev["event"] == "loop_started" and ev["mode"] == "coding"
        assert ev["source_loop_id"] == src_id
        # The source session is read under its lock but never written.
        assert (src_dir / "session.json").read_bytes() == src_before

    @pytest.mark.parametrize("mode", [None, "planning", "planning-only"])
    def test_legacy_planning_sources_accepted(self, repo, mode):
        src_id, _ = make_planning_source(repo, mode=mode)
        _, loop_dir = start_coding(repo, src_id)
        assert loop_session.load_session(loop_dir)["mode"] == "coding"

    @pytest.mark.parametrize("kw,needle", [
        ({"stage": "plan_review"}, "not approved"),
        ({"stage": "max_rounds_exceeded"}, "not approved"),
        ({"mode": "coding"}, "planning loop"),
        ({"mode": "mystery"}, "unknown mode"),
        ({"plan": None}, "no plan.current.md"),
        ({"plan": b"   \n"}, "empty"),
    ])
    def test_source_rejections_are_atomic(self, repo, kw, needle):
        src_id, _ = make_planning_source(repo, **kw)
        before = loop_dirs(repo)
        with pytest.raises(ValueError) as ei:
            start_coding(repo, src_id)
        assert needle in str(ei.value)
        assert loop_dirs(repo) == before

    @pytest.mark.parametrize("bad", ["", "../x", "a/b", "a\\b", ".hidden",
                                     "a..b", None])
    def test_invalid_source_ids(self, repo, bad):
        make_planning_source(repo)
        before = loop_dirs(repo)
        with pytest.raises(ValueError):
            start_coding(repo, bad)
        assert loop_dirs(repo) == before

    @pytest.mark.parametrize("alias", ["trailing_dot", "trailing_dots",
                                       "upper", "mixed_case"])
    def test_filesystem_alias_rejected_atomically(self, repo, alias):
        """Whiteboard P1: on Windows ``<id>.`` and case variants resolve to
        the real source directory. They must be rejected — never persisted
        as a noncanonical ``source_loop_id`` — with no partial directory.
        On case-sensitive filesystems the case variants are simply not
        found; rejection holds on every platform."""
        src_id, _ = make_planning_source(repo)
        bad = {"trailing_dot": src_id + ".",
               "trailing_dots": src_id + "...",
               "upper": src_id.upper(),
               "mixed_case": src_id[:1].upper() + src_id[1:]}[alias]
        before = loop_dirs(repo)
        with pytest.raises(ValueError):
            start_coding(repo, bad)
        assert loop_dirs(repo) == before

    @pytest.mark.skipif(sys.platform != "win32",
                        reason="Windows path aliasing")
    def test_windows_alias_reaches_canonical_check(self, repo):
        """The case-variant alias really resolves to the source dir on
        Windows, so the lock-held loop_id comparison (not a missing-dir
        error) is what rejects it."""
        src_id, src_dir = make_planning_source(repo)
        alias = src_id.upper()
        assert (repo / ".gator" / "loops" / alias).is_dir()
        with pytest.raises(ValueError) as ei:
            start_coding(repo, alias)
        assert "not canonical" in str(ei.value)

    def test_canonical_id_check_is_under_lock(self, repo, monkeypatch):
        """A source whose session loop_id differs from its directory name is
        rejected (the persisted id is always the session's own)."""
        src_id, src_dir = make_planning_source(repo)
        s = loop_session.load_session(src_dir)
        s["loop_id"] = "some-other-id"
        loop_session.save_session(src_dir, s)
        before = loop_dirs(repo)
        with pytest.raises(ValueError) as ei:
            start_coding(repo, src_id)
        assert "not canonical" in str(ei.value)
        assert loop_dirs(repo) == before

    def test_persisted_source_id_is_canonical(self, repo):
        src_id, src_dir = make_planning_source(repo)
        _, loop_dir = start_coding(repo, src_id)
        assert loop_session.load_session(loop_dir)["coding"][
            "source_loop_id"] == loop_session.load_session(src_dir)["loop_id"]

    def test_missing_source(self, repo):
        make_planning_source(repo)
        with pytest.raises(ValueError) as ei:
            start_coding(repo, "no-such-loop")
        assert "not found" in str(ei.value)

    def test_digest_mismatch_leaves_no_partial_dir(self, repo, monkeypatch):
        src_id, _ = make_planning_source(repo)
        before = loop_dirs(repo)
        real = Path.read_bytes

        def corrupt(self):
            data = real(self)
            return data + b"x" if self.name == "approved-plan.md" else data
        monkeypatch.setattr(Path, "read_bytes", corrupt)
        with pytest.raises(ValueError) as ei:
            start_coding(repo, src_id)
        assert "digest" in str(ei.value)
        monkeypatch.undo()
        assert loop_dirs(repo) == before

    def test_failure_partway_leaves_no_partial_dir(self, repo, monkeypatch):
        src_id, _ = make_planning_source(repo)
        before = loop_dirs(repo)

        def boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(loop_host, "save_session", boom)
        with pytest.raises(OSError):
            start_coding(repo, src_id)
        assert loop_dirs(repo) == before

    def test_unborn_repo_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        r = tmp_path / "unborn"
        r.mkdir()
        git(r, "init", "-q")
        (r / ".gator").mkdir()
        src_id, _ = make_planning_source(r)
        before = loop_dirs(r)
        with pytest.raises(ValueError) as ei:
            start_coding(r, src_id)
        assert "unborn" in str(ei.value)
        assert loop_dirs(r) == before

    def test_argument_mismatches(self, repo):
        src_id, _ = make_planning_source(repo)
        with pytest.raises(ValueError):
            loop_host.init_loop("f", str(repo / "sketch.md"), repo_root=repo,
                                mode="coding", from_loop=src_id)
        with pytest.raises(ValueError):
            loop_host.init_loop("f", str(repo / "sketch.md"), repo_root=repo,
                                from_loop=src_id)
        with pytest.raises(ValueError):
            loop_host.init_loop("f", None, repo_root=repo)

    def test_cli_start_argument_errors(self, repo):
        def run(*args):
            return subprocess.run([sys.executable, str(GATOR_LOOP), "start",
                                   "--feature", "x", *args], cwd=str(repo),
                                  capture_output=True, text=True, timeout=60)
        r = run("--mode", "coding")
        assert r.returncode == 1 and "--from-loop" in r.stderr
        r = run()
        assert r.returncode == 1 and "--sketch" in r.stderr
        r = run("--mode", "coding", "--from-loop", "missing-loop")
        assert r.returncode == 1 and "not found" in r.stderr


# ---------------------------------------------------------------------------
# Lifecycle: single-active, timeouts, liveness, adoption
# ---------------------------------------------------------------------------

class TestCodingLifecycle:
    def test_active_coding_loop_detected(self, repo):
        src_id, _ = make_planning_source(repo)
        loop_id, loop_dir = start_coding(repo, src_id)
        loops = repo / ".gator" / "loops"
        assert loop_host.find_active_loop(loops) == loop_id
        set_session(loop_dir, stage="implementation_approved", next_role=None)
        assert loop_host.find_active_loop(loops) is None

    def test_unknown_mode_skipped_by_scan(self, repo):
        src_id, _ = make_planning_source(repo)
        _, loop_dir = start_coding(repo, src_id)
        s = loop_session.load_session(loop_dir)
        s["mode"] = "mystery"
        loop_session.save_session(loop_dir, s)
        assert loop_host.find_active_loop(repo / ".gator" / "loops") is None
        assert loop_host._session_is_terminal(loop_dir) is True

    def test_coding_timeout_enforced(self, repo):
        src_id, _ = make_planning_source(repo)
        _, loop_dir = start_coding(repo, src_id)
        set_session(loop_dir, turn_deadline="2000-01-01T00:00:00+00:00")
        loop_host._try_enforce_timeout(loop_dir)
        s = loop_session.load_session(loop_dir)
        assert s["status"]["stage"] == "turn_timed_out"
        assert sm.is_terminal(s)

    def test_watch_loop_enforces_coding_timeout(self, repo, monkeypatch):
        monkeypatch.setattr(loop_host, "POLL_INTERVAL", 0.05)
        src_id, _ = make_planning_source(repo)
        _, loop_dir = start_coding(repo, src_id)
        set_session(loop_dir, turn_deadline="2000-01-01T00:00:00+00:00")
        t = threading.Thread(target=loop_host.watch_loop, args=(loop_dir,),
                             daemon=True)
        t.start()
        t.join(15)
        assert not t.is_alive()
        assert loop_session.load_session(loop_dir)["status"]["stage"] == \
            "turn_timed_out"

    def test_liveness_projection_coding(self, repo):
        src_id, _ = make_planning_source(repo)
        _, loop_dir = start_coding(repo, src_id)
        store = lv.open_store(loop_dir)
        lv.project(loop_dir, store)
        notes = store.read()["roles"]["draftor"]["notifications"]
        assert [n["kind"] for n in notes] == ["turn-ready"]
        assert notes[0]["stage"] == "implementation_drafting"

    def test_dashboard_adoption_skips_approved_coding_loop(self, repo,
                                                           monkeypatch):
        from conftest import load_script
        dashboard = load_script("gator-dashboard")
        src_id, _ = make_planning_source(repo)
        loop_id, loop_dir = start_coding(repo, src_id)
        calls = []
        monkeypatch.setattr(dashboard, "_ensure_loop_watcher",
                            lambda rp, lid, ld, retry=False:
                            (calls.append(lid), ("attached", None))[1])
        monkeypatch.setattr(dashboard, "_sweep_liveness", lambda rp: None)
        monkeypatch.setattr(dashboard, "_REGISTRY_REPOS",
                            [{"name": "r", "path": str(repo)}])
        dashboard._adopt_orphaned_loops()
        assert calls == [loop_id]  # active coding loop adopted
        calls.clear()
        set_session(loop_dir, stage="implementation_approved", next_role=None)
        dashboard._adopt_orphaned_loops()
        assert calls == []  # terminal coding loop not adopted


# ---------------------------------------------------------------------------
# Reopen (host-level guard + watcher contract)
# ---------------------------------------------------------------------------

def approved_coding_loop(repo):
    src_id, _ = make_planning_source(repo)
    loop_id, loop_dir = start_coding(repo, src_id)
    s = loop_session.load_session(loop_dir)
    s["status"].update(stage="implementation_approved", next_role=None,
                       round=1, turn_deadline=None)
    s["coding"]["approval"] = {"tree": "a" * 40, "head": "b" * 40,
                               "ts": "2026-10-01T00:00:00+00:00"}
    loop_session.save_session(loop_dir, s)
    return loop_id, loop_dir


class TestReopen:
    def test_reopen_loop_transition_and_audit(self, repo):
        loop_id, loop_dir = approved_coding_loop(repo)
        tok = _tokens(loop_dir)
        assert loop_host.reopen_loop(tok["architect"], "review missed a case",
                                     loop_dir=loop_dir) == (loop_id, loop_dir)
        s = loop_session.load_session(loop_dir)
        assert s["status"]["stage"] == "implementation_revision"
        assert s["status"]["next_role"] == "draftor"
        assert s["status"]["round"] == 1
        assert s["coding"]["approval"]["invalidated_at"]
        assert s["turns"][-1]["type"] == "reopen"
        last = json.loads((loop_dir / "events.jsonl").read_text(
            encoding="utf-8").strip().splitlines()[-1])
        assert last["event"] == "loop_reopened"
        assert "REOPENED" in loop_events.format_event(last)
        assert loop_events.format_event(last)  # renders
        assert not sm.is_terminal(s)

    def test_reopen_rejections_leave_state_untouched(self, repo):
        loop_id, loop_dir = approved_coding_loop(repo)
        tok = _tokens(loop_dir)

        def snap():
            return ((loop_dir / "session.json").read_bytes(),
                    (loop_dir / "events.jsonl").read_bytes())
        before = snap()
        with pytest.raises(ValueError):
            loop_host.reopen_loop(tok["architect"], "  ", loop_dir=loop_dir)
        with pytest.raises(PermissionError):
            loop_host.reopen_loop(tok["draftor"], "x", loop_dir=loop_dir)
        set_session(loop_dir, stage="implementation_review",
                    next_role="reviewer")
        mid = snap()
        with pytest.raises(PermissionError):
            loop_host.reopen_loop(tok["architect"], "x", loop_dir=loop_dir)
        assert snap() == mid
        set_session(loop_dir, stage="implementation_approved", next_role=None)
        assert snap()[1] == before[1]

    def test_reopen_rejected_for_planning_loop(self, repo):
        _, src_dir = make_planning_source(repo)
        tok = _tokens(src_dir)
        with pytest.raises(PermissionError):
            loop_host.reopen_loop(tok["architect"], "x", loop_dir=src_dir)

    def test_single_active_guard(self, repo):
        loop_id, loop_dir = approved_coding_loop(repo)
        other_src, _ = make_planning_source(repo, feature="other")
        other_id, _ = start_coding(repo, other_src, feature="other-coding")
        before = (loop_dir / "session.json").read_bytes()
        with pytest.raises(RuntimeError) as ei:
            loop_host.reopen_loop(_tokens(loop_dir)["architect"], "x",
                                  loop_dir=loop_dir)
        assert other_id in str(ei.value)
        assert (loop_dir / "session.json").read_bytes() == before

    def test_reopen_after_host_exit_is_live(self, repo, monkeypatch):
        """Reopened from a fresh call: a watcher attaches, timeouts are
        enforced again, and liveness delivers the Draftor's turn."""
        monkeypatch.setattr(loop_host, "POLL_INTERVAL", 0.05)
        _, loop_dir = approved_coding_loop(repo)
        loop_host.reopen_loop(_tokens(loop_dir)["architect"], "redo",
                              loop_dir=loop_dir)
        fd, state, _ = loop_host.acquire_host_lock_with_retry(loop_dir,
                                                              attempts=1)
        assert state == loop_host.HOST_ATTACHED
        set_session(loop_dir, turn_deadline="2000-01-01T00:00:00+00:00")
        t = threading.Thread(target=loop_host.watch_loop,
                             args=(loop_dir, fd), daemon=True)
        t.start()
        t.join(15)
        loop_host.release_host_lock(fd)
        assert not t.is_alive()
        s = loop_session.load_session(loop_dir)
        assert s["status"]["stage"] == "turn_timed_out"
        notes = lv.open_store(loop_dir).read()["roles"]["draftor"][
            "notifications"]
        assert any(n["kind"] == "turn-ready"
                   and n["stage"] == "implementation_revision" for n in notes)

    def test_cli_reopen_already_hosted(self, repo):
        _, loop_dir = approved_coding_loop(repo)
        fd = loop_host.acquire_host_lock(loop_dir)
        try:
            r = subprocess.run(
                [sys.executable, str(GATOR_LOOP), "reopen", "--token",
                 _tokens(loop_dir)["architect"], "--message", "again"],
                cwd=str(repo), capture_output=True, text=True, timeout=60)
        finally:
            loop_host.release_host_lock(fd)
        assert r.returncode == 0, r.stderr
        assert "Reopened: implementation_revision" in r.stdout
        assert "already hosted" in r.stdout
        assert loop_session.load_session(loop_dir)["status"]["stage"] == \
            "implementation_revision"

    def test_watcher_failure_reported_honestly(self, capsys):
        import cli as loop_cli

        class FakeHost:
            HOST_ALREADY_HOSTED = "already_hosted"
            HOST_ATTACHED = "attached"

            @staticmethod
            def acquire_host_lock_with_retry(loop_dir):
                return None, "failed", "lock file unavailable"
        with pytest.raises(SystemExit) as ei:
            loop_cli._attach_foreground_watcher(FakeHost, Path("."), "reopen")
        assert ei.value.code == 1
        err = capsys.readouterr().err
        assert "reopen is saved" in err and "NOT being enforced" in err

    def test_status_shows_coding_prompt(self, repo):
        src_id, _ = make_planning_source(repo)
        _, loop_dir = start_coding(repo, src_id)
        tok = _tokens(loop_dir)["draftor"]
        r = subprocess.run([sys.executable, str(GATOR_LOOP), "status",
                            "--token", tok], cwd=str(repo),
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0
        assert "Mode: coding" in r.stdout
        assert "submit-implementation" in r.stdout
        assert "approved-plan.md" in r.stdout
        r = subprocess.run([sys.executable, str(GATOR_LOOP), "status",
                            "--token", tok, "--json"], cwd=str(repo),
                           capture_output=True, text=True, timeout=60)
        assert json.loads(r.stdout)["mode"] == "coding"
