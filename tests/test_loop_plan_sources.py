"""
#51 -- planning sources: Architect-originated plans (checkpoint 1).

Pins:
- the generic fixed-artifact verifier (closed allowlist, per-name limits,
  positional binding) and the brief-scoped wrappers;
- an Architect plan enters only as unapproved input that passed the
  ordinary draft validation, only at Reviewer ``plan_review``, with an
  Architect ``initial_plan`` turn and no Draftor turn; coding cannot start
  before Reviewer approval;
- every rejection is atomic (no loop directory, token, session or event);
- provenance integrity and legacy projection.
"""

import argparse
import contextlib
import hashlib
import io
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

import cli as loop_cli  # noqa: E402
import events as loop_events  # noqa: E402
import host as loop_host  # noqa: E402
import session as loop_session  # noqa: E402
import submit as loop_submit  # noqa: E402

GOOD_PLAN = (
    "# Plan\n\n## Executive Summary\n\n- small fix\n\n"
    "## Context Checked\n\n- scripts-loop charter\n\n"
    "## Coding Checkpoints\n\n1. **Fix** — Implement the change. "
    "Verify: the focused test.\n")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A Git repo with one commit, a .gator dir and cwd at its root."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@e.st"],
                   check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"],
                   check=True)
    (root / ".gator").mkdir()
    (root / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"],
                   check=True)
    monkeypatch.chdir(root)
    for mod in (loop_session, loop_submit, loop_host):
        if hasattr(mod, "find_gator_root"):
            monkeypatch.setattr(mod, "find_gator_root",
                                lambda start_path=None: root)
    return root


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    return path


def _start(repo, plan, **kw):
    return loop_host.init_loop("arch-fix", kw.pop("sketch_path", None),
                               repo_root=repo, plan_path=str(plan), **kw)


def _tokens(loop_dir):
    toks = loop_session.load_tokens(loop_dir)
    return {r: toks[r]["token"] for r in ("draftor", "reviewer", "architect")}


def _status(token, as_json=False):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        with pytest.raises(SystemExit) as exc:
            loop_cli._cmd_status(argparse.Namespace(token=token, json=as_json))
    text = out.getvalue()
    return exc.value.code, (json.loads(text) if as_json else text)


# ---------------------------------------------------------------------------
# 3a. Fixed-artifact verifier
# ---------------------------------------------------------------------------

NEW_NAMES = [loop_session.ARCHITECT_PLAN_FILENAME,
             loop_session.REVISION_BASELINE_PLAN,
             loop_session.REVISION_BASELINE_APPROVAL]


@pytest.mark.parametrize("name", NEW_NAMES)
def test_fixed_artifact_verifies_new_names(tmp_path, name):
    data = b"# Artifact\n\nbody\n"
    meta = loop_session.brief_meta(data, name)
    _write(tmp_path / name, data)
    assert loop_session.verify_fixed_artifact(tmp_path, meta, name) == "ok"
    assert loop_session.read_verified_fixed_artifact(tmp_path, meta, name) == \
        ("ok", data)
    assert loop_session.fixed_artifact_view(dict(meta, content="x"), name) == meta
    # Tampering is detected.
    os.chmod(tmp_path / name, 0o666)
    _write(tmp_path / name, data + b"!")
    assert loop_session.verify_fixed_artifact(tmp_path, meta, name) == "mismatch"


@pytest.mark.parametrize("name", NEW_NAMES)
def test_fixed_artifact_size_limit(tmp_path, name):
    limit = loop_session.FIXED_ARTIFACT_LIMITS[name]
    over = {"artifact": name, "sha256": "0" * 64, "bytes": limit + 1}
    assert loop_session.verify_fixed_artifact(tmp_path, over, name) == "invalid_ref"
    # An oversize file on disk never verifies and is never read in full.
    _write(tmp_path / name, b"a" * (limit + 10))
    ok_ref = {"artifact": name, "sha256": "0" * 64, "bytes": limit}
    assert loop_session.verify_fixed_artifact(tmp_path, ok_ref, name) == "mismatch"


