"""
#34 / #35 / #75 — pre-commit resolution policy and the tree-bound,
retry-safe override envelope.

Integration tests drive REAL git commits in throwaway temp repos whose
pre-commit / commit-msg / post-commit hooks run the starter-template (or
Enterprise bundled) gator-pre-commit.py phases. The Architect approval step
runs gator-approve.py only inside those temp repos (never against this
repo) — the constitution forbids the agent approving real governance blocks.

#75 policy under test:
  - a missing charter update blocks as `external-approval`: the Architect
    may approve the exact staged change when no charter edit is warranted
    (the escape hatch); correctness rules are `fix-required`;
  - a HIGH/CRITICAL dangerous pattern is a `[warning]` under the default
    (strict) policy and is never approvable; while any warning has no
    recorded decision the commit PAUSES (`dangerous-pattern-pause`) until
    the draft records the Architect's acknowledgement or an explicit,
    visible skip;
  - only Enterprise `evidence_only` makes a dangerous pattern
    `[external-approval]`; the envelope lifecycle (#34, #35) is exercised
    through both the charter and the evidence_only paths;
  - a block or approval recorded by an earlier runtime for the same staged
    tree is cancelled and retried, never reinterpreted.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = (Path(__file__).resolve().parent.parent / "src" / "gator_command"
           / "templates" / "gator-starter" / "scripts")
PRE_COMMIT = SCRIPTS / "gator-pre-commit.py"
APPROVE = SCRIPTS / "gator-approve.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import precommit_override as ovr  # noqa: E402
import precommit_policy as policy  # noqa: E402
import precommit_local_policy as local_policy  # noqa: E402


# Lint-triggering SQL fixtures (rule SQL-001). Built by concatenation so
# this test SOURCE does not itself match the detector; the temp repos still
# receive the real statement.
SQL_DROP_USERS = "DROP " + "TABLE users;\n"
SQL_DROP_ORDERS = "DROP " + "TABLE orders;\n"
SQL_MATCH = "DROP " + "TABLE users"  # the source text; the rule message only names the statement type


DRAFT = """---
message: "Add foo"
change-type: {change_type}
significance: routine
decision-tags: [test]
agent: test-agent
architect: Test Architect
---

# Session Change Log

- Added foo.
"""

EV = {"GATOR_HOOK_MODE": "evidence_only"}

BUNDLED_SCRIPTS = (Path(__file__).resolve().parent.parent / "enterprise" / "enterprise-cli"
                   / "gator_enterprise_cli" / "bundled_scripts")
APPROVE_BUNDLED = BUNDLED_SCRIPTS / "gator-approve.py"


def _git(repo, *args, check=True):
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {r.stdout}\n{r.stderr}")
    return r


def _write_hook(hooks, name, body):
    p = hooks / name
    # open(..., newline=) rather than Path.write_text(newline=), which needs
    # Python 3.10+; CI still runs 3.9. LF endings matter for sh on Windows.
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/sh\n" + body + "\n")
    p.chmod(0o755)


@pytest.fixture
def repo(tmp_path):
    return _make_repo(tmp_path, SCRIPTS)


@pytest.fixture
def bundled_repo(tmp_path):
    """Same repo, but the hooks run the Enterprise bundled pre-commit copy
    (maintained separately from the template; patched at the same anchors)."""
    return _make_repo(tmp_path, BUNDLED_SCRIPTS)


@pytest.fixture(params=["template", "bundled"])
def any_repo(request, tmp_path):
    """Strict-mode behavior must match in both hook copies."""
    scripts = SCRIPTS if request.param == "template" else BUNDLED_SCRIPTS
    return _make_repo(tmp_path, scripts)


def _make_repo(tmp_path, scripts_dir, level="strict", tracked_level="strict"):
    """`level` is this clone's machine-local commit policy (Git's private
    area); `tracked_level` is what the committed config.json says, which
    the hooks no longer read."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "commit.gpgsign", "false")
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    py = Path(sys.executable).as_posix()
    pc = (scripts_dir / "gator-pre-commit.py").as_posix()
    _write_hook(hooks, "pre-commit", f'exec "{py}" "{pc}" --phase validate')
    _write_hook(hooks, "commit-msg",
                f'"{py}" "{pc}" --phase trailers "$1" || exit $?\n'
                'if [ -f "$(git rev-parse --git-dir)/fail-commit-msg" ]; then exit 1; fi')
    _write_hook(hooks, "post-commit", f'exec "{py}" "{pc}" --phase cleanup')
    _git(root, "config", "core.hooksPath", hooks.as_posix())

    gator = root / ".gator"
    gator.mkdir()
    (gator / "config.json").write_text(
        json.dumps({"enforcement_level": tracked_level}) + "\n", encoding="utf-8")
    local_policy.write_level(root, level)
    (gator / "commit_draft.md").write_text(DRAFT.format(change_type="feature"), encoding="utf-8")
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    (root / "old.py").write_text("x = 0\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-verify", "-m", "init")
    # --no-verify skips pre-commit/commit-msg but post-commit still runs and
    # resets commit_draft.md to the stub — restore a valid draft.
    (gator / "commit_draft.md").write_text(DRAFT.format(change_type="feature"), encoding="utf-8")
    return root


def _draft(repo, change_type):
    (repo / ".gator" / "commit_draft.md").write_text(
        DRAFT.format(change_type=change_type), encoding="utf-8")


def _commit(repo, env=None):
    full_env = dict(os.environ, **env) if env else None
    r = subprocess.run(["git", "commit", "-m", "fallback message"], cwd=str(repo),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=full_env)
    return r.returncode, r.stdout + r.stderr


def _approve(repo, *args, cwd=None, env=None, script=APPROVE):
    r = subprocess.run([sys.executable, str(script), *args], cwd=str(cwd or repo),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", stdin=subprocess.DEVNULL, env=env)
    return r.returncode, r.stdout + r.stderr


def _sdir(repo):
    return ovr.state_dir(repo)


def _backdate_block(repo, seconds=60):
    """Satisfy the 10 s self-approval guard without sleeping."""
    path = _sdir(repo) / ovr.BLOCK_FILE
    block = json.loads(path.read_text(encoding="utf-8"))
    block["created_epoch"] -= seconds
    path.write_text(json.dumps(block), encoding="utf-8")
    return block


def _stage_code(repo, name="foo.py", text="x = 1\n"):
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)


def _stage_sql(repo, name="migrate.sql", text=SQL_DROP_USERS):
    """A HIGH SQL-001 finding. `.sql` is code (charter rule applies);
    `.txt` is charter-exempt, so strict tests use `migrate.txt`."""
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)


def _skip_draft(repo, keys):
    """A draft that records a skip: the agent proceeds without an Architect
    decision, and the commit records the keys as unacknowledged."""
    text = DRAFT.format(change_type="feature").replace(
        "architect: Test Architect\n",
        "architect: Test Architect\n"
        f"dangerous-pattern-skips: [{', '.join(keys)}]\n")
    (repo / ".gator" / "commit_draft.md").write_text(text, encoding="utf-8")


def _last_message(repo):
    return _git(repo, "log", "-1", "--format=%B").stdout


def _state_files(repo):
    return [n for n in (ovr.BLOCK_FILE, ovr.APPROVAL_FILE, ovr.HANDOFF_FILE)
            if (_sdir(repo) / n).exists()]


def _head_json(repo, path):
    return json.loads(_git(repo, "show", f"HEAD:{path}").stdout)


# ---------------------------------------------------------------------------
# #75: a missing charter update blocks; the Architect may approve it
# ---------------------------------------------------------------------------

