"""
#62 — Executive Summary paragraph captured onto Timeline events.

Covers the closed one-paragraph parser, the new-session contract flag, the
projection on every participant event (planning and coding, with the
Reviewer's own text), atomic rejection on all four submit paths, the
capture-once planning review, and the unchanged legacy contract.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import session as loop_session  # noqa: E402
import submit as loop_submit  # noqa: E402

from test_loop_context_evidence import (  # noqa: E402
    GOOD_PLAN, _make_env, _snapshot, _write)
from test_loop_coding_mode import repo  # noqa: E402,F401  (fixture)
from test_loop_checkpoints import (  # noqa: E402,F401
    _events, _stage, _submit, cp_loop)
from test_loop_coding_submit import GOOD_ARTIFACT, write  # noqa: E402

DRAFT_SUMMARY = "The draft plan fixes the widget. The Reviewer checks it next."
REVIEW_SUMMARY = "The plan is sound but needs a recovery step before approval."
IMPL_SUMMARY = "Adds the widget."  # GOOD_ARTIFACT's paragraph

PLAN = GOOD_PLAN.replace(
    "## Executive Summary\n\nx\n",
    "## Executive Summary\n\nThe draft plan fixes the widget.\n"
    "The Reviewer checks it next.\n")


def _review_text(verdict, summary=REVIEW_SUMMARY):
    return (f"# Review\n\n## Executive Summary\n\n{summary}\n\n"
            f"## Verdict\n\n{verdict}\n")


def _last_event(loop_dir):
    lines = (Path(loop_dir) / "events.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1])


def _unflag(loop_dir):
    s = loop_session.load_session(loop_dir)
    s["contract"].pop("executive_summary", None)
    loop_session.save_session(loop_dir, s)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expect", [
    ("## Executive Summary\n\nOne line\nwrapped  here.\n\n## Next\n",
     "One line wrapped here."),
    ("## Executive Summary\n<!-- note -->\nKept text.\n", "Kept text."),
    ("## executive summary\n\nCase is ignored.\n", "Case is ignored."),
    ("```\n## Executive Summary\n- fenced\n```\n\n## Executive Summary\n\n"
     "Real paragraph.\n", "Real paragraph."),
    ("## Executive Summary\n\n" + "a" * 1200 + "\n", "a" * 1200),
    # Review finding 1: hidden headings neither satisfy nor duplicate.
    ("## Executive Summary\n\nVisible text.\n\n<!--\n## Executive Summary\n"
     "Hidden.\n-->\n## Next\n", "Visible text."),
    ("````\n```\n## Executive Summary\n\nFenced.\n````\n\n"
     "## Executive Summary\n\nVisible text.\n", "Visible text."),
], ids=["collapsed", "comment", "case", "fenced-ignored", "at-limit",
        "commented-duplicate-ignored", "long-fence-duplicate-ignored"])
def test_parser_accepts(text, expect):
    assert loop_submit.executive_summary_problems(text) == (expect, [])


@pytest.mark.parametrize("text,needle", [
    ("# Plan\n\n## Approach\n\nx\n", "missing"),
    ("## Executive Summary\n\nA.\n\n## Executive Summary\n\nB.\n",
     "more than one"),
    ("## Executive Summary\n\n\n## Next\n", "empty"),
    ("## Executive Summary\n<!-- only a comment -->\n", "empty"),
    ("## Executive Summary\n\n- one\n- two\n", "one prose paragraph"),
    ("## Executive Summary\n\nIntro text.\n1. item\n", "one prose paragraph"),
    ("## Executive Summary\n\nFirst.\n\nSecond.\n", "exactly one paragraph"),
    ("## Executive Summary\n\n" + "a" * 1201 + "\n", "1201 characters"),
    ("## Executive Summary\n\nTBD\n", "placeholder"),
    ("## Executive Summary\n\n...\n", "placeholder"),
    ("```\n## Executive Summary\n\nFenced only.\n```\n", "missing"),
    # Review finding 1: text a reader cannot see is never a summary.
    ("<!--\n## Executive Summary\nHidden summary.\n## Next\n-->\n", "missing"),
    ("<!-- unterminated\n## Executive Summary\n\nHidden.\n", "missing"),
    ("````\n```\n## Executive Summary\n\nOnly a fenced example.\n\n"
     "## Next\n````\n", "missing"),
    ("~~~\n```\n## Executive Summary\n\nTilde-fenced.\n~~~\n", "missing"),
], ids=["missing", "duplicate", "blank", "comment-only", "list-only",
        "mixed-list", "two-paragraphs", "overlong", "placeholder",
        "ellipsis", "fenced-only", "comment-hidden-heading",
        "unterminated-comment", "longer-fence", "mismatched-fence"])
def test_parser_rejects(text, needle):
    summary, problems = loop_submit.executive_summary_problems(text)
    assert summary is None and len(problems) == 1
    assert needle in problems[0]


def test_new_sessions_flagged():
    planning = loop_session.create_session("f", "f-loop", max_rounds=3,
                                           turn_timeout=300)
    coding = loop_session.create_session(
        "f", "f-loop", mode="coding",
        coding={"source_loop": "x", "base_head": "h", "base_tree": "t"})
    assert planning["contract"]["executive_summary"] == 1
    assert coding["contract"]["executive_summary"] == 1


# ---------------------------------------------------------------------------
# Planning projection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("outcome,event", [
    ("draft", "draft_submitted"),
    ("findings", "revision_requested"),
    ("approve", "plan_approved"),
    ("max-rounds", "max_rounds_exceeded"),
])
def test_planning_events_carry_own_summary(tmp_path, monkeypatch, outcome,
                                           event):
    loop_dir, tok = _make_env(tmp_path, monkeypatch)
    loop_submit.handle_submit_draft(tok["draftor"],
                                    str(_write(tmp_path, "plan.md", PLAN)))
    if outcome == "draft":
        ev = _last_event(loop_dir)
        assert ev["event"] == event and ev["artifact_path"] == "plan.round-0.md"
        assert ev["executive_summary"] == DRAFT_SUMMARY
        return
    if outcome == "max-rounds":
        s = loop_session.load_session(loop_dir)
        s["status"]["max_rounds"] = 1
        loop_session.save_session(loop_dir, s)
    approve = outcome == "approve"
    review = _write(tmp_path, "r.md",
                    _review_text("APPROVE" if approve else "REVISE"))
    loop_submit.handle_submit_review(tok["reviewer"], str(review),
                                     approve=approve)
    ev = _last_event(loop_dir)
    assert ev["event"] == event
    assert ev["artifact_path"] == "findings.round-0.md"
    assert ev["executive_summary"] == REVIEW_SUMMARY  # never the Draftor's
    assert (loop_dir / "findings.round-0.md").read_bytes() == review.read_bytes()


def test_planning_review_persists_captured_bytes(tmp_path, monkeypatch):
    """A source rewritten after the pre-lock read is never persisted: the
    stored artifact and its summary are the captured bytes."""
    loop_dir, tok = _make_env(tmp_path, monkeypatch)
    loop_submit.handle_submit_draft(tok["draftor"],
                                    str(_write(tmp_path, "plan.md", PLAN)))
    review = _write(tmp_path, "r.md", _review_text("REVISE"))
    captured = review.read_bytes()
    real = loop_submit.with_session_lock

    def swap_then_lock(d, fn):
        review.write_bytes(_review_text("REVISE", "Swapped text.").encode())
        return real(d, fn)
    monkeypatch.setattr(loop_submit, "with_session_lock", swap_then_lock)
    loop_submit.handle_submit_review(tok["reviewer"], str(review))
    assert (loop_dir / "findings.round-0.md").read_bytes() == captured
    assert (loop_dir / "findings.current.md").read_bytes() == captured
    assert _last_event(loop_dir)["executive_summary"] == REVIEW_SUMMARY


# ---------------------------------------------------------------------------
# Coding projection (two-checkpoint loop, max_rounds = 2)
# ---------------------------------------------------------------------------

def _coding_review(c, approve, summary=REVIEW_SUMMARY):
    f = c["tmp"] / ("approve.md" if approve else "findings.md")
    write(f, _review_text("APPROVE" if approve else "REVISE", summary))
    loop_submit.handle_submit_review(c["tok"]["reviewer"], str(f),
                                     approve=approve, loop_dir=c["loop_dir"])


@pytest.mark.parametrize("outcome,event", [
    ("implementation", "implementation_submitted"),
    ("findings", "revision_requested"),
    ("checkpoint", "checkpoint_approved"),
    ("final", "implementation_approved"),
    ("max-rounds", "max_rounds_exceeded"),
])
def test_coding_events_carry_summary(cp_loop, outcome, event):
    c = cp_loop
    _stage(c, {"w.py": "x = 1\n"})
    _submit(c, "cp1")
    if outcome == "findings":
        _coding_review(c, False)
    elif outcome == "checkpoint":
        _coding_review(c, True)
    elif outcome == "final":
        _coding_review(c, True)
        _stage(c, {"wire.py": "y = 2\n"})
        _submit(c, "cp2")
        _coding_review(c, True)
    elif outcome == "max-rounds":
        _coding_review(c, False)
        _stage(c, {"w.py": "x = 2\n"})
        _submit(c, "cp1")
        _coding_review(c, False)
    ev = _events(c)[-1]
    assert ev["event"] == event
    expected = IMPL_SUMMARY if outcome == "implementation" else REVIEW_SUMMARY
    # Taken from the participant text: never the CLI-owned Commit State or
    # Reviewed Candidate sections.
    assert ev["executive_summary"] == expected
    assert ev["artifact_path"].endswith(".md")


# ---------------------------------------------------------------------------
# Atomic rejection and the legacy contract (all four submit paths)
# ---------------------------------------------------------------------------

BAD = "# Artifact\n\n## Executive Summary\n\n- a list, not a paragraph\n"
BAD_IMPL = GOOD_ARTIFACT.replace("Adds the widget.\n", "- Adds the widget.\n")


def _to_planning_review(tmp_path, monkeypatch, flagged=True):
    loop_dir, tok = _make_env(tmp_path, monkeypatch)
    loop_submit.handle_submit_draft(tok["draftor"],
                                    str(_write(tmp_path, "plan.md", PLAN)))
    if not flagged:
        _unflag(loop_dir)
    return loop_dir, tok


@pytest.mark.parametrize("path", ["draft", "plan-review"])
def test_planning_rejection_is_atomic(tmp_path, monkeypatch, path):
    if path == "draft":
        loop_dir, tok = _make_env(tmp_path, monkeypatch)
        act = lambda: loop_submit.handle_submit_draft(  # noqa: E731
            tok["draftor"], str(_write(tmp_path, "bad.md", GOOD_PLAN.replace(
                "## Executive Summary\n\nx\n",
                "## Executive Summary\n\n- x\n"))))
    else:
        loop_dir, tok = _to_planning_review(tmp_path, monkeypatch)
        act = lambda: loop_submit.handle_submit_review(  # noqa: E731
            tok["reviewer"], str(_write(tmp_path, "bad.md", BAD)))
    before = _snapshot(loop_dir)
    with pytest.raises(ValueError, match="Executive Summary"):
        act()
    assert _snapshot(loop_dir) == before


def test_hidden_only_summary_creates_no_event(tmp_path, monkeypatch):
    """Review finding 1: a summary visible only inside a comment or a
    fenced example is rejected on a flagged submit; nothing is written."""
    loop_dir, tok = _to_planning_review(tmp_path, monkeypatch)
    hidden = ("# Review\n\n<!--\n## Executive Summary\nHidden summary.\n-->\n\n"
              "````\n```\n## Executive Summary\n\nFenced example.\n````\n\n"
              "## Verdict\n\nREVISE\n")
    before = _snapshot(loop_dir)
    with pytest.raises(ValueError, match="missing a '## Executive Summary'"):
        loop_submit.handle_submit_review(tok["reviewer"],
                                         str(_write(tmp_path, "h.md", hidden)))
    assert _snapshot(loop_dir) == before


@pytest.mark.parametrize("path", ["implementation", "coding-review"])
def test_coding_rejection_is_atomic(cp_loop, path):
    c = cp_loop
    _stage(c, {"w.py": "x = 1\n"})
    if path == "implementation":
        write(c["art"], BAD_IMPL)
        act = lambda: _submit(c, "cp1")  # noqa: E731
    else:
        _submit(c, "cp1")
        f = c["tmp"] / "bad.md"
        write(f, BAD)
        act = lambda: loop_submit.handle_submit_review(  # noqa: E731
            c["tok"]["reviewer"], str(f), loop_dir=c["loop_dir"])
    def state():  # session.lock is created by the first lock, never data
        return {k: v for k, v in _snapshot(c["loop_dir"]).items()
                if k != "session.lock"}
    before = state()
    with pytest.raises(ValueError, match="Executive Summary"):
        act()
    assert state() == before


def test_legacy_planning_unchanged(tmp_path, monkeypatch):
    """Unflagged: no summary required on review, and no field written."""
    loop_dir, tok = _to_planning_review(tmp_path, monkeypatch, flagged=False)
    review = _write(tmp_path, "r.md", "# Review\n\nREVISE, no summary.\n")
    loop_submit.handle_submit_review(tok["reviewer"], str(review))
    ev = _last_event(loop_dir)
    assert ev["event"] == "revision_requested"
    assert "executive_summary" not in ev
    assert (loop_dir / "findings.round-0.md").read_bytes() == review.read_bytes()


def test_legacy_coding_unchanged(cp_loop):
    c = cp_loop
    _unflag(c["loop_dir"])
    write(c["art"], BAD_IMPL)
    _stage(c, {"w.py": "x = 1\n"})
    _submit(c, "cp1")
    assert "executive_summary" not in _events(c)[-1]
    f = c["tmp"] / "bad.md"
    write(f, BAD)
    loop_submit.handle_submit_review(c["tok"]["reviewer"], str(f),
                                     loop_dir=c["loop_dir"])
    ev = _events(c)[-1]
    assert ev["event"] == "revision_requested"
    assert "executive_summary" not in ev


# ---------------------------------------------------------------------------
# Display bound (checkpoint 2): the Timeline's limit is the CLI's limit
# ---------------------------------------------------------------------------

def test_summary_bound_matches_cli():
    import re
    js = (SCRIPTS_DIR / "dashboard" / "views" / "loop.js").read_text(
        encoding="utf-8")
    m = re.search(r"var EXECUTIVE_SUMMARY_MAX = (\d+);", js)
    assert m and int(m.group(1)) == loop_submit.EXECUTIVE_SUMMARY_MAX
    # Same unit as the CLI (code points): an astral character at the limit
    # is accepted here, and the browser counts it with Array.from().
    text = "## Executive Summary\n\n\U0001F600" + "a" * 1199 + "\n"
    assert loop_submit.executive_summary_problems(text)[1] == []
    assert "Array.from(text).length > EXECUTIVE_SUMMARY_MAX" in js
