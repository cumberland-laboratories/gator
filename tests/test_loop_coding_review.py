"""
#41 Module 4 — implementation review, approval binding, staleness, and
approval resolution (committed / pending / stale / unknown).

End-to-end in real Git repos: clean approval then the ordinary commit
resolves Committed; a candidate changed after submission blocks approval
but not findings; post-approval drift is Stale and returns via reopen;
multi-round revision; a commit whose tree differs (hook-like) is Stale;
max-rounds extension resumes implementation; restart recovery through the
CLI; watcher/liveness terminal behavior.
"""

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import gitsnap  # noqa: E402
import host as loop_host  # noqa: E402
import liveness as lv  # noqa: E402
import session as loop_session  # noqa: E402
import state_machine as sm  # noqa: E402
import submit as loop_submit  # noqa: E402

from test_loop_coding_mode import (  # noqa: E402,F401
    _tokens, git, make_planning_source, repo, start_coding)
from test_loop_coding_submit import (  # noqa: E402,F401
    GOOD_ARTIFACT, coding, stage_change, write)

GATOR_LOOP = SCRIPTS_DIR / "gator-loop.py"
REVIEW = "# Review\n\n## Executive Summary\n\n- ok\n\n## Verdict\n\nAPPROVE\n"
FINDINGS = "# Review\n\n## Executive Summary\n\n- fix it\n\n## Verdict\n\nREVISE\n"


def submit_impl(c):
    return loop_submit.handle_submit_implementation(
        c["tok"]["draftor"], str(c["art"]), loop_dir=c["loop_dir"])


def review(c, approve, text=None, tmp=None):
    f = Path(str(c["art"]) + (".approve.md" if approve else ".findings.md"))
    write(f, text or (REVIEW if approve else FINDINGS))
    return loop_submit.handle_submit_review(
        c["tok"]["reviewer"], str(f), approve=approve, loop_dir=c["loop_dir"])


def sess(c):
    return loop_session.load_session(c["loop_dir"])


def resolution(c):
    s = sess(c)
    approval = s["coding"]["approval"]
    # Mirrors the CLI / Dashboard consumers (#85): pass the approved head.
    snap = gitsnap.snapshot(c["repo"], s["coding"]["base_head"],
                            approved_head=(approval or {}).get("head"))
    return sm.resolve_approval(approval, snap)


def loop_bytes(c):
    d = c["loop_dir"]
    return ((d / "session.json").read_bytes(),
            (d / "events.jsonl").read_bytes())