class TestCharterEscapeHatch:
    def test_missing_charter_blocks_and_the_architect_may_approve(self, any_repo):
        repo = any_repo
        approve = APPROVE if (repo.parent / "hooks" / "pre-commit").read_text(
            encoding="utf-8").find("bundled_scripts") < 0 else APPROVE_BUNDLED
        _stage_code(repo)
        rc, out = _commit(repo)
        assert rc != 0
        assert "charter-alongside-code [external-approval]" in out
        assert "STOP. Do not override this yourself." in out
        assert "gator hook approve" in out
        block = json.loads((_sdir(repo) / ovr.BLOCK_FILE).read_text(encoding="utf-8"))
        assert {f["rule"]: f["resolution"] for f in block["failures"]} == {
            "charter-alongside-code": "external-approval"}

        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "typo fix; no charter change",
                           "--name", "Architect", script=approve)
        assert rc == 0, out
        rc, out = _commit(repo)
        assert rc == 0, out
        assert "OVERRIDE (charter-alongside-code) approved by Architect" in out
        msg = _last_message(repo)
        assert "Gator-Charter-Changed: override-skip" in msg
        assert "Gator-Override-Rules: charter-alongside-code" in msg
        assert "Gator-Override-Reason: typo fix; no charter change" in msg
        assert _head_json(repo, ".gator/status.json")["charter_changed"] == "override-skip"
        assert _state_files(repo) == []

    def test_second_block_keeps_the_approval(self, repo):
        """#35 headline: after the Architect approves the charter finding,
        a retry blocked by a fix-required rule keeps the approval, `override
        status` diagnoses it, and the fixed retry lands with the override
        trailers and no leftover state."""
        _stage_code(repo)
        _draft(repo, "bogus")
        rc, out = _commit(repo)
        assert rc != 0
        assert "charter-alongside-code [external-approval]" in out
        assert "invalid-change-type [fix-required]" in out
        block1 = json.loads((_sdir(repo) / ovr.BLOCK_FILE).read_text(encoding="utf-8"))

        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "docs-only refactor", "--name", "Architect")
        assert rc == 0, out
        assert "Still fix-required (not approvable): invalid-change-type" in out

        rc, out = _commit(repo)
        assert rc != 0
        assert "invalid-change-type [fix-required]" in out
        assert "✗ charter-alongside-code" not in out, "approved rule must not block again"
        assert "is kept for the retry" in out
        assert "legacy-override-record" not in out, "a current approval is not legacy"
        assert (_sdir(repo) / ovr.APPROVAL_FILE).exists()
        block2 = json.loads((_sdir(repo) / ovr.BLOCK_FILE).read_text(encoding="utf-8"))
        assert block2["block_id"] == block1["block_id"]

        rc, out = _approve(repo, "status")
        assert rc == 0 and "invalid-change-type (fix-required)" in out

        _draft(repo, "fix")
        rc, out = _commit(repo)
        assert rc == 0, out
        msg = _last_message(repo)
        assert "Gator-Charter-Changed: override-skip" in msg
        assert f"Gator-Override-Block: {block1['block_id']}" in msg
        assert _state_files(repo) == []

    def test_charter_approval_with_a_dangerous_warning(self, any_repo):
        """A commit with a missing charter update AND a HIGH dangerous
        pattern: the charter rule blocks and is approved; the retry passes,
        only the charter rule is recorded as overridden, and the dangerous
        pattern stays a warning (never approved, never acknowledged)."""
        repo = any_repo
        _stage_code(repo)
        _stage_sql(repo, name="migrate.txt")
        rc, out = _commit(repo)
        assert rc != 0
        assert "charter-alongside-code [external-approval]" in out
        assert "SQL-001 [warning]" in out
        assert "dangerous-pattern-pause [pause]" in out
        block = json.loads((_sdir(repo) / ovr.BLOCK_FILE).read_text(encoding="utf-8"))
        assert {f["rule"]: f["resolution"] for f in block["failures"]} == {
            "charter-alongside-code": "external-approval", "dangerous-pattern-pause": "pause"}

        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "no charter content changes",
                           "--name", "Architect")
        assert rc == 0, out
        assert "Approving for this exact staged change: charter-alongside-code" in out
        assert "Still paused" in out and "dangerous-pattern-pause" in out

        # The approval covers only the charter rule; the pause remains until
        # the Architect's decision on the pattern is recorded.
        rc, out = _commit(repo)
        assert rc != 0 and "dangerous-pattern-pause [pause]" in out
        assert "is kept for the retry" in out
        _ack_draft(repo)
        rc, out = _commit(repo)
        assert rc == 0, out
        assert "OVERRIDE (charter-alongside-code) approved by Architect" in out

        trailers = [l for l in _last_message(repo).splitlines() if l.startswith("Gator-")]
        assert "Gator-Override-Rules: charter-alongside-code" in trailers
        assert "Gator-Charter-Changed: override-skip" in trailers
        assert f"Gator-Dangerous-Patterns: {KEY}" in trailers
        assert not any(l.startswith("Gator-Dangerous-Patterns-Unacknowledged") for l in trailers)
        checks = _head_json(repo, ".gator/status.json")["commit_checks"]
        assert checks["overridden_rules"] == ["charter-alongside-code"]
        assert checks["dangerous_pattern_warnings"] == [KEY]
        assert checks["dangerous_pattern_acknowledged"] == [KEY]
        assert checks["dangerous_pattern_pause"] == []
        assert _state_files(repo) == []

    def test_correctness_rules_stay_fix_required(self, repo):
        (repo / "notes.md").write_text("docs\n", encoding="utf-8")
        _git(repo, "add", "notes.md")
        _draft(repo, "bogus")
        rc, out = _commit(repo)
        assert rc != 0
        assert "invalid-change-type [fix-required]" in out
        assert "STOP. Do not override this yourself." not in out


# ---------------------------------------------------------------------------
# #75: dangerous patterns warn under the default policy
# ---------------------------------------------------------------------------