@pytest.mark.parametrize("name", ["plan.current.md", "sketch.md", "session.json"])
def test_unknown_names_fail_closed(tmp_path, name):
    data = b"x\n"
    _write(tmp_path / name, data)
    meta = loop_session.brief_meta(data, name)
    assert loop_session.verify_fixed_artifact(tmp_path, meta, name) == "invalid_ref"
    assert loop_session.fixed_artifact_view(meta, name) is None


def test_positional_binding(tmp_path):
    data = b"x\n"
    meta = loop_session.brief_meta(data, loop_session.REVISION_BASELINE_PLAN)
    _write(tmp_path / loop_session.ARCHITECT_PLAN_FILENAME, data)
    assert loop_session.verify_fixed_artifact(
        tmp_path, meta, loop_session.ARCHITECT_PLAN_FILENAME) == "invalid_ref"


# ---------------------------------------------------------------------------
# 3b. Brief wrappers are closed to non-brief names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", NEW_NAMES)
def test_brief_wrappers_refuse_plan_names(tmp_path, name):
    data = b"x\n"
    _write(tmp_path / name, data)
    meta = loop_session.brief_meta(data, name)
    assert loop_session.verify_brief(tmp_path, meta, name) == "invalid_ref"
    assert loop_session.read_verified_brief(tmp_path, meta, name) == \
        ("invalid_ref", None)
    assert loop_session.brief_status_view(meta, name) is None


# ---------------------------------------------------------------------------
# 1. Architect-plan lifecycle
# ---------------------------------------------------------------------------

def test_architect_plan_lifecycle(repo):
    plan = _write(repo / "docs" / "plan.md", GOOD_PLAN)
    loop_id, loop_dir = _start(repo, plan)
    tok = _tokens(loop_dir)
    s = loop_session.load_session(loop_dir)

    # Reviewer owns the first turn at the existing plan_review stage.
    assert (s["status"]["stage"], s["status"]["next_role"]) == ("plan_review",
                                                                "reviewer")
    assert loop_session.planning_source(s) == "architect_plan"
    data = GOOD_PLAN.encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    assert s["plan_source"] == {"kind": "architect",
                                "artifact": "architect-plan.md",
                                "sha256": sha, "bytes": len(data)}
    for name in ("architect-plan.md", "plan.round-0.md", "plan.current.md"):
        assert (loop_dir / name).read_bytes() == data
    assert not (loop_dir / "sketch.md").exists()
    # One Architect initial_plan turn; no Draftor turn; Draftor not joined.
    assert [(t["role"], t["type"]) for t in s["turns"]] == [
        ("architect", "initial_plan")]
    assert s["roles"]["draftor"]["joined"] is False
    events = [e["event"] for e in loop_events.read_all_events(loop_dir)]
    assert events == ["loop_started", "architect_plan_submitted"]

    code, text = _status(tok["reviewer"])
    assert code == 0
    assert "Architect-originated draft plan (unapproved)" in text
    assert "awaiting Reviewer approval (not approved)" in text
    assert "No sketch:" in text
    assert _status(tok["draftor"])[0] == 1
    code, js = _status(tok["reviewer"], as_json=True)
    assert js["planning_source"] == "architect_plan"
    assert js["plan_source"]["check"] == "ok"
    assert js["plan_source"]["architect_draft_current"] is True

    # No coding loop before Reviewer approval.
    with pytest.raises(ValueError, match="not approved"):
        loop_host.init_loop("arch-fix-code", None, repo_root=repo,
                            mode="coding", from_loop=loop_id)

    # Findings hand the Architect's plan to the Draftor.
    findings = _write(repo / "f.md", "# Findings\n\n1. Tighten scope.\n")
    loop_submit.handle_submit_review(tok["reviewer"], str(findings))
    s = loop_session.load_session(loop_dir)
    assert (s["status"]["stage"], s["status"]["next_role"]) == (
        "plan_revision", "draftor")
    code, text = _status(tok["draftor"])
    assert code == 0 and f"Plan: {loop_dir / 'plan.current.md'}" in text
    assert "full replacement plan" in text

    # A Draftor revision replaces plan.current.md; provenance is unchanged.
    revised = _write(repo / "rev.md", GOOD_PLAN.replace(
        "- small fix", "- small fix, revised"))
    loop_submit.handle_submit_draft(tok["draftor"], str(revised))
    assert (loop_dir / "architect-plan.md").read_bytes() == data
    assert (loop_dir / "plan.current.md").read_bytes() != data
    code, js = _status(tok["reviewer"], as_json=True)
    assert js["plan_source"]["architect_draft_current"] is False

    # Reviewer approval -> ordinary plan_approved -> coding may start.
    approve = _write(repo / "a.md", "# Review\n\nAPPROVE\n")
    loop_submit.handle_submit_review(tok["reviewer"], str(approve), approve=True)
    s = loop_session.load_session(loop_dir)
    assert s["status"]["stage"] == "plan_approved"
    code, text = _status(tok["reviewer"])
    assert "Plan approved by the Reviewer (originated by the Architect)" in text
    code_id, code_dir = loop_host.init_loop(
        "arch-fix-code", None, repo_root=repo, mode="coding", from_loop=loop_id)
    assert (code_dir / "approved-plan.md").read_bytes() == \
        (loop_dir / "plan.current.md").read_bytes()


