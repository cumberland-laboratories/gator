"""
Tests for #46: plan-draft context evidence (``## Context Checked``).

Covers the structural validator, the flagged-session submit path (captured
bytes validated and persisted inside the lock), the legacy migration
boundary, coding-mode isolation, a swap race, and drift guards on the
shipped plan template and loop protocol.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import session as loop_session
import events as loop_events
import submit as loop_submit


GOOD_PLAN = (
    "# Plan\n\n## Executive Summary\n\n- x\n\n"
    "## Context Checked\n\n- `.gator/charters/scripts-loop.md`\n"
    "- `src/gator_command/scripts/loop/submit.py`\n\n"
    "## Approach\n\nDo the thing.\n"
)
OLD_PLAN = "# Plan\n\n## Executive Summary\n\n- x\n\n## Approach\n\nDo it.\n"


def _plan(body):
    return f"# Plan\n\n## Context Checked\n\n{body}\n\n## Approach\n\nx\n"


# ---------------------------------------------------------------------------
# Unit: context_checked_problems
# ---------------------------------------------------------------------------

class TestValidator:
    def test_populated_ok(self):
        assert loop_submit.context_checked_problems(GOOD_PLAN) == []

    @pytest.mark.parametrize("body", [
        "None — greenfield script with no existing charter or code",
        "None - the sketch is self-contained; no charters apply",
        "None: new top-level tool, nothing to read yet",
    ], ids=["em-dash", "hyphen", "colon"])
    def test_none_with_reason_ok(self, body):
        assert loop_submit.context_checked_problems(_plan(body)) == []

    @pytest.mark.parametrize("body", [
        "None", "none.", "N/A", "n/a", "-", "TBD", "TODO", "Nothing", "- None",
    ])
    def test_bare_placeholder_rejected(self, body):
        problems = loop_submit.context_checked_problems(_plan(body))
        assert len(problems) == 1 and "placeholder" in problems[0]

    def test_missing_rejected(self):
        problems = loop_submit.context_checked_problems(OLD_PLAN)
        assert len(problems) == 1 and "missing" in problems[0]

    @pytest.mark.parametrize("body", ["", "   \n\n", "<!-- list what you read -->",
                                      "<!--\nmulti\nline\n-->\n"],
                             ids=["empty", "blank", "comment", "multiline-comment"])
    def test_empty_or_comment_only_rejected(self, body):
        problems = loop_submit.context_checked_problems(_plan(body))
        assert len(problems) == 1 and "empty" in problems[0]

    def test_empty_at_eof_rejected(self):
        problems = loop_submit.context_checked_problems("# Plan\n\n## Context Checked\n")
        assert problems and "empty" in problems[0]

    def test_duplicate_rejected(self):
        text = GOOD_PLAN + "\n## Context Checked\n\n- more\n"
        problems = loop_submit.context_checked_problems(text)
        assert len(problems) == 1 and "more than one" in problems[0]

    def test_fenced_example_ignored(self):
        text = ("# Plan\n\n```markdown\n## Context Checked\n\n- example\n```\n\n"
                "## Approach\n\nx\n")
        problems = loop_submit.context_checked_problems(text)
        assert problems and "missing" in problems[0]

    def test_fenced_example_does_not_count_as_duplicate(self):
        text = GOOD_PLAN + "\n```\n## Context Checked\n- example\n```\n"
        assert loop_submit.context_checked_problems(text) == []

    def test_level3_heading_is_not_the_section(self):
        text = "# Plan\n\n### Context Checked\n\n- x\n"
        assert "missing" in loop_submit.context_checked_problems(text)[0]

    def test_heading_case_insensitive(self):
        assert loop_submit.context_checked_problems(_plan("- charter").replace(
            "Context Checked", "context checked")) == []

    def test_section_ends_at_next_h2(self):
        text = "# Plan\n\n## Context Checked\n\n## Approach\n\n- not context\n"
        assert "empty" in loop_submit.context_checked_problems(text)[0]


# ---------------------------------------------------------------------------
# Integration: handle_submit_draft
# ---------------------------------------------------------------------------

def _make_env(tmp_path, monkeypatch, *, flagged=True, mode=None):
    monkeypatch.setattr(loop_session, "find_gator_root", lambda start_path=None: tmp_path)
    monkeypatch.setattr(loop_submit, "find_gator_root", lambda start_path=None: tmp_path)
    loop_id = "ctx-feature-loop"
    loop_dir = tmp_path / ".gator" / "loops" / loop_id
    loop_dir.mkdir(parents=True)
    loop_session.ensure_loops_gitignore(loop_dir.parent)
    session = loop_session.create_session("ctx-feature", loop_id, max_rounds=3,
                                          turn_timeout=300)
    if not flagged:
        session.pop("contract", None)  # pre-#46 session shape
    if mode is not None:
        session["mode"] = mode
    loop_session.save_session(loop_dir, session)
    loop_events.create_events_file(loop_dir)
    tokens = {}
    for role in ("draftor", "reviewer", "architect"):
        tok, nonce = loop_session.make_token(loop_id, role)
        tokens[role] = {"nonce": nonce, "token": tok}
    loop_session.save_tokens(loop_dir, tokens)
    return loop_dir, {r: v["token"] for r, v in tokens.items()}


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    return p


def _snapshot(loop_dir):
    return {p.name: p.read_bytes() for p in loop_dir.iterdir() if p.is_file()}


class TestSubmitFlagged:
    def test_new_planning_session_carries_flag(self):
        s = loop_session.create_session("f", "f-loop", max_rounds=3, turn_timeout=300)
        assert s["contract"]["context_evidence"] == 1

    def test_missing_section_rejected_atomically(self, tmp_path, monkeypatch):
        loop_dir, tok = _make_env(tmp_path, monkeypatch)
        before = _snapshot(loop_dir)
        draft = _write(tmp_path, "plan.md", OLD_PLAN)
        with pytest.raises(ValueError, match="Context Checked"):
            loop_submit.handle_submit_draft(tok["draftor"], str(draft))
        assert _snapshot(loop_dir) == before
        assert not (loop_dir / "plan.current.md").exists()
        assert not (loop_dir / "plan.round-0.md").exists()

    def test_valid_section_accepted_bytes_exact(self, tmp_path, monkeypatch):
        loop_dir, tok = _make_env(tmp_path, monkeypatch)
        raw = GOOD_PLAN.replace("\n", "\r\n").encode("utf-8")
        draft = tmp_path / "plan.md"
        draft.write_bytes(raw)
        loop_submit.handle_submit_draft(tok["draftor"], str(draft))
        assert (loop_dir / "plan.current.md").read_bytes() == raw
        assert (loop_dir / "plan.round-0.md").read_bytes() == raw
        assert loop_session.load_session(loop_dir)["status"]["stage"] == "plan_review"

    def test_non_utf8_rejected(self, tmp_path, monkeypatch):
        loop_dir, tok = _make_env(tmp_path, monkeypatch)
        draft = tmp_path / "plan.md"
        draft.write_bytes(b"## Context Checked\n\n- \xff\xfe\n")
        with pytest.raises(ValueError, match="UTF-8"):
            loop_submit.handle_submit_draft(tok["draftor"], str(draft))
        assert not (loop_dir / "plan.current.md").exists()

    def test_revision_without_section_rejected(self, tmp_path, monkeypatch):
        loop_dir, tok = _make_env(tmp_path, monkeypatch)
        loop_submit.handle_submit_draft(
            tok["draftor"], str(_write(tmp_path, "plan.md", GOOD_PLAN)))
        loop_submit.handle_submit_review(
            tok["reviewer"],
            str(_write(tmp_path, "findings.md",
                       "# Findings\n\n## Verdict\n\nREVISE\n")))
        assert loop_session.load_session(loop_dir)["status"]["stage"] == "plan_revision"
        current_before = (loop_dir / "plan.current.md").read_bytes()
        with pytest.raises(ValueError, match="Context Checked"):
            loop_submit.handle_submit_draft(
                tok["draftor"], str(_write(tmp_path, "plan2.md", OLD_PLAN)))
        assert (loop_dir / "plan.current.md").read_bytes() == current_before
        assert not (loop_dir / "plan.round-1.md").exists()
        assert loop_session.load_session(loop_dir)["status"]["stage"] == "plan_revision"

    def test_in_lock_check_is_authoritative(self, tmp_path, monkeypatch):
        """Even if the preflight cannot read the session, the locked
        transaction still validates."""
        loop_dir, tok = _make_env(tmp_path, monkeypatch)
        real_load = loop_session.load_session
        calls = {"n": 0}

        def flaky(d):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("torn read")
            return real_load(d)

        monkeypatch.setattr(loop_session, "load_session", flaky)
        with pytest.raises(ValueError, match="Context Checked"):
            loop_submit.handle_submit_draft(
                tok["draftor"], str(_write(tmp_path, "plan.md", OLD_PLAN)))
        assert not (loop_dir / "plan.current.md").exists()


class TestSubmitLegacyAndCoding:
    def test_legacy_unflagged_accepts_old_plan(self, tmp_path, monkeypatch):
        loop_dir, tok = _make_env(tmp_path, monkeypatch, flagged=False)
        draft = _write(tmp_path, "plan.md", OLD_PLAN)
        loop_submit.handle_submit_draft(tok["draftor"], str(draft))
        assert (loop_dir / "plan.current.md").read_bytes() == draft.read_bytes()

    @pytest.mark.parametrize("contract", [
        None, {}, {"context_evidence": 0}, {"context_evidence": True},
        {"context_evidence": "1"}, "yes",
    ], ids=["none", "empty", "zero", "bool", "str", "nondict"])
    def test_flag_shapes_not_required(self, contract):
        session = {"contract": contract} if contract is not None else {}
        assert loop_submit._context_evidence_required(session) is False

    def test_flag_required(self):
        assert loop_submit._context_evidence_required(
            {"contract": {"context_evidence": 1}}) is True
        assert loop_submit._context_evidence_required(None) is False

    def test_coding_session_has_no_contract(self):
        s = loop_session.create_session(
            "f", "f-loop", max_rounds=3, turn_timeout=300, mode="coding",
            coding={"source_loop_id": "src", "plan_sha256": "0" * 64,
                    "base_head": "1" * 40, "base_tree": "2" * 40})
        assert "context_evidence" not in s.get("contract", {})

    def test_implementation_submission_unaffected(self):
        # The implementation artifact validator never asks for the section.
        text = "\n".join(f"## {h}\n\nx\n" for h in loop_submit.IMPLEMENTATION_HEADINGS)
        assert loop_submit.missing_implementation_headings(text) == []
        assert "context checked" not in [
            h.lower() for h in loop_submit.IMPLEMENTATION_HEADINGS]


# ---------------------------------------------------------------------------
# Race: file swapped between preflight read and the locked write
# ---------------------------------------------------------------------------

class TestSwapRace:
    def test_persisted_bytes_are_the_validated_capture(self, tmp_path, monkeypatch):
        loop_dir, tok = _make_env(tmp_path, monkeypatch)
        draft = _write(tmp_path, "plan.md", GOOD_PLAN)
        validated = draft.read_bytes()
        real_lock = loop_submit.with_session_lock

        def swapping_lock(d, fn):
            # Attacker/slow editor replaces the file after capture.
            draft.write_bytes(OLD_PLAN.encode("utf-8"))
            return real_lock(d, fn)

        monkeypatch.setattr(loop_submit, "with_session_lock", swapping_lock)
        loop_submit.handle_submit_draft(tok["draftor"], str(draft))
        assert (loop_dir / "plan.current.md").read_bytes() == validated
        assert (loop_dir / "plan.round-0.md").read_bytes() == validated

    def test_swap_to_valid_does_not_rescue_invalid_capture(self, tmp_path, monkeypatch):
        loop_dir, tok = _make_env(tmp_path, monkeypatch)
        draft = _write(tmp_path, "plan.md", OLD_PLAN)
        monkeypatch.setattr(loop_submit, "_context_evidence_required",
                            _required_only_in_lock())
        real_lock = loop_submit.with_session_lock

        def swapping_lock(d, fn):
            draft.write_bytes(GOOD_PLAN.encode("utf-8"))
            return real_lock(d, fn)

        monkeypatch.setattr(loop_submit, "with_session_lock", swapping_lock)
        with pytest.raises(ValueError, match="Context Checked"):
            loop_submit.handle_submit_draft(tok["draftor"], str(draft))
        assert not (loop_dir / "plan.current.md").exists()


def _required_only_in_lock():
    """Skip the preflight (first call) so the in-lock check is exercised."""
    real = loop_submit._context_evidence_required
    state = {"n": 0}

    def fn(session):
        state["n"] += 1
        return False if state["n"] == 1 else real(session)
    return fn


# ---------------------------------------------------------------------------
# Drift guards: shipped template and protocol
# ---------------------------------------------------------------------------

FORMATS = [
    ROOT / ".gator" / ".includes" / "reference-notes" / "loop-artifact-formats.md",
    ROOT / "src" / "gator_command" / "templates" / "gator-starter"
    / "reference-notes" / "loop-artifact-formats.md",
]
PROTOCOLS = [
    ROOT / ".gator" / ".includes" / "procedures" / "gator-loop-protocol.md",
    ROOT / "src" / "gator_command" / "templates" / "gator-starter"
    / "procedures" / "gator-loop-protocol.md",
]
LOOP_JOIN = [
    ROOT / ".claude" / "commands" / "loop-join.md",
    ROOT / "src" / "gator_command" / "templates" / "gator-starter"
    / "commands" / "loop-join.md",
]


def _plan_template(text):
    """The fenced plan template block from the formats reference."""
    start = text.index("## Plan (written by the draftor)")
    fence = text.index("```markdown", start)
    end = text.index("\n```\n", fence + 11)
    return text[fence + len("```markdown\n"):end]


class TestDriftGuards:
    @pytest.mark.parametrize("pair", [FORMATS, PROTOCOLS, LOOP_JOIN],
                             ids=["formats", "protocol", "loop-join"])
    def test_pairs_identical(self, pair):
        a, b = pair
        if not a.exists():
            pytest.skip("repo-local copy absent")
        assert a.read_bytes() == b.read_bytes()

    def test_plan_template_has_exactly_one_and_passes(self):
        tpl = _plan_template(FORMATS[1].read_text(encoding="utf-8"))
        assert loop_submit._h2_titles(tpl).count("context checked") == 1
        assert loop_submit.context_checked_problems(tpl) == []

    def test_protocol_mentions_brief_and_rules(self):
        text = PROTOCOLS[1].read_text(encoding="utf-8")
        assert "architect-brief.md" in text
        assert "## Context Checked" in text
        assert "None —" in text
        assert "source-architect-brief.md" in text

    def test_loop_join_mentions_brief(self):
        assert "brief" in LOOP_JOIN[1].read_text(encoding="utf-8").lower()