class TestDangerousPatternPause:
    def test_unrecorded_finding_pauses_without_an_approval_path(self, any_repo):
        repo = any_repo
        _stage_sql(repo, name="migrate.txt")
        rc, out = _commit(repo)
        assert rc != 0, out
        assert "SQL-001 [warning]" in out
        assert "dangerous-pattern-pause [pause]" in out
        assert "PAUSE. Architect attention required." in out
        assert "STOP. Do not override this yourself." not in out
        assert "gator hook approve" not in out
        block = json.loads((_sdir(repo) / ovr.BLOCK_FILE).read_text(encoding="utf-8"))
        assert {f["rule"]: f["resolution"] for f in block["failures"]} == {
            "dangerous-pattern-pause": "pause"}
        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "r", "--name", "A")
        assert rc == 1 and "never by this command" in out
        assert not (_sdir(repo) / ovr.APPROVAL_FILE).exists()

        checks = json.loads((repo / ".gator" / "status.json").read_text(
            encoding="utf-8"))["commit_checks"]
        assert checks["dangerous_pattern_pause"] == ["SQL-001@migrate.txt:1"]
        assert checks["integrity_failures"] == [] and checks["external_approval_required"] == []
        wb = (repo / ".gator" / "whiteboard.md").read_text(encoding="utf-8")
        assert "## Paused — Architect decision required" in wb
        assert SQL_MATCH not in wb

    def test_recorded_skip_passes_and_is_visible_in_git(self, any_repo):
        repo = any_repo
        _stage_sql(repo, name="migrate.txt")
        _skip_draft(repo, ["SQL-001@migrate.txt:1"])
        rc, out = _commit(repo)
        assert rc == 0, out
        assert "Committed without an Architect decision" in out
        assert _state_files(repo) == []
        trailers = [l for l in _last_message(repo).splitlines() if l.startswith("Gator-")]
        assert "Gator-Dangerous-Patterns-Unacknowledged: SQL-001@migrate.txt:1" in trailers
        assert not any(l.startswith("Gator-Dangerous-Patterns:") for l in trailers)
        assert not any(l.startswith("Gator-Override") for l in trailers)
        assert not any(SQL_MATCH in l for l in trailers)

        status = _head_json(repo, ".gator/status.json")
        checks = status["commit_checks"]
        assert checks["dangerous_pattern_skipped"] == ["SQL-001@migrate.txt:1"]
        assert checks["dangerous_pattern_acknowledged"] == []
        assert checks["dangerous_pattern_pause"] == []
        wb = _git(repo, "show", "HEAD:.gator/whiteboard.md").stdout
        assert "## Unacknowledged dangerous patterns (recorded skip)" in wb
        assert SQL_MATCH not in wb and SQL_MATCH not in json.dumps(status)

    @pytest.mark.parametrize("how", ["acknowledge", "skip"])
    def test_comma_filename_can_clear_the_pause(self, repo, how):
        """Codex finding 1: a path the flat list cannot hold is
        percent-encoded in its key, so the pause can always be cleared."""
        key = "SQL-001@migrate%2Cfixture.txt:1"
        _stage_sql(repo, name="migrate,fixture.txt")
        rc, out = _commit(repo)
        assert rc != 0 and key in out, out
        if how == "acknowledge":
            _ack_draft(repo, keys=(key,))
            trailer = f"Gator-Dangerous-Patterns: {key}"
        else:
            _skip_draft(repo, [key])
            trailer = f"Gator-Dangerous-Patterns-Unacknowledged: {key}"
        rc, out = _commit(repo)
        assert rc == 0, out
        assert trailer in _last_message(repo).splitlines()

    @pytest.mark.parametrize("evidence", [True, False])
    def test_commit_msg_fails_closed_when_evidence_cannot_be_revalidated(
            self, repo, monkeypatch, tmp_path, evidence):
        """Codex finding 2: required skip/acknowledgement evidence that the
        commit-msg phase cannot revalidate aborts the commit instead of
        landing it without its trailers. With no evidence, the same error
        leaves the commit alone."""
        import importlib.util
        _stage_sql(repo, name="migrate.txt")
        if evidence:
            _skip_draft(repo, ["SQL-001@migrate.txt:1"])
        spec = importlib.util.spec_from_file_location("gpc_failclosed", PRE_COMMIT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def broken_lint(*_a, **_k):
            raise OSError("simulated lint read failure")

        monkeypatch.setattr(mod, "run_layer1_lint", broken_lint)
        monkeypatch.chdir(repo)
        msg = tmp_path / "COMMIT_EDITMSG"
        msg.write_text("fallback\n", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            mod.phase_trailers(str(msg))
        assert exc.value.code == (1 if evidence else 0)

    @pytest.mark.parametrize("case", ["stale", "acknowledged-and-skipped"])
    def test_invalid_skip_fails_closed(self, repo, case):
        _stage_sql(repo, name="migrate.txt")
        if case == "stale":
            _skip_draft(repo, ["SQL-001@migrate.txt:9"])
        else:
            _ack_draft(repo)
            draft = repo / ".gator" / "commit_draft.md"
            draft.write_text(draft.read_text(encoding="utf-8").replace(
                "architect: Test Architect\n",
                f"architect: Test Architect\ndangerous-pattern-skips: [{KEY}]\n"),
                encoding="utf-8")
        rc, out = _commit(repo)
        assert rc != 0
        assert "invalid-dangerous-pattern-acknowledgement [fix-required]" in out
        assert "Gator-Dangerous" not in _last_message(repo)

    def test_charter_failure_and_pause_together(self, repo):
        _stage_code(repo)
        _stage_sql(repo, name="migrate.txt")
        rc, out = _commit(repo)
        assert rc != 0
        assert "charter-alongside-code [external-approval]" in out
        assert "dangerous-pattern-pause [pause]" in out
        assert "STOP. Do not override this yourself." in out, "the charter rule is approvable"
        assert "PAUSE. Architect attention required." in out


# ---------------------------------------------------------------------------
# #75: Architect acknowledgement evidence
# ---------------------------------------------------------------------------

KEY = "SQL-001@migrate.txt:1"
# SQL-004 (MEDIUM) on line 2, built by concatenation like the SQL fixtures.
SQL_MEDIUM_LINE = "cursor." + "execute(\"x\" + y)\n"


def _ack_draft(repo, keys=(KEY,), bullets=None, architect="architect: Test Architect",
               section=True):
    if bullets is None:
        bullets = [f"- `{k}`: Keep this migration fixture; the Architect confirmed it."
                   for k in keys]
    text = (
        "---\n"
        'message: "Keep the migration fixture"\n'
        "change-type: feature\n"
        "significance: routine\n"
        "decision-tags: [test]\n"
        "agent: test-agent\n"
        f"{architect}\n"
        f"dangerous-pattern-acknowledgements: [{', '.join(keys)}]\n"
        "---\n\n"
        "# Session Change Log\n\n"
        "- Added a migration fixture.\n"
    )
    if section:
        text += "\n## Architect acknowledgement\n\n" + "\n".join(bullets) + "\n"
    (repo / ".gator" / "commit_draft.md").write_text(text, encoding="utf-8")


class TestAcknowledgement:
    def test_valid_acknowledgement_emits_trailers_without_source_text(self, any_repo):
        repo = any_repo
        _stage_sql(repo, name="migrate.txt")
        _ack_draft(repo)
        rc, out = _commit(repo)
        assert rc == 0, out
        assert "Kept on the Architect's direction (Test Architect): " + KEY in out
        assert "ARCHITECT ATTENTION REQUIRED" not in out
        msg = _last_message(repo)
        trailers = [l for l in msg.splitlines() if l.startswith("Gator-")]
        assert f"Gator-Dangerous-Patterns: {KEY}" in trailers
        assert "Gator-Dangerous-Pattern-Acknowledged-By: Test Architect" in trailers
        assert not any(SQL_MATCH in l for l in trailers)
        assert not any(l.startswith("Gator-Override") for l in trailers)
        assert "## Architect acknowledgement" in msg
        checks = _head_json(repo, ".gator/status.json")["commit_checks"]
        assert checks["dangerous_pattern_acknowledged"] == [KEY]
        assert checks["acknowledged_by"] == "Test Architect"
        wb = _git(repo, "show", "HEAD:.gator/whiteboard.md").stdout
        assert "## Architect acknowledgements" in wb
        assert "## Dangerous-pattern warnings" not in wb
        assert _state_files(repo) == []

    def test_key_with_spaces_in_path_is_kept_byte_for_byte(self, repo):
        """A staged path may contain repeated spaces: the trailer key must
        name exactly that file."""
        key = "SQL-001@two  spaces.txt:1"
        _stage_sql(repo, name="two  spaces.txt")
        _ack_draft(repo, keys=(key,))
        rc, out = _commit(repo)
        assert rc == 0, out
        trailers = [l for l in _last_message(repo).splitlines() if l.startswith("Gator-")]
        assert f"Gator-Dangerous-Patterns: {key}" in trailers
        checks = _head_json(repo, ".gator/status.json")["commit_checks"]
        assert checks["dangerous_pattern_acknowledged"] == [key]

    def test_acknowledgement_trailers_only_neutralize_line_breaks(self):
        lines = policy.acknowledgement_trailers(
            ["SQL-001@a  b.txt:1", "HYG-002@x\ny.env:0"], "Alan\nGator-Evil: 1")
        assert lines[0] == "Gator-Dangerous-Patterns: SQL-001@a  b.txt:1,HYG-002@x y.env:0"
        assert lines[1] == "Gator-Dangerous-Pattern-Acknowledged-By: Alan Gator-Evil: 1"
        assert len(lines) == 2

    @pytest.mark.parametrize("case", [
        "stale-line", "fabricated", "duplicate", "medium-key", "missing-architect",
        "pi-only", "missing-section", "unlisted-bullet", "section-without-field",
        "empty-bullet",
    ])
    def test_malformed_evidence_fails_closed(self, repo, case):
        _stage_sql(repo, name="migrate.txt", text=SQL_DROP_USERS + SQL_MEDIUM_LINE)
        kwargs = {
            "stale-line": dict(keys=("SQL-001@migrate.txt:7",)),
            "fabricated": dict(keys=("SEC-001@other.py:3",)),
            "duplicate": dict(keys=(KEY, KEY), bullets=[f"- `{KEY}`: keep"]),
            "medium-key": dict(keys=("SQL-004@migrate.txt:2",)),
            "missing-architect": dict(architect="architect:"),
            "pi-only": dict(architect="pi: Test Architect"),
            "missing-section": dict(section=False),
            "unlisted-bullet": dict(bullets=[f"- `{KEY}`: keep", "- `SQL-002@x.sql:1`: also"]),
            "section-without-field": dict(keys=(), bullets=[f"- `{KEY}`: keep"]),
            "empty-bullet": dict(bullets=[f"- `{KEY}`:"]),
        }[case]
        _ack_draft(repo, **kwargs)
        rc, out = _commit(repo)
        assert rc != 0, out
        assert "invalid-dangerous-pattern-acknowledgement [fix-required]" in out
        assert "Current dangerous-pattern warning keys: " + KEY in out
        assert SQL_MATCH not in out.split("invalid-dangerous-pattern-acknowledgement", 1)[1] \
            .split("\n", 1)[0], "the failure message never carries source text"

    def test_only_the_charter_failure_remains_with_valid_evidence(self, repo):
        _stage_code(repo)
        _stage_sql(repo, name="migrate.txt")
        _ack_draft(repo)
        rc, out = _commit(repo)
        assert rc != 0
        block = json.loads((_sdir(repo) / ovr.BLOCK_FILE).read_text(encoding="utf-8"))
        assert [f["rule"] for f in block["failures"]] == ["charter-alongside-code"]
        assert "invalid-dangerous-pattern-acknowledgement" not in out

    def test_acknowledgement_never_touches_the_envelope(self, bundled_repo):
        """In evidence_only the finding is external-approval: listing it as
        acknowledged neither clears the block nor yields acknowledgement
        trailers, and the approval lifecycle is unchanged."""
        repo = bundled_repo
        _stage_sql(repo)
        _ack_draft(repo, keys=("SQL-001@migrate.sql:1",))
        rc, out = _commit(repo, env=EV)
        assert rc != 0 and "SQL-001 [external-approval]" in out
        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "ok", "--name", "Architect",
                           script=APPROVE_BUNDLED)
        assert rc == 0, out
        rc, out = _commit(repo, env=EV)
        assert rc == 0, out
        msg = _last_message(repo)
        assert "Gator-Override-Rules: SQL-001" in msg
        assert "Gator-Dangerous" not in msg
        assert _state_files(repo) == []

    def test_warn_mode_never_records_invalid_evidence(self, tmp_path):
        repo = _make_repo(tmp_path, SCRIPTS, level="warn")
        _stage_sql(repo, name="migrate.txt")
        _ack_draft(repo, keys=("SQL-001@migrate.txt:9",))
        rc, out = _commit(repo)
        assert rc == 0, out
        assert "invalid-dangerous-pattern-acknowledgement" in out
        assert "Gator-Dangerous" not in _last_message(repo)


def test_machine_local_warn_passes_and_is_recorded(tmp_path):
    """This clone's local `warn` passes a missing charter update and a HIGH
    finding, and the commit says so in `Gator-Commit-Policy: warn`. The
    file lives in Git's private area: nothing in the repository changes.
    Back to strict, the next commit carries no policy trailer."""
    repo = _make_repo(tmp_path, SCRIPTS, level="warn")
    assert local_policy.policy_path(repo).is_file()
    assert local_policy.POLICY_FILENAME not in _git(
        repo, "status", "--porcelain", "--ignored").stdout
    _stage_code(repo)
    _stage_sql(repo, name="migrate.txt")
    rc, out = _commit(repo)
    assert rc == 0, out
    assert "PASS (commit policy: warn on this machine" in out
    assert "charter-alongside-code" in out and "SQL-001" in out
    assert "Gator-Commit-Policy: warn" in _last_message(repo)
    assert _state_files(repo) == []

    local_policy.write_level(repo, "strict")
    assert not local_policy.policy_path(repo).exists()
    (repo / "notes.txt").write_text("plain\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    _draft(repo, "docs")
    rc, out = _commit(repo)
    assert rc == 0, out
    assert "Gator-Commit-Policy" not in _last_message(repo)


@pytest.mark.parametrize("tracked", ["warn", "off"])
def test_tracked_config_cannot_relax_checks(any_repo_factory, tracked):
    """A relaxation committed in config.json reaches every engineer through
    Git, so neither hook copy reads it: a missing charter update still
    blocks. The template hook says the value is ignored."""
    repo, kind = any_repo_factory(tracked_level=tracked)
    _stage_code(repo)
    rc, out = _commit(repo)
    assert rc != 0, out
    assert "charter-alongside-code" in out
    if kind == "template":
        assert "tracked-commit-policy-ignored" in out and "is ignored" in out
    assert "Gator-Commit-Policy" not in _git(repo, "log", "-1", "--format=%B").stdout


@pytest.fixture(params=["template", "bundled"])
def any_repo_factory(request, tmp_path):
    scripts = SCRIPTS if request.param == "template" else BUNDLED_SCRIPTS
    return lambda **kw: (_make_repo(tmp_path, scripts, **kw), request.param)


# ---------------------------------------------------------------------------
# #75 migration: in-flight records from an earlier runtime
# ---------------------------------------------------------------------------

def _write_legacy_block(repo, failures, tree=None, expires_in=3600):
    sdir = _sdir(repo)
    sdir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    block = {
        "schema": ovr.SCHEMA, "block_id": "legacy01",
        "created_epoch": now - 120, "created_at": "x", "updated_at": "x",
        "expires_epoch": now + expires_in, "expires_at": "x",
        "index_tree": tree or ovr.index_tree(repo),
        "failures": [{"rule": r, "resolution": res, "message": "m"} for r, res in failures],
        "files": [],
    }
    (sdir / ovr.BLOCK_FILE).write_text(json.dumps(block), encoding="utf-8")
    return block


def _write_approval(repo, block, rules):
    approval = {
        "schema": ovr.SCHEMA, "approval_id": "legacyap", "block_id": block["block_id"],
        "index_tree": block["index_tree"], "approved_rules": rules,
        "approved_by": "Architect", "reason": "earlier runtime",
        "approved_epoch": block["created_epoch"] + 60, "approved_at": "x",
        "expires_epoch": block["expires_epoch"], "expires_at": "x",
    }
    (_sdir(repo) / ovr.APPROVAL_FILE).write_text(json.dumps(approval), encoding="utf-8")
    return approval


def _write_handoff(repo, approval):
    handoff = {
        "schema": ovr.SCHEMA, "block_id": approval["block_id"],
        "approval_id": approval["approval_id"], "index_tree": approval["index_tree"],
        "overridden_rules": approval["approved_rules"], "charter_override": False,
        "approved_by": "Architect", "reason": "earlier runtime", "written_at": "x",
    }
    (_sdir(repo) / ovr.HANDOFF_FILE).write_text(json.dumps(handoff), encoding="utf-8")


class TestLegacyMigration:
    @pytest.mark.parametrize("case", ["lint", "lint-approved", "charter-approved"])
    def test_guard_persists_until_cancel(self, repo, case):
        if case == "charter-approved":
            _stage_code(repo)
            block = _write_legacy_block(repo, [("charter-alongside-code", "approvable")])
            _write_approval(repo, block, ["charter-alongside-code"])
        else:
            _stage_sql(repo, name="migrate.txt")
            block = _write_legacy_block(repo, [("SQL-001", "lint")])
            if case == "lint-approved":
                _write_handoff(repo, _write_approval(repo, block, ["SQL-001"]))
            else:
                rc, out = _approve(repo, "approve", "--reason", "r", "--name", "A")
                assert rc == 1 and "earlier Gator runtime" in out
                assert "gator hook override cancel" in out

        for attempt in (1, 2):
            rc, out = _commit(repo)
            assert rc != 0, f"attempt {attempt} must block:\n{out}"
            assert "legacy-override-record [fix-required]" in out
            assert "OVERRIDE" not in out
            assert not (_sdir(repo) / ovr.HANDOFF_FILE).exists()
            if case != "lint":
                assert (_sdir(repo) / ovr.APPROVAL_FILE).exists(), "legacy approval kept"

        rc, out = _approve(repo, "cancel")
        assert rc == 0
        rc, out = _commit(repo)
        assert "legacy-override-record" not in out
        if case == "charter-approved":
            assert rc != 0 and "charter-alongside-code [external-approval]" in out
        else:
            # The current policy: the pattern pauses for a recorded decision.
            assert rc != 0 and "dangerous-pattern-pause [pause]" in out
            assert "SQL-001 [warning]" in out
            _skip_draft(repo, ["SQL-001@migrate.txt:1"])
            rc, out = _commit(repo)
            assert rc == 0, out
            assert "Gator-Override" not in _last_message(repo)

    @pytest.mark.parametrize("which", ["expired", "other-tree"])
    def test_stale_legacy_records_do_not_block(self, repo, which):
        _stage_sql(repo, name="migrate.txt")
        if which == "expired":
            _write_legacy_block(repo, [("SQL-001", "lint")], expires_in=-10)
        else:
            _write_legacy_block(repo, [("SQL-001", "lint")], tree="another-tree")
        _skip_draft(repo, ["SQL-001@migrate.txt:1"])
        rc, out = _commit(repo)
        assert rc == 0, out
        assert "legacy-override-record" not in out
        assert _state_files(repo) == [], "retired by post-commit cleanup"


# ---------------------------------------------------------------------------
# Enterprise evidence_only: the external-approval envelope (#34, #35)
# ---------------------------------------------------------------------------

def _ev_block_and_approve(repo):
    _stage_sql(repo)
    rc, _ = _commit(repo, env=EV)
    assert rc != 0
    _backdate_block(repo)
    rc, out = _approve(repo, "approve", "--reason", "ok", "--name", "Architect",
                       script=APPROVE_BUNDLED)
    assert rc == 0, out


class TestEnterpriseEvidenceOnly:
    """Enterprise `evidence_only` (GATOR_HOOK_MODE) lint goes through the
    tree-bound envelope — block recorded, Architect approval of the exact
    change, retry, consumed post-commit."""

    def test_block_approve_retry(self, bundled_repo):
        repo = bundled_repo
        _stage_sql(repo)
        rc, out = _commit(repo, env=EV)
        assert rc != 0
        assert "BLOCKED (evidence_only" in out
        assert "SQL-001 [external-approval]" in out
        assert "gator hook approve" in out
        assert "charter-alongside-code" not in out, "evidence_only skips charter rules"
        block = json.loads((_sdir(repo) / ovr.BLOCK_FILE).read_text(encoding="utf-8"))
        assert block["failures"][0]["resolution"] == "external-approval"

        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "intentional migration",
                           "--name", "Architect", script=APPROVE_BUNDLED)
        assert rc == 0, out

        rc, out = _commit(repo, env=EV)
        assert rc == 0, out
        assert "OVERRIDE (SQL-001) approved by Architect (evidence_only)" in out
        msg = _last_message(repo)
        assert "Gator-Override-Rules: SQL-001" in msg
        assert "Gator-Override-Approved-By: Architect" in msg
        assert "Gator-Override-Reason: intentional migration" in msg
        assert "Gator-Charter-Changed: override-skip" not in msg
        assert _state_files(repo) == []

        # Trailer readers surface the override from real history. Run in a
        # clean interpreter: this module puts the starter-template scripts
        # dir first on sys.path, whose gator_core.py is a different file
        # from the package copy repo-status imports in production.
        pkg_scripts = SCRIPTS.parent.parent.parent / "scripts"
        probe = (
            "import sys, json, importlib.util; sys.path.insert(0, sys.argv[1]);"
            "spec = importlib.util.spec_from_file_location('rs', sys.argv[1] + '/gator-repo-status.py');"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
            "_, recent, events = m.get_trailer_data(sys.argv[2]);"
            "print(json.dumps({'override': recent[0]['override'], 'events': events}))"
        )
        r = subprocess.run([sys.executable, "-c", probe, str(pkg_scripts), str(repo)],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout.strip().splitlines()[-1])
        assert data["override"] is True
        ev = data["events"][0]
        assert ev["approver"] == "Architect"
        assert ev["rules"] == ["SQL-001"]
        assert ev["block_id"] == block["block_id"]

    def test_reporting_separates_categories(self, bundled_repo):
        repo = bundled_repo
        _stage_sql(repo)
        rc, out = _commit(repo, env=EV)
        assert rc != 0
        status = json.loads((repo / ".gator" / "status.json").read_text(encoding="utf-8"))
        checks = status["commit_checks"]
        assert checks["external_approval_required"] == ["SQL-001"]
        assert checks["integrity_failures"] == []
        assert checks["dangerous_pattern_acknowledged"] == []
        wb = (repo / ".gator" / "whiteboard.md").read_text(encoding="utf-8")
        assert "## External approval required" in wb
        assert "## Blocked — fix required" not in wb
        assert _git(repo, "ls-files", ".gator/whiteboard.md").stdout.strip() == "", \
            "an untracked whiteboard is not staged in evidence_only"

        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "ok", "--name", "Architect",
                           script=APPROVE_BUNDLED)
        assert rc == 0, out
        rc, out = _commit(repo, env=EV)
        assert rc == 0, out
        checks = _head_json(repo, ".gator/status.json")["commit_checks"]
        assert checks["overridden_rules"] == ["SQL-001"]
        assert checks["external_approval_required"] == []
        assert checks["dangerous_pattern_acknowledged"] == []
        assert "## Overrides" in (repo / ".gator" / "whiteboard.md").read_text(encoding="utf-8")
        assert "Gator-Dangerous" not in _last_message(repo)
        assert ".gator/whiteboard.md" not in _git(
            repo, "show", "--name-only", "--format=", "HEAD").stdout

    def test_unmerged_index_is_fix_required_not_approvable(self, bundled_repo):
        repo = bundled_repo
        _git(repo, "config", "core.hooksPath", (repo / ".no-hooks").as_posix())
        _git(repo, "checkout", "-q", "-b", "other")
        (repo / "old.py").write_text("x = 'other'\n", encoding="utf-8")
        _git(repo, "commit", "-q", "--no-verify", "-am", "other")
        _git(repo, "checkout", "-q", "main")
        (repo / "old.py").write_text("x = 'main'\n", encoding="utf-8")
        _git(repo, "commit", "-q", "--no-verify", "-am", "main")
        _git(repo, "merge", "other", check=False)
        _stage_sql(repo)
        r = subprocess.run(
            [sys.executable, str(BUNDLED_SCRIPTS / "gator-pre-commit.py"), "--phase", "validate"],
            cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=dict(os.environ, **EV))
        out = r.stdout + r.stderr
        assert r.returncode == 1, out
        assert "unmerged-index [fix-required]" in out
        checks = json.loads(
            (repo / ".gator" / "status.json").read_text(encoding="utf-8"))["commit_checks"]
        assert "unmerged-index" in checks["integrity_failures"]
        assert "unmerged-index" not in checks["external_approval_required"]
        wb = (repo / ".gator" / "whiteboard.md").read_text(encoding="utf-8")
        fix_section = wb.split("## Blocked — fix required", 1)[1].split("##", 1)[0]
        assert "unmerged-index" in fix_section

    def test_lint_allow_is_explained_not_honored(self, bundled_repo):
        repo = bundled_repo
        (repo / ".gator" / "lint-allow.json").write_text(
            json.dumps([{"rule": "SQL-001", "file": "migrate.sql"}]), encoding="utf-8")
        _stage_sql(repo)
        rc, out = _commit(repo, env=EV)
        assert rc != 0
        assert "no longer authorizes lint findings" in out
        assert "SQL-001 in migrate.sql" in out

    def test_clean_evidence_only_commit_passes(self, bundled_repo):
        repo = bundled_repo
        (repo / "notes.sql").write_text("SELECT 1;\n", encoding="utf-8")
        _git(repo, "add", "notes.sql")
        rc, out = _commit(repo, env=EV)
        assert rc == 0, out