def test_architect_plan_with_sketch(repo):
    plan = _write(repo / "plan.md", GOOD_PLAN)
    sketch = _write(repo / "sketch.md", "# Sketch\n\nScope.\n")
    _, loop_dir = _start(repo, plan, sketch_path=str(sketch))
    assert (loop_dir / "sketch.md").read_text(encoding="utf-8") == \
        "# Sketch\n\nScope.\n"
    code, text = _status(_tokens(loop_dir)["reviewer"])
    assert "No sketch:" not in text


# ---------------------------------------------------------------------------
# 2. Atomic rejection
# ---------------------------------------------------------------------------

def _loops_snapshot(repo):
    base = repo / ".gator" / "loops"
    if not base.is_dir():
        return []
    # Loop directories only (start.lock is the shared start lock file).
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def _bad_plan(repo, case, tmp_path):
    if case == "missing":
        return repo / "nope.md"
    if case == "outside_repo":
        return _write(tmp_path / "outside.md", GOOD_PLAN)
    if case == "directory":
        d = repo / "adir"
        d.mkdir()
        return d
    if case == "empty":
        return _write(repo / "e.md", b"")
    if case == "blank":
        return _write(repo / "b.md", "   \n\n")
    if case == "non_utf8":
        return _write(repo / "n.md", b"\xff\xfe bad")
    if case == "nul":
        return _write(repo / "z.md", GOOD_PLAN.encode() + b"\x00")
    if case == "oversize":
        return _write(repo / "o.md", GOOD_PLAN + "x" * loop_session.MAX_PLAN_BYTES)
    if case == "no_context_checked":
        return _write(repo / "c.md", GOOD_PLAN.replace("## Context Checked",
                                                       "## Background"))
    if case == "bad_checkpoints":
        return _write(repo / "k.md", GOOD_PLAN.replace(
            "1. **Fix**", "2. **Fix**"))
    raise AssertionError(case)


@pytest.mark.parametrize("case", [
    "missing", "outside_repo", "directory", "empty", "blank", "non_utf8",
    "nul", "oversize", "no_context_checked", "bad_checkpoints"])
def test_bad_plan_input_is_atomic(repo, tmp_path, case):
    plan = _bad_plan(repo, case, tmp_path)
    before = _loops_snapshot(repo)
    with pytest.raises((ValueError, FileNotFoundError)):
        _start(repo, plan)
    assert _loops_snapshot(repo) == before


def test_symlinked_plan_is_refused(repo, tmp_path):
    real = _write(repo / "real.md", GOOD_PLAN)
    link = repo / "link.md"
    try:
        os.symlink(str(real), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("cannot create symlinks on this platform")
    before = _loops_snapshot(repo)
    with pytest.raises(ValueError, match="symlink|alias"):
        _start(repo, link)
    assert _loops_snapshot(repo) == before


def test_plan_behind_directory_junction_is_refused(repo):
    """A path through a junction/symlinked directory is an alias: refused."""
    real_dir = repo / "realdir"
    _write(real_dir / "plan.md", GOOD_PLAN)
    alias = repo / "aliasdir"
    if sys.platform == "win32":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias),
                            str(real_dir)], capture_output=True)
        if r.returncode != 0:
            pytest.skip("cannot create a junction")
    else:
        os.symlink(str(real_dir), str(alias))
    before = _loops_snapshot(repo)
    with pytest.raises(ValueError, match="alias|symlink"):
        _start(repo, alias / "plan.md")
    assert _loops_snapshot(repo) == before