def last_event(c):
    return json.loads((c["loop_dir"] / "events.jsonl").read_text(
        encoding="utf-8").strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# Pure: resolve_approval
# ---------------------------------------------------------------------------

APPROVAL = {"tree": "t" * 40, "head": "h" * 40, "round": 0, "ts": "x"}
SUCCESSOR = {"ok": True, "status": "successor", "commit": "n" * 40,
             "tree": "t" * 40}


def snap(**kw):
    base = {"ok": True, "current_head": "h" * 40, "head_tree": "p" * 40,
            "staged_tree": "t" * 40, "detached": False}
    base.update(kw)
    return base


class TestResolveApproval:
    def test_none_and_invalidated(self):
        assert sm.resolve_approval(None, snap())["state"] == "none"
        inv = dict(APPROVAL, invalidated_at="now")
        assert sm.resolve_approval(inv, snap())["state"] == "invalidated"

    def test_unknown_on_snapshot_failure(self):
        r = sm.resolve_approval(APPROVAL, {"ok": False, "error": "conflict"})
        assert r["state"] == "unknown" and r["reason"] == "conflict"

    def test_pending(self):
        assert sm.resolve_approval(APPROVAL, snap())["state"] == "pending"

    def test_stale_staged_tree_changed(self):
        r = sm.resolve_approval(APPROVAL, snap(staged_tree="z" * 40))
        assert (r["state"], r["reason"]) == ("stale", "staged_tree_changed")

    def test_committed(self):
        r = sm.resolve_approval(APPROVAL, snap(current_head="n" * 40,
                                               head_tree="t" * 40,
                                               staged_tree="t" * 40,
                                               approval_history=SUCCESSOR))
        assert r["state"] == "committed" and r["commit"] == "n" * 40

    def test_committed_names_successor_not_current_head(self):
        # #85: later commits moved HEAD; the approval commit is historical.
        r = sm.resolve_approval(APPROVAL, snap(
            current_head="l" * 40, head_tree="z" * 40,
            approval_history=dict(SUCCESSOR, commit="c" * 40)))
        assert r["state"] == "committed" and r["commit"] == "c" * 40
        assert "approval_history" not in r

    def test_committed_even_if_index_moved_after_commit(self):
        r = sm.resolve_approval(APPROVAL, snap(current_head="n" * 40,
                                               head_tree="t" * 40,
                                               staged_tree="q" * 40,
                                               approval_history=SUCCESSOR))
        assert r["state"] == "committed"

    def test_head_moved_tree_differs(self):
        r = sm.resolve_approval(APPROVAL, snap(
            current_head="n" * 40, head_tree="t" * 40,
            approval_history=dict(SUCCESSOR, tree="d" * 40)))
        assert (r["state"], r["reason"]) == ("stale", "head_moved_tree_differs")

    @pytest.mark.parametrize("tree", ["d" * 40, "t" * 40])
    def test_detached_mismatch_precedes_history(self, tree):
        # A matching successor does not make a detached HEAD committed.
        r = sm.resolve_approval(APPROVAL, snap(
            current_head="n" * 40, head_tree=tree, detached=True,
            approval_history=dict(SUCCESSOR, tree=tree)))
        assert (r["state"], r["reason"]) == ("stale", "detached_mismatch")

    def test_history_diverged(self):
        r = sm.resolve_approval(APPROVAL, snap(
            current_head="n" * 40, head_tree="t" * 40,
            approval_history={"ok": True, "status": "diverged",
                              "why": "not_ancestor"}))
        assert (r["state"], r["reason"]) == ("stale", "history_diverged")

    @pytest.mark.parametrize("hist,reason", [
        (None, "history_unavailable"),
        ({"ok": False, "error": "git_error", "detail": "x"}, "git_error"),
    ])
    def test_history_missing_or_failed_is_unknown(self, hist, reason):
        kw = {} if hist is None else {"approval_history": hist}
        r = sm.resolve_approval(APPROVAL, snap(current_head="n" * 40,
                                               head_tree="t" * 40, **kw))
        assert (r["state"], r["reason"]) == ("unknown", reason)


class TestAdvanceReviewed:
    def _s(self, **status):
        s = loop_session.create_session(
            "f", "f-id", max_rounds=2, mode="coding",
            coding={"source_loop_id": "s", "plan_sha256": "0" * 64,
                    "base_head": "b" * 40, "base_tree": "c" * 40})
        s["status"].update(stage="implementation_review", next_role="reviewer")
        s["status"].update(status)
        return s

    def test_approve_requires_binding(self):
        with pytest.raises(ValueError):
            sm.advance_implementation_reviewed(self._s(), True, 300)

    def test_approve(self):
        s = self._s()
        sm.advance_implementation_reviewed(s, True, 300, approval=APPROVAL)
        assert s["status"]["stage"] == "implementation_approved"
        assert s["status"]["next_role"] is None
        assert s["coding"]["approval"] == APPROVAL
        assert sm.is_terminal(s)

    def test_findings_then_round_limit(self):
        s = self._s()
        sm.advance_implementation_reviewed(s, False, 300)
        assert (s["status"]["stage"], s["status"]["round"]) == (
            "implementation_revision", 1)
        s["status"]["stage"] = "implementation_review"
        sm.advance_implementation_reviewed(s, False, 300)
        assert s["status"]["stage"] == "max_rounds_exceeded"

    def test_rejects_wrong_mode_or_stage(self):
        with pytest.raises(ValueError):
            sm.advance_implementation_reviewed(
                self._s(stage="implementation_drafting"), False, 300)
        p = loop_session.create_session("f", "id")
        p["status"]["stage"] = "plan_review"
        with pytest.raises(ValueError):
            sm.advance_implementation_reviewed(p, False, 300)


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

class TestReviewEndToEnd:
    def test_clean_approval_then_commit_resolves_committed(self, coding):
        c = coding
        stage_change(c["repo"])
        *_, gen = submit_impl(c)
        review(c, approve=True)
        s = sess(c)
        assert s["status"]["stage"] == "implementation_approved"
        appr = s["coding"]["approval"]
        assert appr["tree"] == gen["snapshot"]["staged_tree"]
        assert appr["head"] == gen["snapshot"]["current_head"]
        rv = s["coding"]["generations"][-1]["review"]
        assert rv["verdict"] == "approve" and rv["candidate_changed"] is False
        art = (c["loop_dir"] / "findings.current.md").read_text(encoding="utf-8")
        assert "## Reviewed Candidate" in art and appr["tree"] in art
        assert last_event(c)["event"] == "implementation_approved"
        assert resolution(c)["state"] == "pending"

        git(c["repo"], "commit", "-q", "-m", "the one normal commit")
        r = resolution(c)
        assert r["state"] == "committed"
        assert r["commit"] == git(c["repo"], "rev-parse", "HEAD").stdout.strip()

    def test_changed_candidate_blocks_approval_not_findings(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        stage_change(c["repo"], "extra.py", "x = 1\n")  # index moves on
        before = loop_bytes(c)
        with pytest.raises(ValueError) as ei:
            review(c, approve=True)
        assert "changed since submission" in str(ei.value)
        assert loop_bytes(c) == before
        review(c, approve=False)
        s = sess(c)
        assert s["status"]["stage"] == "implementation_revision"
        assert s["coding"]["generations"][-1]["review"]["candidate_changed"] is True
        assert "candidate changed" in last_event(c)["detail"]

    def test_head_moved_after_submission_blocks_approval(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        git(c["repo"], "commit", "-q", "-m", "early commit")
        with pytest.raises(ValueError):
            review(c, approve=True)

    def test_unverifiable_live_candidate_blocks_approval(self, coding,
                                                          monkeypatch):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        monkeypatch.setattr(gitsnap, "snapshot", lambda root, base=None: {
            "ok": False, "error": "git_busy", "detail": "index.lock"})
        with pytest.raises(ValueError) as ei:
            review(c, approve=True)
        assert "Cannot verify" in str(ei.value)
        review(c, approve=False)  # findings still recorded
        rv = sess(c)["coding"]["generations"][-1]["review"]
        assert rv["live_snapshot_ok"] is False and rv["candidate_changed"]

    def test_post_approval_drift_is_stale_then_reopen_cycle(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        review(c, approve=True)
        stage_change(c["repo"], text="print('changed after approval')\n")
        r = resolution(c)
        assert (r["state"], r["reason"]) == ("stale", "staged_tree_changed")

        loop_host.reopen_loop(c["tok"]["architect"], "drifted",
                              loop_dir=c["loop_dir"])
        assert sess(c)["coding"]["approval"]["invalidated_at"]
        assert resolution(c)["state"] == "invalidated"
        *_, gen2 = submit_impl(c)
        review(c, approve=True)
        s = sess(c)
        assert s["status"]["stage"] == "implementation_approved"
        assert s["coding"]["approval"]["tree"] == gen2["snapshot"]["staged_tree"]
        assert "invalidated_at" not in s["coding"]["approval"]
        assert resolution(c)["state"] == "pending"

    def test_multi_round_revision(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        review(c, approve=False)
        stage_change(c["repo"], text="print('v2')\n")
        submit_impl(c)
        review(c, approve=True)
        gens = sess(c)["coding"]["generations"]
        assert [g["round"] for g in gens] == [0, 1]
        assert [g["review"]["verdict"] for g in gens] == ["revise", "approve"]
        assert gens[0]["review"]["reviewed_tree"] != gens[1]["review"]["reviewed_tree"]
        assert (c["loop_dir"] / "findings.round-0.md").exists()
        assert (c["loop_dir"] / "findings.round-1.md").exists()

    def test_hook_like_commit_with_different_tree_is_stale(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        review(c, approve=True)
        # Simulate a hook rewriting content inside the commit.
        stage_change(c["repo"], "hook-added.txt", "status\n")
        git(c["repo"], "commit", "-q", "-m", "commit with extra content")
        r = resolution(c)
        assert (r["state"], r["reason"]) == ("stale", "head_moved_tree_differs")

    def test_reviewer_cannot_author_reviewed_candidate(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        before = loop_bytes(c)
        with pytest.raises(ValueError) as ei:
            review(c, approve=True,
                   text=REVIEW + "\n## Reviewed Candidate\n\nfake\n")
        assert "must not include" in str(ei.value)
        assert loop_bytes(c) == before

    def test_review_without_generation_rejected(self, coding):
        c = coding
        s = sess(c)
        s["status"].update(stage="implementation_review", next_role="reviewer")
        loop_session.save_session(c["loop_dir"], s)
        with pytest.raises(ValueError) as ei:
            review(c, approve=False)
        assert "No implementation candidate" in str(ei.value)

    def test_max_rounds_then_extend_resumes_implementation(self, repo, tmp_path):
        src_id, _ = make_planning_source(repo)
        loop_id, loop_dir = start_coding(repo, src_id, max_rounds=1)
        art = tmp_path / "impl.md"
        write(art, GOOD_ARTIFACT)
        c = {"repo": repo, "loop_dir": loop_dir, "tok": _tokens(loop_dir),
             "art": art}
        stage_change(repo)
        submit_impl(c)
        review(c, approve=False)
        assert sess(c)["status"]["stage"] == "max_rounds_exceeded"
        assert last_event(c)["event"] == "max_rounds_exceeded"
        loop_host.extend_loop(c["tok"]["architect"], 1, "one more",
                              loop_dir=loop_dir)
        s = sess(c)
        assert (s["status"]["stage"], s["status"]["next_role"]) == (
            "implementation_revision", "draftor")
        stage_change(repo, text="print('v2')\n")
        submit_impl(c)
        assert sess(c)["status"]["stage"] == "implementation_review"

    def test_watcher_exits_on_approval(self, coding, monkeypatch):
        c = coding
        monkeypatch.setattr(loop_host, "POLL_INTERVAL", 0.05)
        stage_change(c["repo"])
        submit_impl(c)
        lv.register(c["tok"]["draftor"], loop_dir=c["loop_dir"])
        review(c, approve=True)
        t = threading.Thread(target=loop_host.watch_loop,
                             args=(c["loop_dir"],), daemon=True)
        t.start()
        t.join(15)
        assert not t.is_alive()
        notes = lv.open_store(c["loop_dir"]).read()["roles"]["draftor"][
            "notifications"]
        assert [n["kind"] for n in notes if lv.is_pending(n)] == ["terminal"]


# ---------------------------------------------------------------------------
# CLI and restart recovery
# ---------------------------------------------------------------------------

def cli(c, *args):
    return subprocess.run([sys.executable, str(GATOR_LOOP), *args],
                          cwd=str(c["repo"]), capture_output=True, text=True,
                          timeout=60)


class TestCli:
    def test_approve_message_and_restart_resolution(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        f = Path(str(c["art"]) + ".r.md")
        write(f, REVIEW)
        r = cli(c, "submit-review", "--token", c["tok"]["reviewer"],
                "--file", str(f), "--approve")
        assert r.returncode == 0, r.stderr
        assert "Implementation approved" in r.stdout
        assert "ONE normal commit" in r.stdout
        # A fresh process (restart) reads the persisted binding.
        r = cli(c, "status", "--token", c["tok"]["draftor"], "--json")
        out = json.loads(r.stdout)
        assert out["approval_resolution"]["state"] == "pending"
        r = cli(c, "status", "--token", c["tok"]["draftor"])
        assert "PENDING COMMIT" in r.stdout and r.returncode == 2
        git(c["repo"], "commit", "-q", "-m", "commit")
        r = cli(c, "status", "--token", c["tok"]["draftor"])
        assert "COMMITTED" in r.stdout

    def test_committed_survives_later_commits(self, coding):
        # #85: the original false-Stale report.
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        review(c, approve=True)
        git(c["repo"], "commit", "-q", "-m", "the one normal commit")
        normal = git(c["repo"], "rev-parse", "HEAD").stdout.strip()
        for i in range(2):
            stage_change(c["repo"], f"later{i}.py", "x = 1\n")
            git(c["repo"], "commit", "-q", "-m", f"later {i}")
        r = cli(c, "status", "--token", c["tok"]["architect"])
        assert f"COMMITTED -- handoff complete (commit {normal})" in r.stdout
        assert "gator loop reopen" not in r.stdout
        out = json.loads(cli(c, "status", "--token", c["tok"]["architect"],
                             "--json").stdout)
        res = out["approval_resolution"]
        assert res["state"] == "committed" and res["commit"] == normal
        assert res["current_head"] != normal

    def test_coincidental_later_tree_cannot_repair_stale(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        review(c, approve=True)
        approved_tree = sess(c)["coding"]["approval"]["tree"]
        stage_change(c["repo"], "hook-added.txt", "status\n")
        git(c["repo"], "commit", "-q", "-m", "hook-altered normal commit")
        git(c["repo"], "rm", "-q", "hook-added.txt")
        git(c["repo"], "commit", "-q", "-m", "restores the approved tree")
        assert git(c["repo"], "rev-parse",
                   "HEAD^{tree}").stdout.strip() == approved_tree
        r = cli(c, "status", "--token", c["tok"]["architect"])
        assert "STALE -- the first commit after approval does not" in r.stdout
        out = json.loads(cli(c, "status", "--token", c["tok"]["architect"],
                             "--json").stdout)
        assert out["approval_resolution"]["reason"] == "head_moved_tree_differs"

    def test_detached_after_commit_is_stale_until_reattached(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        review(c, approve=True)
        git(c["repo"], "commit", "-q", "-m", "the one normal commit")
        branch = git(c["repo"], "symbolic-ref", "--short",
                     "HEAD").stdout.strip()
        git(c["repo"], "checkout", "-q", "--detach")
        r = cli(c, "status", "--token", c["tok"]["architect"])
        assert "STALE -- HEAD moved and is detached" in r.stdout
        assert "COMMITTED" not in r.stdout
        git(c["repo"], "checkout", "-q", branch)
        r = cli(c, "status", "--token", c["tok"]["architect"])
        assert "COMMITTED -- handoff complete" in r.stdout

    def test_architect_sees_stale_and_reopen_hint(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        review(c, approve=True)
        stage_change(c["repo"], text="print('drift')\n")
        r = cli(c, "status", "--token", c["tok"]["architect"])
        assert "STALE" in r.stdout
        assert "gator loop reopen --token" in r.stdout
        out = json.loads(cli(c, "status", "--token", c["tok"]["architect"],
                             "--json").stdout)
        assert out["approval_resolution"]["reason"] == "staged_tree_changed"
        assert out["mode"] == "coding"

    def test_findings_on_changed_candidate_cli_note(self, coding):
        c = coding
        stage_change(c["repo"])
        submit_impl(c)
        stage_change(c["repo"], "extra.py", "x = 1\n")
        f = Path(str(c["art"]) + ".f.md")
        write(f, FINDINGS)
        r = cli(c, "submit-review", "--token", c["tok"]["reviewer"],
                "--file", str(f))
        assert r.returncode == 0, r.stderr
        assert "must resubmit the current tree" in r.stdout
        r = cli(c, "submit-review", "--token", c["tok"]["reviewer"],
                "--file", str(f), "--approve")
        assert r.returncode == 1  # not the reviewer's turn any more