class TestSupersede:
    @pytest.mark.parametrize("change", ["modify", "add", "delete", "rename"])
    def test_staged_change_invalidates_approval(self, bundled_repo, change):
        repo = bundled_repo
        _ev_block_and_approve(repo)
        if change == "modify":
            _stage_sql(repo, text=SQL_DROP_USERS + SQL_DROP_ORDERS)
        elif change == "add":
            _stage_code(repo, name="bar.py", text="y = 1\n")
        elif change == "delete":
            _git(repo, "rm", "-q", "old.py")
        elif change == "rename":
            _git(repo, "mv", "old.py", "old2.py")
        rc, out = _commit(repo, env=EV)
        assert rc != 0
        assert "Previous approval retired" in out and "different staged tree" in out
        assert not (_sdir(repo) / ovr.APPROVAL_FILE).exists()
        assert "SQL-001 [external-approval]" in out

    def test_expired_approval_is_retired(self, bundled_repo):
        repo = bundled_repo
        _ev_block_and_approve(repo)
        path = _sdir(repo) / ovr.APPROVAL_FILE
        approval = json.loads(path.read_text(encoding="utf-8"))
        approval["expires_epoch"] = 1
        path.write_text(json.dumps(approval), encoding="utf-8")
        rc, out = _commit(repo, env=EV)
        assert rc != 0 and "expired" in out
        assert not path.exists()

    @pytest.mark.parametrize("corrupt", ["block_missing_fields", "approval_missing_id",
                                         "approval_bad_epochs"])
    def test_schema_valid_partial_state_fails_closed_without_traceback(self, bundled_repo,
                                                                         corrupt):
        """Valid JSON with the right schema but missing or mistyped fields
        must never crash the hook."""
        repo = bundled_repo
        _ev_block_and_approve(repo)
        sdir = _sdir(repo)
        if corrupt == "block_missing_fields":
            block = json.loads((sdir / ovr.BLOCK_FILE).read_text(encoding="utf-8"))
            del block["block_id"], block["created_epoch"]
            (sdir / ovr.BLOCK_FILE).write_text(json.dumps(block), encoding="utf-8")
        else:
            approval = json.loads((sdir / ovr.APPROVAL_FILE).read_text(encoding="utf-8"))
            if corrupt == "approval_missing_id":
                del approval["approval_id"]
            else:
                approval["approved_epoch"] = "later"
                approval["expires_epoch"] = "never"
            (sdir / ovr.APPROVAL_FILE).write_text(json.dumps(approval), encoding="utf-8")

        rc, out = _commit(repo, env=EV)
        assert "Traceback" not in out, out
        if corrupt == "block_missing_fields":
            # The approval is intact and valid for this tree: commit passes.
            assert rc == 0, out
        else:
            assert rc != 0
            assert "Previous approval retired" in out
            assert "SQL-001 [external-approval]" in out
            assert not (sdir / ovr.APPROVAL_FILE).exists()
        for args in (("status",), ("approve", "--reason", "r", "--name", "A")):
            rc2, out2 = _approve(repo, *args, script=APPROVE_BUNDLED)
            assert "Traceback" not in out2, out2

    def test_malformed_approval_fails_closed(self, bundled_repo):
        repo = bundled_repo
        _ev_block_and_approve(repo)
        (_sdir(repo) / ovr.APPROVAL_FILE).write_text("{not json", encoding="utf-8")
        rc, out = _commit(repo, env=EV)
        assert rc != 0 and "SQL-001 [external-approval]" in out
        assert not (_sdir(repo) / ovr.APPROVAL_FILE).exists()

    def test_approval_for_other_rule_keeps_it_and_reports_new_rule(self, bundled_repo):
        """An approval snapshot that does not name this attempt's rule is
        kept, and the rule still needs approval."""
        repo = bundled_repo
        _stage_sql(repo)
        _commit(repo, env=EV)
        block = _backdate_block(repo)
        block["failures"] = [{"rule": "SQL-003", "resolution": "external-approval",
                              "message": "m"}]
        ovr.write_approval(_sdir(repo), block, "Architect", "earlier rule")
        rc, out = _commit(repo, env=EV)
        assert rc != 0
        assert "SQL-001 [external-approval]" in out
        assert (_sdir(repo) / ovr.APPROVAL_FILE).exists()

    def test_cancel_retires_block_and_approval(self, bundled_repo):
        repo = bundled_repo
        _ev_block_and_approve(repo)
        rc, out = _approve(repo, "cancel", script=APPROVE_BUNDLED)
        assert rc == 0 and "Cancelled" in out
        assert _state_files(repo) == []
        rc, out = _approve(repo, "status", script=APPROVE_BUNDLED)
        assert "No blocked commit attempt" in out