def test_plan_file_with_coding_mode_is_refused(repo):
    plan = _write(repo / "plan.md", GOOD_PLAN)
    before = _loops_snapshot(repo)
    with pytest.raises(ValueError, match="--plan-file"):
        loop_host.init_loop("x", None, repo_root=repo, mode="coding",
                            from_loop="whatever", plan_path=str(plan))
    assert _loops_snapshot(repo) == before


def test_active_loop_blocks_start(repo, monkeypatch):
    plan = _write(repo / "plan.md", GOOD_PLAN)
    _start(repo, plan)
    before = _loops_snapshot(repo)
    monkeypatch.setattr(loop_host, "watch_loop", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="active loop"):
        loop_host.start_loop("again", None, plan_path=str(plan))
    assert _loops_snapshot(repo) == before


# ---------------------------------------------------------------------------
# 3. Integrity and legacy
# ---------------------------------------------------------------------------

def test_tampered_provenance_is_flagged(repo):
    plan = _write(repo / "plan.md", GOOD_PLAN)
    _, loop_dir = _start(repo, plan)
    target = loop_dir / "architect-plan.md"
    os.chmod(target, 0o666)
    target.write_bytes(GOOD_PLAN.encode() + b"tampered\n")
    code, text = _status(_tokens(loop_dir)["reviewer"])
    assert "[!!] DIGEST MISMATCH" in text
    assert "do not rely on it" in text


def test_planning_source_fails_closed_and_legacy_projects_as_sketch():
    s = loop_session.create_session("f", "id")
    assert loop_session.planning_source(s) == "sketch"
    ref = {"artifact": "architect-plan.md", "sha256": "0" * 64, "bytes": 1}
    both = dict(s, plan_source=dict(ref, kind="architect"),
                revision={"source_loop_id": "x"})
    with pytest.raises(ValueError):
        loop_session.planning_source(both)
    with pytest.raises(ValueError):
        loop_session.planning_source(dict(s, plan_source={"kind": "architect"}))
    with pytest.raises(ValueError):
        loop_session.create_session("f", "id", plan_source=ref, revision={})


def test_legacy_status_text_unchanged(repo):
    """An ordinary sketch loop prints no plan-source lines."""
    sketch = _write(repo / "s.md", "# Sketch\n")
    _, loop_dir = loop_host.init_loop("plain", str(sketch), repo_root=repo)
    code, text = _status(_tokens(loop_dir)["draftor"])
    assert "Plan source" not in text and "Architect-originated" not in text
    code, js = _status(_tokens(loop_dir)["draftor"], as_json=True)
    assert js["planning_source"] == "sketch" and "plan_source" not in js


# ---------------------------------------------------------------------------
# Checkpoint 2: revision planning from an approved loop
# ---------------------------------------------------------------------------

def _approved_loop(repo, kind, name="src-feature"):
    """An approved planning loop: ordinary (sketch + Draftor draft) or
    Architect-originated. Returns (loop_id, loop_dir)."""
    approve = _write(repo / f"{name}-approve.md", "# Review\n\nAPPROVE\n")
    if kind == "architect":
        plan = _write(repo / f"{name}-plan.md", GOOD_PLAN)
        loop_id, loop_dir = loop_host.init_loop(name, None, repo_root=repo,
                                                plan_path=str(plan))
    else:
        sketch = _write(repo / f"{name}-sketch.md", "# Sketch\n\nScope.\n")
        loop_id, loop_dir = loop_host.init_loop(name, str(sketch), repo_root=repo)
        draft = _write(repo / f"{name}-draft.md", GOOD_PLAN)
        loop_submit.handle_submit_draft(_tokens(loop_dir)["draftor"], str(draft))
    loop_submit.handle_submit_review(_tokens(loop_dir)["reviewer"], str(approve),
                                     approve=True)
    return loop_id, loop_dir


