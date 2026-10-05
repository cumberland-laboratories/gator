"""
#55 — modular coding checkpoints.

M1: the closed ``## Coding Checkpoints`` grammar (one table) and the
planning-loop draft gate behind ``contract.coding_checkpoints`` (one table
over flagged/legacy sessions x absent/valid/invalid sections).
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import session as loop_session  # noqa: E402
import submit as loop_submit  # noqa: E402

from test_loop_context_evidence import _make_env, _write  # noqa: E402

EM = "—"


def _plan(section_body, extra=""):
    return ("# Plan\n\n## Context Checked\n\n- scripts-loop charter\n\n"
            "## Coding Checkpoints\n\n" + section_body + "\n" + extra)


ONE = f"1. **Fix** {EM} Implement the change. Verify: the focused test."
TWO = (f"1. **Checkpoint contract** {EM} Parse and validate the section.\n"
       f"  Freeze it at coding start. Verify: grammar table.\n"
       f"2. **Lifecycle and binding** - Per-checkpoint transitions. "
       f"Verify: transition table.")


# ---------------------------------------------------------------------------
# Grammar (one table)
# ---------------------------------------------------------------------------

VALID = [
    ("one", ONE, [("cp1", "Fix", "Implement the change.", "the focused test.")]),
    ("two-continuation-dash", TWO,
     [("cp1", "Checkpoint contract",
       "Parse and validate the section. Freeze it at coding start.", "grammar table."),
      ("cp2", "Lifecycle and binding", "Per-checkpoint transitions.", "transition table.")]),
    ("colon-separator", "1. **Fix**: do it. Verify: test.",
     [("cp1", "Fix", "do it.", "test.")]),
    ("twelve", "\n".join(f"{i}. **Step {chr(64 + i)}** {EM} part {i}. Verify: t{i}."
                         for i in range(1, 13)), None),
    ("comment-and-fence-ignored",
     "<!-- guidance -->\n" + ONE + "\n```\nnot an item\n```", None),
]


@pytest.mark.parametrize("name,body,expect", VALID, ids=[v[0] for v in VALID])
def test_grammar_valid(name, body, expect):
    present, items, problems = loop_submit.parse_coding_checkpoints(_plan(body))
    assert present and problems == []
    if expect is not None:
        assert [(i["id"], i["title"], i["scope"], i["verify"]) for i in items] == expect
    if name == "twelve":
        assert [i["id"] for i in items] == [f"cp{i}" for i in range(1, 13)]


INVALID = [
    ("empty", "", "has no checkpoints"),
    ("gap", ONE + f"\n3. **Two** {EM} b. Verify: c.", "numbered 3"),
    ("out-of-order", f"2. **A** {EM} a. Verify: b.", "numbered 2"),
    ("missing-title", f"1. Fix {EM} a. Verify: b.", "expected '**Title**"),
    ("missing-verify", f"1. **Fix** {EM} do it.", "missing 'Verify:'"),
    ("placeholder-scope", f"1. **Fix** {EM} TBD. Verify: b.", "scope is empty or a placeholder"),
    ("placeholder-verify", f"1. **Fix** {EM} a. Verify: n/a", "verification is empty"),
    ("thirteen", "\n".join(f"{i}. **S{i}x** {EM} a. Verify: b." for i in range(1, 14)),
     "at most 12"),
    ("long-title", f"1. **{'x' * 81}** {EM} a. Verify: b.", "title must be 1-80"),
    ("code-title", f"1. **`fix`** {EM} a. Verify: b.", "plain text"),
    ("path-title-slash", f"1. **src/x.py** {EM} a. Verify: b.", "looks like a file"),
    ("path-title-ext", f"1. **loop.js** {EM} a. Verify: b.", "looks like a file"),
    ("path-title-backslash", f"1. **docs\\notes** {EM} a. Verify: b.", "looks like a file"),
    ("stray-text", ONE + "\nsomething else", "unexpected text"),
]


@pytest.mark.parametrize("name,body,needle", INVALID, ids=[v[0] for v in INVALID])
def test_grammar_invalid(name, body, needle):
    present, _items, problems = loop_submit.parse_coding_checkpoints(_plan(body))
    assert present
    assert any(needle in p for p in problems), problems


def test_grammar_absent_and_duplicate_and_fenced_heading():
    assert loop_submit.parse_coding_checkpoints("# Plan\n\n## Approach\n\nx\n") == (False, [], [])
    dup = _plan(ONE) + "\n## Coding Checkpoints\n\n" + ONE + "\n"
    present, _items, problems = loop_submit.parse_coding_checkpoints(dup)
    assert present and "more than one" in problems[0]
    fenced = "# Plan\n\n```\n## Coding Checkpoints\n\n" + ONE + "\n```\n"
    assert loop_submit.parse_coding_checkpoints(fenced)[0] is False


def test_long_scope_capped():
    body = f"1. **Fix** {EM} {'word ' * 200}Verify: test."
    _p, items, problems = loop_submit.parse_coding_checkpoints(_plan(body))
    assert problems == [] and len(items[0]["scope"]) == loop_submit.CHECKPOINT_TEXT_MAX


def test_shipped_plan_template_declares_valid_checkpoints():
    fmt = (Path(__file__).parent.parent / "src" / "gator_command" / "templates"
           / "gator-starter" / "reference-notes" / "loop-artifact-formats.md")
    text = fmt.read_text(encoding="utf-8")
    start = text.index("## Plan (written by the draftor)")
    fence = text.index("```markdown", start)
    tpl = text[fence + len("```markdown\n"):text.index("\n```\n", fence + 11)]
    present, items, problems = loop_submit.parse_coding_checkpoints(tpl)
    assert present and problems == [] and len(items) == 2


# ---------------------------------------------------------------------------
# Draft gate (one table): flagged vs legacy x absent / valid / invalid
# ---------------------------------------------------------------------------

def test_new_planning_sessions_carry_the_flag():
    s = loop_session.create_session("f", "f-loop", max_rounds=3, turn_timeout=300)
    assert s["contract"]["coding_checkpoints"] == 1
    c = loop_session.create_session(
        "f", "f-loop", mode="coding",
        coding={"source_loop_id": "src", "plan_sha256": "0" * 64,
                "base_head": "1" * 40, "base_tree": "2" * 40})
    assert "coding_checkpoints" not in c["contract"]


ABSENT = "# Plan\n\n## Context Checked\n\n- scripts-loop charter\n\n## Approach\n\nx\n"
GATE = [
    # (session, plan text, accepted?)
    ("flagged", ABSENT, False),
    ("flagged", _plan(ONE), True),
    ("flagged", _plan(TWO), True),
    ("flagged", _plan(f"1. **src/x.py** {EM} a. Verify: b."), False),
    ("legacy", ABSENT, True),
    ("legacy", _plan(TWO), True),
    ("legacy", _plan(f"1. **src/x.py** {EM} a. Verify: b."), True),  # rechecked at coding start
]


@pytest.mark.parametrize("kind,text,accepted", GATE,
                         ids=["flag-absent", "flag-one", "flag-two", "flag-invalid",
                              "legacy-absent", "legacy-valid", "legacy-invalid"])
def test_draft_gate(tmp_path, monkeypatch, kind, text, accepted):
    loop_dir, tok = _make_env(tmp_path, monkeypatch)
    if kind == "legacy":
        s = loop_session.load_session(loop_dir)
        s["contract"].pop("coding_checkpoints")
        loop_session.save_session(loop_dir, s)
    before = sorted(p.name for p in loop_dir.iterdir())
    draft = _write(tmp_path, "plan.md", text)
    if accepted:
        loop_submit.handle_submit_draft(tok["draftor"], str(draft))
        assert (loop_dir / "plan.current.md").read_bytes() == text.encode("utf-8")
        return
    with pytest.raises(ValueError) as exc:
        loop_submit.handle_submit_draft(tok["draftor"], str(draft))
    msg = str(exc.value)
    assert msg.startswith("Plan draft rejected:") and "Coding Checkpoints:" in msg
    if text == ABSENT:
        assert f"1. **Fix** {EM} <the change>. Verify: <the focused test>." in msg
    assert sorted(p.name for p in loop_dir.iterdir()) == before   # atomic
    assert loop_session.load_session(loop_dir)["status"]["stage"] == "plan_drafting"


def test_both_contracts_reported_together(tmp_path, monkeypatch):
    loop_dir, tok = _make_env(tmp_path, monkeypatch)
    draft = _write(tmp_path, "plan.md", "# Plan\n\n## Approach\n\nx\n")
    with pytest.raises(ValueError) as exc:
        loop_submit.handle_submit_draft(tok["draftor"], str(draft))
    assert "Context Checked" in str(exc.value) and "Coding Checkpoints:" in str(exc.value)


def test_in_lock_gate_is_authoritative(tmp_path, monkeypatch):
    """A file swapped after capture can't land: the captured bytes are what
    is checked inside the lock and persisted (#46 pattern)."""
    loop_dir, tok = _make_env(tmp_path, monkeypatch)
    draft = _write(tmp_path, "plan.md", _plan(ONE))
    real_lock = loop_submit.with_session_lock

    def swapping_lock(d, fn):
        draft.write_bytes(ABSENT.encode("utf-8"))
        return real_lock(d, fn)
    monkeypatch.setattr(loop_submit, "with_session_lock", swapping_lock)
    loop_submit.handle_submit_draft(tok["draftor"], str(draft))
    assert (loop_dir / "plan.current.md").read_bytes() == _plan(ONE).encode("utf-8")


# ===========================================================================
# M2 — lifecycle, generation and evidence binding
# ===========================================================================

import json  # noqa: E402

import gitsnap  # noqa: E402
import host as loop_host  # noqa: E402

from test_loop_coding_mode import (  # noqa: E402,F401
    PLAN_TEXT, _tokens, git, loop_dirs, make_planning_source, repo, start_coding)
from test_loop_coding_submit import GOOD_ARTIFACT, write  # noqa: E402
from test_loop_coding_review import FINDINGS, REVIEW  # noqa: E402

TWO_CP_PLAN = (
    "# Implementation Plan\n\n## Executive Summary\n\n- approved\n\n"
    "## Coding Checkpoints\n\n"
    f"1. **Widget core** {EM} Add the widget module. Verify: unit test.\n"
    f"2. **Widget wiring** {EM} Wire the widget in. Verify: integration test.\n"
).encode("utf-8")
BAD_CP_PLAN = PLAN_TEXT + (
    f"\n## Coding Checkpoints\n\n1. **src/w.py** {EM} a. Verify: b.\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Coding start (one table): source flag x plan section
# ---------------------------------------------------------------------------

START = [
    # (legacy source?, plan, expected manifest source or error needle)
    (False, PLAN_TEXT, "no '## Coding Checkpoints' section"),
    (False, TWO_CP_PLAN, "declared"),
    (False, BAD_CP_PLAN, "looks like a file"),
    (True, PLAN_TEXT, "implicit"),
    (True, TWO_CP_PLAN, "declared"),
    (True, BAD_CP_PLAN, "looks like a file"),
]


@pytest.mark.parametrize("legacy,plan,expect", START, ids=[
    "flag-absent", "flag-valid", "flag-invalid",
    "legacy-absent", "legacy-valid", "legacy-invalid"])
def test_coding_start_table(repo, legacy, plan, expect):
    src_id, src_dir = make_planning_source(repo, plan=plan, legacy=legacy)
    before = loop_dirs(repo)
    if expect not in ("declared", "implicit"):
        with pytest.raises(ValueError) as exc:
            start_coding(repo, src_id)
        assert expect in str(exc.value)
        assert loop_dirs(repo) == before  # atomic: no partial directory
        return
    _loop_id, loop_dir = start_coding(repo, src_id)
    s = loop_session.load_session(loop_dir)
    m = s["coding"]["checkpoints"]
    assert m["source"] == expect and m["current"] == 0
    ids = [i["id"] for i in m["items"]]
    assert ids == (["cp1"] if expect == "implicit" else ["cp1", "cp2"])
    assert m["items"][0]["state"] == "active"
    assert m["items"][0]["base_tree"] == s["coding"]["base_tree"]
    assert all(i["state"] == "pending" and i["base_tree"] is None
               for i in m["items"][1:])
    if expect == "implicit":
        assert m["items"][0]["title"] == "Full implementation"
    # Frozen: editing the source plan afterwards never changes the manifest.
    (src_dir / "plan.current.md").write_bytes(BAD_CP_PLAN)
    assert loop_session.load_session(loop_dir)["coding"]["checkpoints"] == m


# ---------------------------------------------------------------------------
# D3 transition table: one two-checkpoint loop, max_rounds = 2, extend +1
# ---------------------------------------------------------------------------

@pytest.fixture
def cp_loop(repo, tmp_path):
    src_id, _ = make_planning_source(repo, plan=TWO_CP_PLAN, legacy=False)
    _loop_id, loop_dir = start_coding(repo, src_id, max_rounds=2)
    art = tmp_path / "impl.md"
    write(art, GOOD_ARTIFACT)
    return {"repo": repo, "loop_dir": loop_dir, "tok": _tokens(loop_dir),
            "art": art, "tmp": tmp_path}


def _stage(c, files):
    for name, text in files.items():
        write(c["repo"] / name, text)
        git(c["repo"], "add", name)


def _submit(c, cp):
    return loop_submit.handle_submit_implementation(
        c["tok"]["draftor"], str(c["art"]), loop_dir=c["loop_dir"],
        checkpoint=cp)


def _review(c, approve):
    f = c["tmp"] / ("approve.md" if approve else "findings.md")
    write(f, REVIEW if approve else FINDINGS)
    loop_submit.handle_submit_review(c["tok"]["reviewer"], str(f),
                                     approve=approve, loop_dir=c["loop_dir"])


def _events(c):
    return [json.loads(x) for x in (c["loop_dir"] / "events.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()]


def _git_state(repo):
    return (git(repo, "rev-parse", "HEAD").stdout,
            git(repo, "write-tree").stdout,
            git(repo, "for-each-ref").stdout)


def _artifacts(c):
    return {p.name: p.read_bytes() for p in c["loop_dir"].glob("*.round-*.md")}


# (action, arg, stage, role, generations, new artifacts, status.round,
#  manifest current, active findings_rounds, event)
TRANSITIONS = [
    ("submit", ("cp1", {"a.py": "a1\n", "c.py": "c\n"}),
     "implementation_review", "reviewer", 1, ["implementation.round-0.md"],
     0, 0, 0, "implementation_submitted"),
    ("review", False, "implementation_revision", "draftor", 1,
     ["findings.round-0.md"], 1, 0, 1, "revision_requested"),
    ("submit", ("cp1", {"a.py": "a2\n"}), "implementation_review", "reviewer",
     2, ["implementation.round-1.md"], 1, 0, 1, "implementation_submitted"),
    ("review", True, "implementation_drafting", "draftor", 2,
     ["findings.round-1.md"], 1, 1, 0, "checkpoint_approved"),
    ("pause", None, "paused_by_architect", None, 2, [], 1, 1, 0, "loop_paused"),
    ("unblock", None, "implementation_drafting", "draftor", 2, [], 1, 1, 0,
     "loop_unblocked"),
    ("submit", ("cp2", {"b.py": "b1\n", "a.py": "a3\n"}),
     "implementation_review", "reviewer", 3, ["implementation.round-2.md"],
     1, 1, 0, "implementation_submitted"),
    ("review", False, "implementation_revision", "draftor", 3,
     ["findings.round-2.md"], 2, 1, 1, "revision_requested"),
    ("submit", ("cp2", {"b.py": "b2\n"}), "implementation_review", "reviewer",
     4, ["implementation.round-3.md"], 2, 1, 1, "implementation_submitted"),
    ("review", False, "max_rounds_exceeded", None, 4, ["findings.round-3.md"],
     3, 1, 2, "max_rounds_exceeded"),
    ("extend", 1, "implementation_revision", "draftor", 4, [], 3, 1, 2,
     "loop_extended"),
    ("submit", ("cp2", {"b.py": "b3\n"}), "implementation_review", "reviewer",
     5, ["implementation.round-4.md"], 3, 1, 2, "implementation_submitted"),
    ("review", True, "implementation_approved", None, 5,
     ["findings.round-4.md"], 3, 1, 2, "implementation_approved"),
    ("reopen", None, "implementation_revision", "draftor", 5, [], 3, 1, 2,
     "loop_reopened"),
    ("submit", ("cp2", {"b.py": "b4\n"}), "implementation_review", "reviewer",
     6, ["implementation.round-5.md"], 3, 1, 2, "implementation_submitted"),
]

GEN_EVENTS = ("implementation_submitted", "revision_requested",
              "max_rounds_exceeded", "checkpoint_approved",
              "implementation_approved")


def test_transition_table(cp_loop):
    c = cp_loop
    d = c["loop_dir"]
    # Binding: only the active checkpoint can be submitted.
    _stage(c, {"a.py": "a0\n"})
    before = (d / "session.json").read_bytes()
    for wrong in ("cp2", None):
        with pytest.raises(ValueError, match="active checkpoint is cp1"):
            _submit(c, wrong)
    assert (d / "session.json").read_bytes() == before
    assert not _artifacts(c)

    seen = {}
    for (action, arg, stage, role, n_gens, written, rnd, cur, spent,
         ev) in TRANSITIONS:
        label = f"{action} -> {stage} ({ev})"
        git_before = _git_state(c["repo"])
        if action == "submit":
            _stage(c, arg[1])
            _submit(c, arg[0])
        elif action == "review":
            _review(c, arg)
        elif action == "pause":
            loop_submit.handle_pause(c["tok"]["architect"], "hold",
                                     loop_dir=d)
        elif action == "unblock":
            loop_submit.handle_unblock(c["tok"]["architect"], loop_dir=d)
        elif action == "extend":
            loop_host.extend_loop(c["tok"]["architect"], arg, "more",
                                  loop_dir=d)
        elif action == "reopen":
            loop_host.reopen_loop(c["tok"]["architect"], "again", loop_dir=d)

        s = loop_session.load_session(d)
        st, m = s["status"], s["coding"]["checkpoints"]
        assert st["stage"] == stage, label
        assert st["next_role"] == role, label
        assert [g["generation"] for g in s["coding"]["generations"]] == \
            list(range(n_gens)), label
        assert st["round"] == rnd, label
        assert m["current"] == cur, label
        assert m["items"][cur]["findings_rounds"] == spent, label
        e = _events(c)[-1]
        assert e["event"] == ev, label

        # Every artifact name is unique and nothing is ever overwritten.
        now = _artifacts(c)
        assert sorted(set(now) - set(seen)) == sorted(written), label
        for name, data in seen.items():
            assert now[name] == data, f"{label}: {name} overwritten"
        seen = now

        if ev in GEN_EVENTS:
            assert e["generation"] == n_gens - 1, label
            reviewed_idx = cur - 1 if ev == "checkpoint_approved" else cur
            assert e["checkpoint_id"] == f"cp{reviewed_idx + 1}", label
        if ev in ("revision_requested", "max_rounds_exceeded"):
            assert e["findings_round"] == spent, label
        if ev == "implementation_submitted":
            assert e["checkpoint_index"] == cur + 1
            assert e["checkpoint_count"] == 2
            assert e["checkpoint_base_tree"] == m["items"][cur]["base_tree"]
        if ev == "checkpoint_approved":
            cp1, cp2 = m["items"]
            assert cp1["state"] == "approved" and cp2["state"] == "active"
            assert cp1["accepted"]["generation"] == 1
            assert cp2["base_tree"] == cp1["accepted"]["tree"] == \
                e["accepted_tree"]
            assert e["next_checkpoint_id"] == "cp2"
            # Never authorizes a commit; no Git mutation per checkpoint.
            assert s["coding"]["approval"] is None
            assert _git_state(c["repo"]) == git_before
        if ev == "implementation_approved":
            assert s["coding"]["approval"]["generation"] == 4
            assert m["items"][1]["accepted"]["generation"] == 4
        if ev == "loop_extended":
            assert st["max_rounds"] == 3   # budget raised; guard used cp2's 2
        if ev == "loop_reopened":
            assert m["items"][1]["state"] == "active"
            assert m["items"][1]["accepted"]["invalidated_at"]
            assert m["items"][0]["state"] == "approved"   # never reopened
            assert s["coding"]["approval"]["invalidated_at"]

    # Escalate + unblock preserve the checkpoint and the turn.
    loop_submit.handle_escalate(c["tok"]["reviewer"], "need a decision")
    loop_submit.handle_unblock(c["tok"]["architect"], message="decided",
                               loop_dir=d)
    s = loop_session.load_session(d)
    assert s["status"]["stage"] == "implementation_review"
    assert s["status"]["next_role"] == "reviewer"
    assert s["coding"]["checkpoints"]["current"] == 1


def test_findings_keep_the_checkpoint_base(cp_loop):
    c = cp_loop
    _stage(c, {"a.py": "a\n"})
    _submit(c, "cp1")
    _review(c, False)
    s = loop_session.load_session(c["loop_dir"])
    m = s["coding"]["checkpoints"]
    assert m["current"] == 0 and m["items"][1]["base_tree"] is None
    assert m["items"][0]["base_tree"] == s["coding"]["base_tree"]


def test_nothing_staged_beyond_checkpoint_base(cp_loop):
    c = cp_loop
    _stage(c, {"a.py": "a\n"})
    _submit(c, "cp1")
    _review(c, True)
    with pytest.raises(ValueError, match="beyond checkpoint cp2's base"):
        _submit(c, "cp2")


# ---------------------------------------------------------------------------
# Exact checkpoint diff and revisit disclosure
# ---------------------------------------------------------------------------

def test_checkpoint_diff_and_revisit(cp_loop):
    c = cp_loop
    d = c["loop_dir"]
    _stage(c, {"a.py": "a1\n", "c.py": "c\n"})
    _submit(c, "cp1")
    _review(c, True)
    cp1_tree = loop_session.load_session(d)["coding"]["checkpoints"][
        "items"][0]["accepted"]["tree"]
    _stage(c, {"b.py": "b\n", "a.py": "a2\n"})
    _submit(c, "cp2")
    s = loop_session.load_session(d)
    staged = s["coding"]["generations"][-1]["snapshot"]["staged_tree"]
    text = (d / "implementation.round-1.md").read_text(encoding="utf-8")
    start = text.index("Changed paths in this checkpoint (status")
    fence = text.index("```text\n", start) + len("```text\n")
    block = text[fence:text.index("```", fence)].splitlines()
    assert f"git diff {cp1_tree} {staged}" in text
    assert f"| Checkpoint | cp2 (2 of 2) {EM} Widget wiring |" in text
    assert "| Generation | 1 |" in text
    assert block == ["M a.py  [revisits an earlier checkpoint]", "A b.py"]
    assert s["coding"]["generations"][-1]["checkpoint"] == {
        "id": "cp2", "index": 1, "base_tree": cp1_tree,
        "changed_count": 2, "revisited_count": 1}
    # The review artifact names the checkpoint, its base and the generation.
    _review(c, False)
    rv = (d / "findings.round-1.md").read_text(encoding="utf-8")
    assert f"| Checkpoint | cp2 (2 of 2) {EM} Widget wiring |" in rv
    assert f"| Checkpoint base tree | `{cp1_tree}` |" in rv
    assert "| Generation | 1 |" in rv


def test_diff_trees_is_a_pure_read(repo):
    base = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    write(repo / "x.py", "x\n")
    git(repo, "add", "x.py")
    staged = git(repo, "write-tree").stdout.strip()
    index = (repo / ".git" / "index").read_bytes()
    r = gitsnap.diff_trees(repo, base, staged)
    assert r == {"ok": True, "changed_paths": [{"status": "A", "path": "x.py"}],
                 "changed_truncated": 0}
    assert (repo / ".git" / "index").read_bytes() == index
    assert not (repo / ".git" / "index.lock").exists()
    bad = gitsnap.diff_trees(repo, "0" * 40, staged)
    assert bad["ok"] is False and bad["error"] == "git_error"


# ---------------------------------------------------------------------------
# Legacy: implicit manifests and pre-#55 coding sessions
# ---------------------------------------------------------------------------

@pytest.fixture
def legacy_loop(repo, tmp_path):
    src_id, _ = make_planning_source(repo)   # pre-#55 source, no section
    _loop_id, loop_dir = start_coding(repo, src_id)
    art = tmp_path / "impl.md"
    write(art, GOOD_ARTIFACT)
    return {"repo": repo, "loop_dir": loop_dir, "tok": _tokens(loop_dir),
            "art": art, "tmp": tmp_path}


def _drop_manifest(c):
    """Simulate a coding session created before #55 (no manifest)."""
    s = loop_session.load_session(c["loop_dir"])
    s["coding"].pop("checkpoints")
    loop_session.save_session(c["loop_dir"], s)


@pytest.mark.parametrize("pre55", [True, False], ids=["no-manifest", "implicit"])
def test_legacy_reopen_never_overwrites(legacy_loop, pre55):
    c = legacy_loop
    if pre55:
        _drop_manifest(c)
    _stage(c, {"a.py": "a1\n"})
    _submit(c, None)
    _review(c, False)                      # round 1
    _stage(c, {"a.py": "a2\n"})
    _submit(c, None)                       # generation 1 == status.round 1
    _review(c, True)
    approved = _artifacts(c)
    assert sorted(approved) == ["findings.round-0.md", "findings.round-1.md",
                                "implementation.round-0.md",
                                "implementation.round-1.md"]
    loop_host.reopen_loop(c["tok"]["architect"], "again",
                          loop_dir=c["loop_dir"])
    _stage(c, {"a.py": "a3\n"})
    _submit(c, None)
    _review(c, False)
    now = _artifacts(c)
    for name, data in approved.items():
        assert now[name] == data           # the approved round survives
    assert "implementation.round-2.md" in now and "findings.round-2.md" in now
    s = loop_session.load_session(c["loop_dir"])
    assert s["status"]["round"] == 2       # the counter itself is unchanged


def test_legacy_surface_unchanged(legacy_loop):
    c = legacy_loop
    _stage(c, {"a.py": "a1\n"})
    # Implicit checkpoint: --checkpoint optional; cp1 accepted, others not.
    with pytest.raises(ValueError, match="active checkpoint is cp1"):
        _submit(c, "cp2")
    _submit(c, "cp1")
    text = (c["loop_dir"] / "implementation.round-0.md").read_text(
        encoding="utf-8")
    assert "| Checkpoint |" not in text and "| Base tree |" in text
    # A pre-#55 session (no manifest) rejects the flag outright.
    _review(c, False)
    _drop_manifest(c)
    with pytest.raises(ValueError, match="has no checkpoints"):
        _submit(c, "cp1")


# ===========================================================================
# M3 — participant guidance: CLI text and counters
# ===========================================================================

import subprocess  # noqa: E402

GATOR_LOOP = SCRIPTS_DIR / "gator-loop.py"


def _cli(c, *args):
    r = subprocess.run([sys.executable, str(GATOR_LOOP), *args],
                       cwd=str(c["repo"]), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    return r.returncode, r.stdout + r.stderr


def _status(c, role, *extra):
    return _cli(c, "status", "--token", c["tok"][role], *extra)


@pytest.mark.parametrize("role", ["draftor", "reviewer"])
def test_cli_action_names_the_checkpoint(cp_loop, role):
    c = cp_loop
    _stage(c, {"a.py": "a1\n"})
    _submit(c, "cp1")
    _review(c, True)                          # cp1 approved -> cp2 active
    s = loop_session.load_session(c["loop_dir"])
    cp2_base = s["coding"]["checkpoints"]["items"][1]["base_tree"]
    if role == "reviewer":
        _stage(c, {"b.py": "b1\n"})
        _submit(c, "cp2")
        staged = loop_session.load_session(c["loop_dir"])["coding"][
            "generations"][-1]["snapshot"]["staged_tree"]
    code, out = _status(c, role)
    assert code == 0, out
    head = "checkpoint 2 of 2 -- Widget wiring"
    if role == "draftor":
        assert f"Action: Implement {head}." in out
        assert "Scope: Wire the widget in." in out
        assert "Verify: integration test." in out
        assert f"Checkpoint base tree: {cp2_base}" in out
        assert (f"submit-implementation --token {c['tok']['draftor']} "
                "--checkpoint cp2 --file") in out
    else:
        assert f"Review real code changed for {head} (generation 1)." in out
        assert f"Review exactly this checkpoint: git diff {cp2_base} {staged}" in out
        assert "final checkpoint: approval authorizes" in out
    assert "Checkpoint: 2 of 2 -- Widget wiring (findings round 0 of 2)" in out
    assert "Round:" not in out


def test_cli_non_final_reviewer_is_told_no_commit(cp_loop):
    c = cp_loop
    _stage(c, {"a.py": "a1\n"})
    _submit(c, "cp1")
    _code, out = _status(c, "reviewer")
    assert "does NOT" in out and "authorize a commit" in out
    assert "Generation: 0" in out


def _drive_to_budget(c):
    """cp1 approved; cp2 at max_rounds_exceeded with status.round 3 > 2."""
    _stage(c, {"a.py": "a1\n"})
    _submit(c, "cp1")
    _review(c, False)
    _stage(c, {"a.py": "a2\n"})
    _submit(c, "cp1")
    _review(c, True)
    for n in (1, 2):
        _stage(c, {"b.py": f"b{n}\n"})
        _submit(c, "cp2")
        _review(c, False)
    s = loop_session.load_session(c["loop_dir"])
    assert s["status"]["stage"] == "max_rounds_exceeded"
    assert (s["status"]["round"], s["status"]["max_rounds"]) == (3, 2)


def test_cli_counters_never_show_round_over_budget(cp_loop):
    c = cp_loop
    _drive_to_budget(c)
    for role in ("draftor", "architect"):
        _code, out = _status(c, role)
        assert "Checkpoint: 2 of 2 -- Widget wiring (findings round 2 of 2)" in out
        assert "Generation: 3" in out
        assert "Round:" not in out and "3/2" not in out
        assert "Findings budget exceeded for checkpoint cp2 (2 of 2)" in out
    _code, out = _cli(c, "list")
    assert "cp 2/2 findings 2/2" in out and "3/2" not in out
    _code, out = _cli(c, "list", "--json")
    item = json.loads(out)["loops"]
    item = [i for i in item if i.get("checkpoint_summary")][0]
    assert item["checkpoint_summary"] == {
        "index": 2, "count": 2, "findings_round": 2, "findings_budget": 2,
        "generation": 3}


def test_cli_status_json_is_additive(cp_loop):
    c = cp_loop
    _stage(c, {"a.py": "a1\n"})
    _submit(c, "cp1")
    _code, out = _status(c, "reviewer", "--json")
    j = json.loads(out)
    assert j["round"] == 0 and j["max_rounds"] == 2     # kept for compatibility
    assert j["checkpoint"] == {"index": 1, "count": 2, "id": "cp1",
                               "title": "Widget core", "state": "active",
                               "findings_round": 0, "findings_budget": 2}
    assert j["checkpoints"] == [
        {"id": "cp1", "index": 1, "title": "Widget core", "state": "active"},
        {"id": "cp2", "index": 2, "title": "Widget wiring", "state": "pending"}]
    assert j["generation"] == 0
    assert "scope" not in out and "verify" not in out.lower().replace(
        "verify_", "")


def test_cli_submit_and_review_output(cp_loop):
    c = cp_loop
    _stage(c, {"a.py": "a1\n", "c.py": "c\n"})
    code, out = _cli(c, "submit-implementation", "--token", c["tok"]["draftor"],
                     "--file", str(c["art"]))
    assert code == 1 and "active checkpoint is cp1" in out
    code, out = _cli(c, "submit-implementation", "--token", c["tok"]["draftor"],
                     "--checkpoint", "cp1", "--file", str(c["art"]))
    assert code == 0, out
    assert "Checkpoint cp1 submitted (generation 0)" in out
    assert "Changed paths in this checkpoint: 2" in out
    f = c["tmp"] / "ok.md"
    write(f, REVIEW)
    code, out = _cli(c, "submit-review", "--token", c["tok"]["reviewer"],
                     "--file", str(f), "--approve")
    assert code == 0, out
    assert "Checkpoint cp1 approved; the Draftor continues with cp2. No commit yet." in out
    _stage(c, {"a.py": "a2\n"})
    _cli(c, "submit-implementation", "--token", c["tok"]["draftor"],
         "--checkpoint", "cp2", "--file", str(c["art"]))
    code, out = _cli(c, "submit-implementation", "--token", c["tok"]["draftor"],
                     "--checkpoint", "cp2", "--file", str(c["art"]))
    assert code == 1   # not the Draftor's turn any more
    f = c["tmp"] / "no.md"
    write(f, FINDINGS)
    code, out = _cli(c, "submit-review", "--token", c["tok"]["reviewer"],
                     "--file", str(f))
    assert "Checkpoint cp2: findings round 1 of 2 (generation 1)." in out


def test_cli_legacy_surface_keeps_round(legacy_loop):
    c = legacy_loop
    code, out = _status(c, "draftor")
    assert "Round: 0/3" in out and "Checkpoint:" not in out
    assert "--checkpoint" not in out
    _code, out = _status(c, "draftor", "--json")
    j = json.loads(out)
    assert not {"checkpoint", "checkpoints", "generation"} & set(j)