class TestRetrySafety:
    def test_commit_msg_failure_keeps_approval_for_retry(self, bundled_repo):
        repo = bundled_repo
        _ev_block_and_approve(repo)
        marker = Path(_git(repo, "rev-parse", "--git-dir").stdout.strip())
        marker = marker if marker.is_absolute() else repo / marker
        (marker / "fail-commit-msg").write_text("1", encoding="utf-8")
        rc, out = _commit(repo, env=EV)
        assert rc != 0
        assert (_sdir(repo) / ovr.APPROVAL_FILE).exists(), out
        assert (_sdir(repo) / ovr.HANDOFF_FILE).exists(), out

        (marker / "fail-commit-msg").unlink()
        rc, out = _commit(repo, env=EV)
        assert rc == 0, out
        assert "Gator-Override-Approved-By: Architect" in _last_message(repo)
        assert not (_sdir(repo) / ovr.APPROVAL_FILE).exists()

    def test_trailer_values_cannot_inject(self, bundled_repo):
        repo = bundled_repo
        _stage_sql(repo)
        _commit(repo, env=EV)
        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason",
                           "ok\nGator-Architect: mallory\r\nGator-Fake: 1",
                           "--name", "Arch\nGator-Evil: x", script=APPROVE_BUNDLED)
        assert rc == 0, out
        rc, out = _commit(repo, env=EV)
        assert rc == 0, out
        lines = _last_message(repo).splitlines()
        assert not any(l.startswith("Gator-Architect: mallory") for l in lines)
        assert not any(l.startswith("Gator-Fake") or l.startswith("Gator-Evil") for l in lines)
        reason = [l for l in lines if l.startswith("Gator-Override-Reason:")]
        assert reason == ["Gator-Override-Reason: ok Gator-Architect: mallory Gator-Fake: 1"]


class TestDiagnosis:
    def test_block_with_nothing_approvable_is_recorded_and_explained(self, repo):
        (repo / "notes.md").write_text("docs\n", encoding="utf-8")
        _git(repo, "add", "notes.md")
        _draft(repo, "bogus")
        rc, out = _commit(repo)
        assert rc != 0
        assert "invalid-change-type [fix-required]" in out
        assert "STOP. Do not override this yourself." not in out, "nothing approvable"
        assert (_sdir(repo) / ovr.BLOCK_FILE).exists()

        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "r", "--name", "A")
        assert rc == 1
        assert "nothing in this block can be approved" in out
        assert "invalid-change-type" in out
        assert "No pending override request" not in out

    def test_no_block_recorded_gives_guidance(self, repo):
        rc, out = _approve(repo, "approve", "--reason", "r", "--name", "A")
        assert rc == 1
        assert "No blocked commit attempt is recorded" in out
        assert "Retry `git commit`" in out

    def test_approve_refuses_premature_approval(self, bundled_repo):
        repo = bundled_repo
        _stage_sql(repo)
        _commit(repo, env=EV)
        rc, out = _approve(repo, "approve", "--reason", "r", "--name", "A",
                           script=APPROVE_BUNDLED)
        assert rc == 1 and "too recent" in out
        assert not (_sdir(repo) / ovr.APPROVAL_FILE).exists()

    def test_unknown_subcommand_is_usage_error(self, repo):
        rc, out = _approve(repo, "bogus")
        assert rc == 2

    def test_bare_flags_default_to_approve(self, repo):
        rc, out = _approve(repo, "--reason", "r", "--name", "A")
        assert rc == 1 and "No blocked commit attempt is recorded" in out

    def test_status_and_approve_work_from_subdirectory(self, repo):
        _stage_code(repo)
        _commit(repo)
        sub = repo / "pkg"
        sub.mkdir()
        rc, out = _approve(repo, "status", cwd=sub)
        assert rc == 0 and "charter-alongside-code (external-approval)" in out

    def test_outside_git_is_a_clear_error(self, tmp_path):
        # pytest's basetemp may live inside a checkout (e.g. --basetemp .tmp/...),
        # so stop git's upward discovery at this directory rather than relying
        # on where the temp dir happens to be.
        outside = tmp_path / "outside"
        outside.mkdir()
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path))
        rc, out = _approve(outside, "status", cwd=outside, env=env)
        assert rc == 1 and "not inside a git worktree" in out