def _dir_bytes(d):
    return {p.name: p.read_bytes() for p in sorted(Path(d).iterdir())
            if p.is_file() and not p.name.endswith(".lock")}


def _revise(repo, source_id, sketch=None, **kw):
    if sketch is None:
        sketch = _write(repo / "rev-sketch.md", "# Revision\n\nAdd X.\n")
    return loop_host.init_loop("revised", str(sketch) if sketch else None,
                               repo_root=repo, revise_from=source_id, **kw)


@pytest.mark.parametrize("kind", ["ordinary", "architect"])
def test_revision_lifecycle(repo, kind):
    import shutil
    src_id, src_dir = _approved_loop(repo, kind)
    src_before = _dir_bytes(src_dir)
    src_session = loop_session.load_session(src_dir)
    approval_name = src_session["turns"][-1]["artifact_path"]

    loop_id, loop_dir = _revise(repo, src_id)
    s = loop_session.load_session(loop_dir)
    assert loop_session.planning_source(s) == "revision"
    assert (s["status"]["stage"], s["status"]["next_role"]) == ("plan_drafting",
                                                                "draftor")
    assert s["revision"]["source_loop_id"] == src_id
    assert s["revision"]["approval"]["source_artifact"] == approval_name
    assert (loop_dir / "revision-baseline-plan.md").read_bytes() == \
        (src_dir / "plan.current.md").read_bytes()
    assert (loop_dir / "revision-baseline-approval.md").read_bytes() == \
        (src_dir / approval_name).read_bytes()
    assert (loop_dir / "sketch.md").read_text(encoding="utf-8") == \
        "# Revision\n\nAdd X.\n"
    ev = loop_events.read_all_events(loop_dir)[0]
    assert ev["revision_source_loop_id"] == src_id
    assert ev["baseline_sha256"] == s["revision"]["baseline"]["sha256"]

    # The source loop was only read.
    assert _dir_bytes(src_dir) == src_before

    tok = _tokens(loop_dir)
    code, text = _status(tok["draftor"])
    assert code == 0
    assert f"Revision of: {src_id}" in text
    assert "Draft a full replacement plan" in text
    assert f"Baseline plan: {loop_dir / 'revision-baseline-plan.md'} [OK]" in text
    assert f"Revision sketch: {loop_dir / 'sketch.md'}" in text
    code, js = _status(tok["reviewer"], as_json=True)
    assert js["planning_source"] == "revision"
    assert js["revision"]["baseline"]["check"] == "ok"
    assert js["revision"]["approval"]["check"] == "ok"

    # The copies stay authoritative after the source is removed.
    for p in src_dir.iterdir():
        os.chmod(p, 0o666)
    shutil.rmtree(src_dir)
    code, js = _status(tok["draftor"], as_json=True)
    assert js["revision"]["baseline"]["check"] == "ok"
    assert js["revision"]["approval"]["check"] == "ok"

    # An ordinary Draftor-led cycle follows.
    draft = _write(repo / "rev-draft.md", GOOD_PLAN)
    loop_submit.handle_submit_draft(tok["draftor"], str(draft))
    assert loop_session.load_session(loop_dir)["status"]["stage"] == "plan_review"


def _tamper_session(loop_dir, fn):
    path = loop_dir / "session.json"
    loop_session._make_writable(path)
    s = loop_session.load_session(loop_dir)
    fn(s)
    path.write_text(json.dumps(s), encoding="utf-8")


def _tamper_file(path, data=b"# tampered\n"):
    os.chmod(path, 0o666)
    path.write_bytes(data)


@pytest.mark.parametrize("case", [
    "not_approved", "coding_source", "non_canonical_id", "missing_source",
    "approval_not_last", "findings_mismatch", "plan_mismatch",
    "sketch_outside_repo", "no_sketch", "with_plan_file", "coding_mode"])