class TestLintAllowDeprecated:
    """The deprecated lint-allow.json neither suppresses nor approves
    findings, and the hook never rewrites it."""

    def test_lint_allow_json_does_not_change_handling(self, repo):
        (repo / ".gator" / "lint-allow.json").write_text(
            json.dumps([{"rule": "SQL-001", "file": "migrate.txt"}]), encoding="utf-8")
        _stage_sql(repo, name="migrate.txt")
        rc, out = _commit(repo)
        assert rc != 0, "the allowlist never clears the pause"
        assert "SQL-001 [warning]" in out and "dangerous-pattern-pause [pause]" in out
        assert "lint-allow-deprecated" in out
        assert "Still reported despite being listed: SQL-001 in migrate.txt" in out

    def _track_allowlist(self, repo):
        content = json.dumps([{"rule": "SQL-001", "file": "migrate.sql"}]) + "\n"
        path = repo / ".gator" / "lint-allow.json"
        path.write_text(content, encoding="utf-8")
        _git(repo, "add", ".gator/lint-allow.json")
        _git(repo, "commit", "-q", "--no-verify", "-m", "track allowlist")
        _draft(repo, "feature")  # post-commit reset the draft
        return path, path.read_bytes()

    def _assert_allowlist_untouched(self, repo, path, original):
        assert path.read_bytes() == original, "working copy rewritten"
        assert _git(repo, "show", "HEAD:.gator/lint-allow.json").stdout.encode() \
            .replace(b"\r\n", b"\n") == original.replace(b"\r\n", b"\n"), \
            "committed copy changed"
        assert _git(repo, "status", "--porcelain", "--", ".gator/lint-allow.json").stdout == ""

    def test_lint_allow_json_is_never_rewritten_or_staged(self, repo):
        """The deprecated allowlist is read-only — an unrelated clean commit
        must not reset or stage it."""
        path, original = self._track_allowlist(repo)
        (repo / "notes.md").write_text("docs\n", encoding="utf-8")
        _git(repo, "add", "notes.md")
        rc, out = _commit(repo)
        assert rc == 0, out
        assert "lint-allow-deprecated" in out
        self._assert_allowlist_untouched(repo, path, original)
        assert ".gator/lint-allow.json" not in _git(
            repo, "show", "--name-only", "--format=", "HEAD").stdout

    def test_lint_allow_json_survives_envelope_approved_lint_commit(self, bundled_repo):
        repo = bundled_repo
        path, original = self._track_allowlist(repo)
        _stage_sql(repo)
        rc, _ = _commit(repo, env=EV)
        assert rc != 0
        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "migration", "--name", "Architect",
                           script=APPROVE_BUNDLED)
        assert rc == 0, out
        rc, out = _commit(repo, env=EV)
        assert rc == 0, out
        self._assert_allowlist_untouched(repo, path, original)

    def test_run_layer1_lint_tags_allowlisted(self, repo):
        import precommit_lint
        (repo / ".gator" / "lint-allow.json").write_text(
            json.dumps([{"rule": "SQL-001", "file": "migrate.sql"}]), encoding="utf-8")
        _stage_sql(repo)
        findings = precommit_lint.run_layer1_lint(["migrate.sql"], repo)
        sql = [f for f in findings if f["rule"] == "SQL-001"]
        assert sql and sql[0]["allowlisted"] is True


class TestCleanupAndLegacy:
    def test_successful_commit_retires_abandoned_and_legacy_state(self, repo):
        sdir = _sdir(repo)
        ovr.write_block(sdir, "stale-tree", [("charter-alongside-code", "m")], ["x.py"])
        for name in ("override-request.json", "override-approved.json", ".override-meta.json"):
            (repo / ".gator" / name).write_text("{}", encoding="utf-8")
        (repo / "notes.md").write_text("docs\n", encoding="utf-8")
        _git(repo, "add", "notes.md")
        rc, out = _commit(repo)
        assert rc == 0, out
        assert not (sdir / ovr.BLOCK_FILE).exists()
        assert ovr.legacy_files_present(repo / ".gator") == []

    def test_legacy_override_file_no_longer_authorizes(self, repo):
        _stage_code(repo)
        (repo / ".gator" / ".override").write_text("charter-skip", encoding="utf-8")
        rc, out = _commit(repo)
        assert rc != 0
        assert "legacy-override-file [fix-required]" in out
        assert "charter-alongside-code [external-approval]" in out


class TestWorktrees:
    def test_linked_worktree_has_separate_state(self, repo, tmp_path):
        _stage_code(repo)
        _commit(repo)
        assert (_sdir(repo) / ovr.BLOCK_FILE).exists()
        wt = tmp_path / "wt"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "side")
        assert ovr.state_dir(wt) != ovr.state_dir(repo)
        rc, out = _approve(wt, "status", cwd=wt)
        assert rc == 0 and "No blocked commit attempt" in out


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

EXT = {"SQL-001": ovr.EXTERNAL_APPROVAL}


class TestUnits:
    def test_classify_uses_the_explicit_map(self):
        assert ovr.classify("SQL-001", EXT) == ovr.EXTERNAL_APPROVAL
        assert ovr.classify("SQL-001") == ovr.FIX_REQUIRED
        assert ovr.classify("charter-alongside-code", EXT) == ovr.FIX_REQUIRED
        assert ovr.classify("something-new") == ovr.FIX_REQUIRED  # fail closed
        assert "charter-alongside-code" not in ovr.FIX_REQUIRED_RULES
        assert "charter-alongside-code" in ovr.CHARTER_OVERRIDE_RULES
        assert policy.charter_resolutions(
            [("charter-alongside-code", "m"), ("invalid-change-type", "m")]) == {
            "charter-alongside-code": ovr.EXTERNAL_APPROVAL}
        assert ovr.LEGACY_RECORD_RULE in ovr.FIX_REQUIRED_RULES
        for legacy in ("approvable", "lint"):
            assert not ovr.is_approvable(legacy)

    @pytest.mark.parametrize("mode,expected", [
        ("strict", policy.WARNING), ("warn", policy.WARNING), ("off", policy.WARNING),
        ("evidence_only", policy.EXTERNAL_APPROVAL), ("bogus", policy.WARNING),
    ])
    def test_dangerous_resolution_table(self, mode, expected):
        assert policy.dangerous_resolution(mode) == expected

    def test_split_lint_and_categories(self):
        findings = [
            {"rule": "SQL-001", "severity": "HIGH", "file": "a", "line": 1, "message": "m"},
            {"rule": "SEC-003", "severity": "CRITICAL", "file": "b\\c", "line": 0, "message": "m"},
            {"rule": "PY-001", "severity": "MEDIUM", "file": "a", "line": 2, "message": "m"},
        ]
        dangerous, external, advisory = policy.split_lint(findings, "strict")
        assert [f["rule"] for f in dangerous] == ["SQL-001", "SEC-003"]
        assert external == [] and [f["rule"] for f in advisory] == ["PY-001"]
        assert policy.finding_keys(dangerous) == ["SQL-001@a:1", "SEC-003@b/c:0"]
        dangerous, external, _ = policy.split_lint(findings, "evidence_only")
        assert dangerous == [] and policy.resolution_map(external) == {
            "SQL-001": policy.EXTERNAL_APPROVAL, "SEC-003": policy.EXTERNAL_APPROVAL}
        fix, ext = policy.report_categories(
            [("SQL-001", "m"), ("unmerged-index", "m")], EXT)
        assert fix == ["unmerged-index"] and ext == ["SQL-001"]

    def test_pause_and_skip_units(self):
        dangerous = [{"rule": "SQL-001", "severity": "HIGH", "file": "a b.txt", "line": 1,
                      "message": "m"}]
        key = "SQL-001@a b.txt:1"
        assert policy.pause_failure([]) is None
        rule, msg = policy.pause_failure([key])
        assert rule == policy.PAUSE_RULE and key in msg and policy.SKIP_FIELD in msg
        assert ovr.classify(rule, {rule: policy.PAUSE}) == ovr.PAUSE
        assert not ovr.is_approvable(ovr.PAUSE)
        assert policy.report_categories([(rule, msg)], {rule: policy.PAUSE}) == ([], [])
        assert policy.validate_skips({}, dangerous) == ([], [])
        assert policy.validate_skips({policy.SKIP_FIELD: [key]}, dangerous) == ([key], [])
        for raw in (["SQL-001@a b.txt:2"], [key, key], "nope"):
            keys, problems = policy.validate_skips({policy.SKIP_FIELD: raw}, dangerous)
            assert keys == [] and problems, raw
        keys, problems = policy.validate_skips({policy.SKIP_FIELD: [key]}, dangerous, [key])
        assert keys == [] and "both acknowledged and skipped" in problems[0]
        assert policy.skip_trailers([key]) == [f"Gator-Dangerous-Patterns-Unacknowledged: {key}"]
        assert policy.skip_trailers([]) == []

    def test_render_block_report_stop_box_only_for_external_approval(self):
        out = "\n".join(ovr.render_block_report(
            "H", [("charter-alongside-code", "m")], [], {}, [], None,
            attention=[("SQL-001", "a:1 — m")]))
        assert "[fix-required]" in out and "SQL-001 [warning]" in out
        assert "STOP" not in out and "gator hook approve" not in out
        out = "\n".join(ovr.render_block_report("H", [("SQL-001", "m")], [], EXT, [], None))
        assert "SQL-001 [external-approval]" in out and "gator hook approve" in out

    def test_apply_approval_keeps_approval_when_fix_required_remains(self, repo):
        """#35 at unit level: a valid approval covers its external-approval
        rule, is kept for the retry, and never clears a fix-required rule."""
        sdir, tree = _sdir(repo), ovr.index_tree(repo)
        block = ovr.write_block(sdir, tree, [("SQL-001", "m"), ("invalid-change-type", "m")],
                                [], EXT, now=time.time() - 60)
        ovr.write_approval(sdir, block, "A", "r")
        remaining, handoff, notes = ovr.apply_approval(
            sdir, tree, [("SQL-001", "m"), ("invalid-change-type", "m")], EXT)
        assert remaining == [("invalid-change-type", "m")]
        assert handoff is None and "is kept for the retry" in notes[0]
        assert (sdir / ovr.APPROVAL_FILE).exists()
        remaining, handoff, _ = ovr.apply_approval(sdir, tree, [("SQL-001", "m")], EXT)
        assert remaining == [] and handoff["overridden_rules"] == ["SQL-001"]
        assert handoff["charter_override"] is False

    def test_legacy_records(self, repo):
        sdir, tree = _sdir(repo), ovr.index_tree(repo)
        assert ovr.legacy_records(sdir, tree) is None
        _write_legacy_block(repo, [("SQL-001", "lint")])
        assert "earlier Gator runtime" in ovr.legacy_records(sdir, tree)
        assert ovr.legacy_records(sdir, "other-tree") is None
        ovr.write_block(sdir, tree, [(ovr.LEGACY_RECORD_RULE, "m")], [])
        assert ovr.legacy_records(sdir, tree), "the guard's own marker persists"
        ovr.write_block(sdir, tree, [("charter-alongside-code", "m")], [])
        assert ovr.legacy_records(sdir, tree) is None
        _write_approval(repo, ovr.read_block(sdir)[1], ["SQL-001"])
        assert "was not written for the current policy" in ovr.legacy_records(sdir, tree)
        # An approval this runtime writes carries the policy marker: not legacy.
        block = ovr.write_block(sdir, tree, [("charter-alongside-code", "m")], [],
                                {"charter-alongside-code": ovr.EXTERNAL_APPROVAL})
        approval = ovr.write_approval(sdir, block, "A", "r")
        assert approval["resolution_policy"] == ovr.RESOLUTION_POLICY
        assert ovr.legacy_records(sdir, tree) is None

    def test_sanitize(self):
        assert ovr.sanitize_trailer_value("a\r\nb\n  c", 50) == "a b c"
        assert len(ovr.sanitize_trailer_value("x" * 500, 200)) == 200

    def test_inspect_states(self, repo):
        sdir, tree = _sdir(repo), ovr.index_tree(repo)
        assert ovr.inspect(sdir, tree)["state"] == "absent"
        block = ovr.write_block(sdir, tree, [("SQL-001", "m")], ["a.py"], EXT, now=1000.0)
        ovr.write_approval(sdir, block, "A", "r", now=1005.0)
        assert ovr.inspect(sdir, tree, now=1006.0)["state"] == "premature"
        ovr.write_approval(sdir, block, "A", "r", now=1020.0)
        assert ovr.inspect(sdir, tree, now=1021.0)["state"] == "valid"
        assert ovr.inspect(sdir, "other", now=1021.0)["state"] == "mismatch"
        assert ovr.inspect(sdir, tree, now=block["expires_epoch"] + 1)["state"] == "expired"

    def test_block_id_stable_per_tree(self, repo):
        sdir = _sdir(repo)
        a = ovr.write_block(sdir, "t1", [("r1", "m")], [])
        b = ovr.write_block(sdir, "t1", [("r2", "m")], [])
        c = ovr.write_block(sdir, "t2", [("r1", "m")], [])
        assert a["block_id"] == b["block_id"] != c["block_id"]

    def test_hook_managed_files_do_not_change_identity(self, repo):
        before = ovr.index_tree(repo)
        (repo / ".gator" / "status.json").write_text('{"t": 1}', encoding="utf-8")
        (repo / ".gator" / "whiteboard.md").write_text("x", encoding="utf-8")
        _git(repo, "add", ".gator/status.json", ".gator/whiteboard.md")
        assert ovr.index_tree(repo) == before
        _stage_code(repo)
        assert ovr.index_tree(repo) != before

    def test_unmerged_index_fails_closed(self, repo):
        # No hooks for the setup commits: post-commit rewrites commit_draft.md,
        # which would leave the tree dirty and make `git merge` refuse to start.
        _git(repo, "config", "core.hooksPath", (repo / ".no-hooks").as_posix())
        _git(repo, "checkout", "-q", "-b", "other")
        (repo / "old.py").write_text("x = 'other'\n", encoding="utf-8")
        _git(repo, "commit", "-q", "--no-verify", "-am", "other")
        _git(repo, "checkout", "-q", "main")
        (repo / "old.py").write_text("x = 'main'\n", encoding="utf-8")
        _git(repo, "commit", "-q", "--no-verify", "-am", "main")
        _git(repo, "merge", "other", check=False)
        with pytest.raises(ovr.OverrideStateError, match="unmerged"):
            ovr.index_tree(repo)

    @pytest.mark.parametrize("mutate", [
        lambda b: b.pop("block_id"),
        lambda b: b.pop("created_epoch"),
        lambda b: b.update(expires_epoch="soon"),
        lambda b: b.update(created_epoch=True),
        lambda b: b.update(files="a.py"),
        lambda b: b.update(failures=[{"rule": "x"}]),
        lambda b: b.update(failures="nope"),
    ])
    def test_partial_block_is_malformed(self, repo, mutate):
        sdir = _sdir(repo)
        block = ovr.write_block(sdir, "t", [("charter-alongside-code", "m")], ["a.py"])
        mutate(block)
        (sdir / ovr.BLOCK_FILE).write_text(json.dumps(block), encoding="utf-8")
        assert ovr.read_block(sdir) == ("malformed", None)
        # write_block recovers with a fresh block instead of raising
        fresh = ovr.write_block(sdir, "t", [("charter-alongside-code", "m")], [])
        assert ovr.read_block(sdir)[0] == "ok" and fresh["block_id"]

    @pytest.mark.parametrize("mutate", [
        lambda a: a.pop("approval_id"),
        lambda a: a.update(approved_epoch="yesterday"),
        lambda a: a.update(expires_epoch=None),
        lambda a: a.update(approved_rules="SQL-001"),
        lambda a: a.update(approved_rules=[1]),
        lambda a: a.update(approved_by=""),
    ])
    def test_partial_approval_is_malformed(self, repo, mutate):
        sdir, tree = _sdir(repo), ovr.index_tree(repo)
        block = ovr.write_block(sdir, tree, [("SQL-001", "m")], [], EXT, now=1000.0)
        approval = ovr.write_approval(sdir, block, "A", "r", now=1020.0)
        mutate(approval)
        (sdir / ovr.APPROVAL_FILE).write_text(json.dumps(approval), encoding="utf-8")
        assert ovr.read_approval(sdir) == ("malformed", None)
        assert ovr.inspect(sdir, tree, now=1021.0)["state"] == "malformed"

    def test_partial_handoff_is_ignored(self, repo):
        sdir = _sdir(repo)
        (sdir).mkdir(parents=True, exist_ok=True)
        (sdir / ovr.HANDOFF_FILE).write_text(
            json.dumps({"schema": ovr.SCHEMA, "index_tree": "t"}), encoding="utf-8")
        assert ovr.read_handoff(sdir, tree="t") is None

    def test_write_approval_requires_name_reason_and_rules(self, repo):
        sdir = _sdir(repo)
        block = ovr.write_block(sdir, "t", [("charter-alongside-code", "m")], [])
        with pytest.raises(ValueError, match="no approvable"):
            ovr.write_approval(sdir, block, "A", "r")
        block = ovr.write_block(sdir, "t", [("SQL-001", "m")], [], EXT)
        with pytest.raises(ValueError, match="name"):
            ovr.write_approval(sdir, block, "  ", "r")
        with pytest.raises(ValueError, match="reason"):
            ovr.write_approval(sdir, block, "A", "")


# ---------------------------------------------------------------------------
# #76: machine-readable override CLI (status / approve / cancel --json)
# ---------------------------------------------------------------------------

def _cli_json(repo, *args, script=APPROVE):
    """Run gator-approve.py; stdout must be exactly one JSON object."""
    r = subprocess.run([sys.executable, str(script), *args], cwd=str(repo),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", stdin=subprocess.DEVNULL)
    return r.returncode, json.loads(r.stdout)


def _status_json(repo, script=APPROVE):
    rc, data = _cli_json(repo, "status", "--json", script=script)
    assert rc == 0 and data["schema"] == "gator-override-status-v1"
    return data


def _garbage(repo, name):
    sdir = _sdir(repo)
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / name).write_text("{not json", encoding="utf-8")


def _charter_block(repo, backdate=True):
    _stage_code(repo)
    rc, _ = _commit(repo)
    assert rc != 0
    if backdate:
        _backdate_block(repo)


def _setup_none(repo):
    pass


def _setup_external(repo):
    _charter_block(repo)


def _setup_pause(repo):
    _stage_sql(repo, name="migrate.txt")
    assert _commit(repo)[0] != 0