def test_revision_rejection_is_atomic(repo, tmp_path, case):
    src_id, src_dir = _approved_loop(repo, "ordinary")
    kw = {}
    sketch = None
    target = src_id
    if case == "not_approved":
        _tamper_session(src_dir, lambda s: s["status"].update(stage="plan_review"))
    elif case == "coding_source":
        target, _ = loop_host.init_loop("code", None, repo_root=repo,
                                        mode="coding", from_loop=src_id)
        from submit import handle_end
        handle_end(_tokens(repo / ".gator" / "loops" / target)["architect"],
                   reason="done")
    elif case == "non_canonical_id":
        target = src_id + "."
    elif case == "missing_source":
        target = "no-such-loop-2026-01-01T00-00-00Z"
    elif case == "approval_not_last":
        _tamper_session(src_dir, lambda s: s["turns"].append(
            {"turn_id": "architect-009", "role": "architect", "type": "note",
             "summary": "x", "round": 0, "ts": "2026-01-01T00:00:00+00:00"}))
    elif case == "findings_mismatch":
        _tamper_file(src_dir / "findings.current.md")
    elif case == "plan_mismatch":
        _tamper_file(src_dir / "plan.current.md")
    elif case == "sketch_outside_repo":
        sketch = _write(tmp_path / "outside-sketch.md", "# S\n")
    elif case == "no_sketch":
        sketch = False
    elif case == "with_plan_file":
        kw["plan_path"] = str(_write(repo / "p.md", GOOD_PLAN))
    elif case == "coding_mode":
        kw["mode"] = "coding"
    reason = {
        "not_approved": "not approved", "coding_source": "coding loop",
        "non_canonical_id": "Invalid source loop id",
        "missing_source": "not found",
        "approval_not_last": "approving review cannot be identified",
        "findings_mismatch": "approving review is inconsistent",
        "plan_mismatch": "approved plan is inconsistent",
        "sketch_outside_repo": "inside the repository",
        "no_sketch": "requires --sketch", "with_plan_file": "not both",
        "coding_mode": "not valid with --mode coding",
    }[case]
    src_before = _dir_bytes(src_dir)
    before = _loops_snapshot(repo)
    with pytest.raises((ValueError, FileNotFoundError), match=reason):
        _revise(repo, target, sketch=sketch, **kw)
    assert _loops_snapshot(repo) == before
    assert _dir_bytes(src_dir) == src_before


# ---------------------------------------------------------------------------
# #51 follow-up: a source loop directory that is a junction / reparse point
# (or symlink) is refused before session.json or any artifact is opened.
# ---------------------------------------------------------------------------

def _start_from(repo, path, source_id):
    if path == "revision":
        return _revise(repo, source_id)
    return loop_host.init_loop("code", None, repo_root=repo, mode="coding",
                               from_loop=source_id)


@pytest.mark.parametrize("path", ["revision", "coding"])
def test_reparse_point_source_dir_is_refused(repo, monkeypatch, path):
    src_id, src_dir = _approved_loop(repo, "ordinary")
    real = loop_host._is_reparse_point
    monkeypatch.setattr(
        loop_host, "_is_reparse_point",
        lambda p: Path(p) == src_dir or real(p))

    def _no_source_access(*a, **k):
        raise AssertionError("source session must not be opened")
    monkeypatch.setattr(loop_session, "with_session_lock", _no_source_access)

    src_before = _dir_bytes(src_dir)
    before = _loops_snapshot(repo)
    with pytest.raises(ValueError) as exc:
        _start_from(repo, path, src_id)
    assert str(exc.value) == (
        f"Source loop must not be a symlink or reparse point: {src_id}")
    assert _loops_snapshot(repo) == before   # no loop dir, tokens, session, events
    assert _dir_bytes(src_dir) == src_before


@pytest.mark.parametrize("path", ["revision", "coding"])
def test_symlinked_source_dir_is_refused(repo, tmp_path, path):
    src_id, src_dir = _approved_loop(repo, "ordinary")
    alias = "alias-feature-2026-01-01T00-00-00Z"
    try:
        os.symlink(str(src_dir), str(src_dir.parent / alias),
                   target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("cannot create directory symlinks on this platform")
    before = _loops_snapshot(repo)
    with pytest.raises(ValueError, match="symlink or reparse point: " + alias):
        _start_from(repo, path, alias)
    assert _loops_snapshot(repo) == before