def _setup_fix(repo):
    _draft(repo, "bogus")
    (repo / "notes.txt").write_text("n\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    assert _commit(repo)[0] != 0


def _setup_mixed(repo):
    _stage_code(repo)
    _stage_sql(repo, name="migrate.txt")
    assert _commit(repo)[0] != 0
    _backdate_block(repo)


def _setup_approved(repo):
    _charter_block(repo)
    assert _approve(repo, "approve", "--reason", "r", "--name", "A")[0] == 0


def _setup_stale(repo):
    _charter_block(repo)
    _stage_code(repo, name="bar.py")


def _setup_expired(repo):
    _charter_block(repo)
    path = _sdir(repo) / ovr.BLOCK_FILE
    block = json.loads(path.read_text(encoding="utf-8"))
    block["expires_epoch"] = time.time() - 1
    path.write_text(json.dumps(block), encoding="utf-8")


def _setup_malformed(repo):
    _garbage(repo, ovr.BLOCK_FILE)


def _setup_legacy(repo):
    _write_legacy_block(repo, [("charter-alongside-code", "approvable")])


STATUS_CASES = {
    # case: (setup, state, {rule: resolution}, can_approve, approve_refusal)
    "none": (_setup_none, "none", {}, False, "no-block"),
    "external": (_setup_external, "blocked",
                 {"charter-alongside-code": "external-approval"}, True, None),
    "pause": (_setup_pause, "blocked",
              {"dangerous-pattern-pause": "pause"}, False, "nothing-approvable"),
    "fix": (_setup_fix, "blocked",
            {"invalid-change-type": "fix-required"}, False, "nothing-approvable"),
    "mixed": (_setup_mixed, "blocked",
              {"charter-alongside-code": "external-approval",
               "dangerous-pattern-pause": "pause"}, True, None),
    "approved": (_setup_approved, "approved",
                 {"charter-alongside-code": "external-approval"}, False, None),
    "stale": (_setup_stale, "stale",
              {"charter-alongside-code": "external-approval"}, False, "tree-changed"),
    "expired": (_setup_expired, "expired",
                {"charter-alongside-code": "external-approval"}, False, "expired"),
    "malformed": (_setup_malformed, "malformed", {}, False, "malformed"),
    "legacy": (_setup_legacy, "legacy",
               {"charter-alongside-code": "fix-required"}, False, "legacy"),
}


class TestOverrideJson:
    @pytest.mark.parametrize("case", list(STATUS_CASES))
    def test_status_json_states(self, repo, case):
        setup, state, rules, can_approve, refusal = STATUS_CASES[case]
        setup(repo)
        data = _status_json(repo)
        assert data["state"] == state
        assert {f["rule"]: f["resolution"] for f in data["findings"]} == rules
        assert data["can_approve"] is can_approve
        assert data["approve_refusal"] == refusal
        assert data["architect_default"] == "Test"
        assert (data["revision"] is None) is (case == "none")
        if case == "malformed":
            assert data["block"] is None and data["malformed"] == ["block"]
        if case == "legacy":
            assert data["findings"][0]["legacy"] is True
        if case == "approved":
            assert data["covered_rules"] == ["charter-alongside-code"]
            assert data["uncovered_external_rules"] == []
            assert data["findings"][0]["covered"] is True
            assert "reason" not in data["approval"]

    def test_status_reports_the_delay(self, repo):
        _charter_block(repo, backdate=False)
        data = _status_json(repo)
        assert data["approve_refusal"] == "too-recent" and not data["can_approve"]
        assert 0 < data["approve_wait_seconds"] <= ovr.MIN_APPROVAL_DELAY_SECONDS

    @pytest.mark.parametrize("case", ["block-changed", "findings-changed", "too-recent",
                                      "nothing-approvable", "invalid-input", "tree-changed"])
    def test_approve_json_refusals(self, repo, case):
        if case == "nothing-approvable":
            _setup_pause(repo)
            _backdate_block(repo)
        else:
            _charter_block(repo, backdate=(case != "too-recent"))
        status = _status_json(repo)
        args = ["approve", "--json", "--name", "A", "--reason", "r",
                "--expect-block", status["block"]["block_id"],
                "--expect-revision", status["revision"]]
        if case == "block-changed":
            args[args.index("--expect-block") + 1] = "deadbeef"
        elif case == "findings-changed":
            args[args.index("--expect-revision") + 1] = "0" * 16
        elif case == "invalid-input":
            args[args.index("--name") + 1] = "x" * 81
        elif case == "tree-changed":
            _stage_code(repo, name="bar.py")
        rc, data = _cli_json(repo, *args)
        assert rc == 1 and data["ok"] is False and data["refusal"] == case
        assert data["schema"] == "gator-override-approve-v1"
        if case == "too-recent":
            assert data["retry_after_seconds"] >= 1
        assert not (_sdir(repo) / ovr.APPROVAL_FILE).exists()

    def test_approve_json_records_approval_and_commit_carries_trailers(self, repo):
        _charter_block(repo)
        status = _status_json(repo)
        rc, data = _cli_json(repo, "approve", "--json", "--name", "Dash Architect",
                             "--reason", "no charter edit needed",
                             "--expect-block", status["block"]["block_id"],
                             "--expect-revision", status["revision"])
        assert rc == 0 and data["ok"] is True, data
        assert data["approval"]["approved_rules"] == ["charter-alongside-code"]
        assert data["remaining"] == {"fix_required": [], "paused": []}
        rc, out = _commit(repo)
        assert rc == 0, out
        msg = _last_message(repo)
        assert "Gator-Override-Approved-By: Dash Architect" in msg
        assert "Gator-Override-Reason: no charter edit needed" in msg
        assert _status_json(repo)["state"] == "none"

    def test_approve_refuses_changed_findings_under_same_block_id(self, repo):
        sdir, tree = _sdir(repo), ovr.index_tree(repo)
        ext = {"charter-alongside-code": ovr.EXTERNAL_APPROVAL,
               "charter-index-gap": ovr.EXTERNAL_APPROVAL}
        first = ovr.write_block(sdir, tree, [("charter-alongside-code", "m")], [], ext,
                                now=time.time() - 60)
        seen = _status_json(repo)
        second = ovr.write_block(sdir, tree, [("charter-alongside-code", "m"),
                                              ("charter-index-gap", "m")], [], ext)
        assert second["block_id"] == first["block_id"], "the real stable-ID path"
        rc, data = _cli_json(repo, "approve", "--json", "--name", "A", "--reason", "r",
                             "--expect-block", seen["block"]["block_id"],
                             "--expect-revision", seen["revision"])
        assert rc == 1 and data["refusal"] == "findings-changed"
        assert not (sdir / ovr.APPROVAL_FILE).exists()

    def test_status_reports_uncovered_rule_after_supersede(self, repo):
        sdir, tree = _sdir(repo), ovr.index_tree(repo)
        ext = {"charter-alongside-code": ovr.EXTERNAL_APPROVAL,
               "charter-index-gap": ovr.EXTERNAL_APPROVAL}
        ovr.write_block(sdir, tree, [("charter-alongside-code", "m")], [], ext,
                        now=time.time() - 60)
        seen = _status_json(repo)
        rc, _ = _cli_json(repo, "approve", "--json", "--name", "A", "--reason", "r",
                          "--expect-block", seen["block"]["block_id"],
                          "--expect-revision", seen["revision"])
        assert rc == 0
        ovr.write_block(sdir, tree, [("charter-alongside-code", "m"),
                                     ("charter-index-gap", "m")], [], ext)
        data = _status_json(repo)
        assert data["state"] == "blocked"
        assert data["covered_rules"] == ["charter-alongside-code"]
        assert data["uncovered_external_rules"] == ["charter-index-gap"]
        assert {f["rule"]: f["covered"] for f in data["findings"]} == {
            "charter-alongside-code": True, "charter-index-gap": False}
        assert data["can_approve"] is True

    def test_approval_plus_pause_stays_paused(self, repo):
        _setup_mixed(repo)
        assert _approve(repo, "approve", "--reason", "r", "--name", "A")[0] == 0
        rc, out = _commit(repo)
        assert rc != 0 and "dangerous-pattern-pause [pause]" in out
        data = _status_json(repo)
        assert data["state"] == "approved"
        assert data["uncovered_external_rules"] == []
        assert "dangerous-pattern-pause" in {f["rule"] for f in data["findings"]}

    def test_evidence_only_dangerous_finding_is_external_approval(self, bundled_repo):
        _stage_sql(bundled_repo)
        assert _commit(bundled_repo, env=EV)[0] != 0
        data = _status_json(bundled_repo, script=APPROVE_BUNDLED)
        resolutions = {f["rule"]: f["resolution"] for f in data["findings"]}
        assert resolutions["SQL-001"] == "external-approval"

    @pytest.mark.parametrize("case", ["match", "changed", "vanished", "malformed-block",
                                      "malformed-approval", "replaced"])
    def test_cancel_json_guard(self, repo, case):
        if case in ("malformed-block", "replaced"):
            _garbage(repo, ovr.BLOCK_FILE)
        else:
            _charter_block(repo)
        if case == "malformed-approval":
            readable_rev = _status_json(repo)["revision"]
            _garbage(repo, ovr.APPROVAL_FILE)
        status = _status_json(repo)
        args = ["cancel", "--json", "--expect-revision", status["revision"]]
        if status["block"]:
            args += ["--expect-block", status["block"]["block_id"]]
        if case == "changed":
            args[3] = "0" * 16
        elif case == "vanished":
            assert _cli_json(repo, "cancel", "--json")[0] == 0
        elif case == "replaced":
            _stage_code(repo)
            assert _commit(repo)[0] != 0  # a later attempt writes a readable block
        rc, data = _cli_json(repo, *args)
        assert data["schema"] == "gator-override-cancel-v1"
        if case in ("changed", "vanished", "replaced"):
            # The block-ID guard runs first: a vanished block that was shown
            # with an ID is block-changed; a revision-only guard (malformed
            # block replaced) is findings-changed.
            expected = "block-changed" if case == "vanished" else "findings-changed"
            assert rc == 1 and data["refusal"] == expected
            assert data["removed"] == []
            if case != "vanished":
                assert (_sdir(repo) / ovr.BLOCK_FILE).exists()
            return
        assert rc == 0 and data["ok"] is True
        assert _status_json(repo)["state"] == "none"
        if case == "malformed-block":
            assert status["state"] == "malformed" and status["malformed"] == ["block"]
        if case == "malformed-approval":
            assert status["malformed"] == ["approval"]
            assert status["revision"] != readable_rev

    def test_unreadable_record_has_no_revision(self, repo, monkeypatch):
        """If a malformed record's raw bytes cannot be read, nothing can
        match it, so a guarded action fails safe."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("gator_approve_mod", APPROVE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _garbage(repo, ovr.BLOCK_FILE)

        def boom(path):
            raise mod._Unreadable("locked")
        monkeypatch.setattr(mod, "_raw_digest", boom)
        snap = mod._snapshot(_sdir(repo))
        assert snap["revision"] is None and snap["unreadable"] is True
        assert mod._guard_refusal(snap, None, "a" * 16)[0] == "unavailable"

    def test_json_outside_git_is_unavailable(self, tmp_path):
        rc, data = _cli_json(tmp_path, "status", "--json")
        assert rc == 1 and data["state"] == "unavailable"
        rc, data = _cli_json(tmp_path, "approve", "--json")
        assert rc == 1 and data["refusal"] == "unavailable"
