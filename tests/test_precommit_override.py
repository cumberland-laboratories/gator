"""
#34 / #35 — tree-bound, retry-safe pre-commit override approval.

Integration tests drive REAL git commits in throwaway temp repos whose
pre-commit / commit-msg / post-commit hooks run the starter-template
gator-pre-commit.py phases. The Architect approval step runs
gator-approve.py only inside those temp repos (never against this repo) —
the constitution forbids the agent approving real governance blocks.

The headline regression (#35): a charter block + a second, different block
(invalid change-type). After the Architect approves the charter finding, the
retry is blocked only by the fix-required finding, the approval SURVIVES,
`override status` diagnoses the remaining rule, and after fixing it the
commit lands with durable override trailers and no leftover state.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = (Path(__file__).resolve().parent.parent / "src" / "gator_command"
           / "templates" / "gator-starter" / "scripts")
PRE_COMMIT = SCRIPTS / "gator-pre-commit.py"
APPROVE = SCRIPTS / "gator-approve.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import precommit_override as ovr  # noqa: E402


# Lint-triggering SQL fixtures (rule SQL-001). Built by concatenation so
# this test SOURCE does not itself match the detector; the temp repos still
# receive the real statement.
SQL_DROP_USERS = "DROP " + "TABLE users;\n"
SQL_DROP_ORDERS = "DROP " + "TABLE orders;\n"


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


def _git(repo, *args, check=True):
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {r.stdout}\n{r.stderr}")
    return r


def _write_hook(hooks, name, body):
    p = hooks / name
    p.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8", newline="\n")
    p.chmod(0o755)


BUNDLED_SCRIPTS = (Path(__file__).resolve().parent.parent / "enterprise" / "enterprise-cli"
                   / "gator_enterprise_cli" / "bundled_scripts")


@pytest.fixture
def repo(tmp_path):
    return _make_repo(tmp_path, SCRIPTS)


@pytest.fixture
def bundled_repo(tmp_path):
    """Same repo, but the hooks run the Enterprise bundled pre-commit copy
    (maintained separately from the template; patched at the same anchors)."""
    return _make_repo(tmp_path, BUNDLED_SCRIPTS)


def _make_repo(tmp_path, scripts_dir):
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
    (gator / "config.json").write_text('{"enforcement_level": "strict"}\n', encoding="utf-8")
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
    import os
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


def _last_message(repo):
    return _git(repo, "log", "-1", "--format=%B").stdout


# ---------------------------------------------------------------------------
# #35 headline regression
# ---------------------------------------------------------------------------

class TestSecondBlockIsApprovableAndDiagnosable:
    def test_full_lifecycle(self, repo):
        _stage_code(repo)
        _draft(repo, "bogus")

        rc, out = _commit(repo)
        assert rc != 0
        assert "charter-alongside-code [approvable]" in out
        assert "invalid-change-type [fix-required]" in out
        assert "gator hook approve" in out
        block1 = json.loads((_sdir(repo) / ovr.BLOCK_FILE).read_text(encoding="utf-8"))
        assert {f["rule"]: f["resolution"] for f in block1["failures"]} == {
            "charter-alongside-code": "approvable",
            "invalid-change-type": "fix-required",
        }

        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "docs-only refactor", "--name", "Architect")
        assert rc == 0, out
        assert "Still fix-required (not approvable): invalid-change-type" in out
        assert (_sdir(repo) / ovr.APPROVAL_FILE).exists()

        # The #35 moment: a second, different block after approval.
        rc, out = _commit(repo)
        assert rc != 0
        assert "invalid-change-type [fix-required]" in out
        assert "✗ charter-alongside-code" not in out, "approved rule must not block again"
        assert "is kept for the retry" in out
        assert (_sdir(repo) / ovr.APPROVAL_FILE).exists(), "approval must survive the retry"
        block2 = json.loads((_sdir(repo) / ovr.BLOCK_FILE).read_text(encoding="utf-8"))
        assert block2["block_id"] == block1["block_id"], "same tree -> same block id"

        # Diagnosable, never "no pending request".
        rc, out = _approve(repo, "status")
        assert rc == 0
        assert "invalid-change-type (fix-required)" in out
        assert "No blocked commit attempt" not in out

        _draft(repo, "fix")
        rc, out = _commit(repo)
        assert rc == 0, out
        assert "OVERRIDE (charter-alongside-code) approved by Architect" in out

        msg = _last_message(repo)
        assert "Gator-Charter-Changed: override-skip" in msg
        assert "Gator-Override-Approved-By: Architect" in msg
        assert f"Gator-Override-Block: {block1['block_id']}" in msg
        assert "Gator-Override-Reason: docs-only refactor" in msg
        assert "Gator-Override-Rules: charter-alongside-code" in msg

        # Consumed only now, by post-commit.
        for name in (ovr.BLOCK_FILE, ovr.APPROVAL_FILE, ovr.HANDOFF_FILE):
            assert not (_sdir(repo) / name).exists(), f"{name} left behind"

        # Trailer readers (change 10) surface the override from real history.
        # Run in a clean interpreter: this module puts the starter-template
        # scripts dir first on sys.path, whose gator_core.py is a different
        # file from the package copy repo-status imports in production.
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
        assert ev["reason"] == "docs-only refactor"
        assert ev["rules"] == ["charter-alongside-code"]
        assert ev["block_id"] == block1["block_id"]


class TestEnterpriseBundledRuntime:
    """The #35 headline flow through the Enterprise bundled copies."""

    def test_second_block_keeps_approval_with_bundled_scripts(self, bundled_repo):
        # The bundled copy predates the change-type enum gate (known drift,
        # roadmap "bundled gator-pre-commit.py sync"), so the second,
        # fix-required block here is `missing-message` — shared by both copies.
        repo = bundled_repo
        approve = BUNDLED_SCRIPTS / "gator-approve.py"
        _stage_code(repo)
        (repo / ".gator" / "commit_draft.md").write_text(
            "---\nmessage: \"\"\nchange-type: feature\n---\n\n# Session Change Log\n",
            encoding="utf-8")
        rc, out = _commit(repo)
        assert rc != 0 and "charter-alongside-code [approvable]" in out
        assert "missing-message [fix-required]" in out
        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "ok", "--name", "Architect", script=approve)
        assert rc == 0, out
        rc, out = _commit(repo)
        assert rc != 0 and "is kept for the retry" in out
        assert (_sdir(repo) / ovr.APPROVAL_FILE).exists()
        rc, out = _approve(repo, "status", script=approve)
        assert "missing-message (fix-required)" in out
        _draft(repo, "fix")
        rc, out = _commit(repo)
        assert rc == 0, out
        msg = _last_message(repo)
        assert "Gator-Charter-Changed: override-skip" in msg
        assert "Gator-Override-Approved-By: Architect" in msg
        assert not (_sdir(repo) / ovr.APPROVAL_FILE).exists()


class TestEnterpriseEvidenceOnly:
    """Whiteboard Phase 2 P1: Enterprise `evidence_only` (GATOR_HOOK_MODE)
    lint must go through the same tree-bound envelope — block recorded,
    Architect approval of the exact change, retry, consumed post-commit."""

    ENV = {"GATOR_HOOK_MODE": "evidence_only"}
    APPROVE_BUNDLED = BUNDLED_SCRIPTS / "gator-approve.py"

    def _stage_sql(self, repo):
        (repo / "migrate.sql").write_text(SQL_DROP_USERS, encoding="utf-8")
        _git(repo, "add", "migrate.sql")

    def test_block_approve_retry(self, bundled_repo):
        repo = bundled_repo
        self._stage_sql(repo)
        rc, out = _commit(repo, env=self.ENV)
        assert rc != 0
        assert "BLOCKED (evidence_only" in out
        assert "SQL-001 [lint]" in out
        assert "gator hook approve" in out
        assert "charter-alongside-code" not in out, "evidence_only skips charter rules"
        assert (_sdir(repo) / ovr.BLOCK_FILE).exists()

        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "intentional migration",
                           "--name", "Architect", script=self.APPROVE_BUNDLED)
        assert rc == 0, out

        rc, out = _commit(repo, env=self.ENV)
        assert rc == 0, out
        assert "OVERRIDE (SQL-001) approved by Architect (evidence_only)" in out
        msg = _last_message(repo)
        assert "Gator-Override-Rules: SQL-001" in msg
        assert "Gator-Override-Approved-By: Architect" in msg
        for name in (ovr.BLOCK_FILE, ovr.APPROVAL_FILE, ovr.HANDOFF_FILE):
            assert not (_sdir(repo) / name).exists()

    def test_changed_content_needs_new_approval(self, bundled_repo):
        repo = bundled_repo
        self._stage_sql(repo)
        _commit(repo, env=self.ENV)
        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "r", "--name", "A",
                           script=self.APPROVE_BUNDLED)
        assert rc == 0, out
        (repo / "migrate.sql").write_text(SQL_DROP_USERS + SQL_DROP_ORDERS,
                                          encoding="utf-8")
        _git(repo, "add", "migrate.sql")
        rc, out = _commit(repo, env=self.ENV)
        assert rc != 0 and "Previous approval retired" in out

    def test_lint_allow_is_explained_not_honored(self, bundled_repo):
        repo = bundled_repo
        (repo / ".gator" / "lint-allow.json").write_text(
            json.dumps([{"rule": "SQL-001", "file": "migrate.sql"}]), encoding="utf-8")
        self._stage_sql(repo)
        rc, out = _commit(repo, env=self.ENV)
        assert rc != 0
        assert "no longer authorizes lint findings" in out
        assert "SQL-001 in migrate.sql" in out

    def test_clean_evidence_only_commit_passes(self, bundled_repo):
        repo = bundled_repo
        (repo / "notes.sql").write_text("SELECT 1;\n", encoding="utf-8")
        _git(repo, "add", "notes.sql")
        rc, out = _commit(repo, env=self.ENV)
        assert rc == 0, out


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

    def test_approve_refuses_premature_approval(self, repo):
        _stage_code(repo)
        _commit(repo)
        rc, out = _approve(repo, "approve", "--reason", "r", "--name", "A")
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
        assert rc == 0 and "charter-alongside-code (approvable)" in out

    def test_outside_git_is_a_clear_error(self, tmp_path):
        # pytest's basetemp may live inside a checkout (e.g. --basetemp .tmp/...),
        # so stop git's upward discovery at this directory rather than relying
        # on where the temp dir happens to be.
        import os
        outside = tmp_path / "outside"
        outside.mkdir()
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path))
        rc, out = _approve(outside, "status", cwd=outside, env=env)
        assert rc == 1 and "not inside a git worktree" in out


# ---------------------------------------------------------------------------
# Supersede matrix and fail-closed states
# ---------------------------------------------------------------------------

def _block_and_approve(repo):
    _stage_code(repo)
    rc, _ = _commit(repo)
    assert rc != 0
    _backdate_block(repo)
    rc, out = _approve(repo, "approve", "--reason", "ok", "--name", "Architect")
    assert rc == 0, out


class TestSupersede:
    @pytest.mark.parametrize("change", ["modify", "add", "delete", "rename"])
    def test_staged_change_invalidates_approval(self, repo, change):
        _block_and_approve(repo)
        if change == "modify":
            _stage_code(repo, text="x = 2\n")
        elif change == "add":
            _stage_code(repo, name="bar.py", text="y = 1\n")
        elif change == "delete":
            _git(repo, "rm", "-q", "old.py")
        elif change == "rename":
            _git(repo, "mv", "old.py", "old2.py")
        rc, out = _commit(repo)
        assert rc != 0
        assert "Previous approval retired" in out and "different staged tree" in out
        assert not (_sdir(repo) / ovr.APPROVAL_FILE).exists()
        assert "charter-alongside-code [approvable]" in out

    def test_expired_approval_is_retired(self, repo):
        _block_and_approve(repo)
        path = _sdir(repo) / ovr.APPROVAL_FILE
        approval = json.loads(path.read_text(encoding="utf-8"))
        approval["expires_epoch"] = 1
        path.write_text(json.dumps(approval), encoding="utf-8")
        rc, out = _commit(repo)
        assert rc != 0 and "expired" in out
        assert not path.exists()

    @pytest.mark.parametrize("corrupt", ["block_missing_fields", "approval_missing_id",
                                         "approval_bad_epochs"])
    def test_schema_valid_partial_state_fails_closed_without_traceback(self, repo, corrupt):
        """Whiteboard P2: valid JSON with the right schema but missing or
        mistyped fields must never crash the hook."""
        _block_and_approve(repo)
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

        rc, out = _commit(repo)
        assert "Traceback" not in out, out
        if corrupt == "block_missing_fields":
            # The approval is intact and valid for this tree: commit passes.
            assert rc == 0, out
        else:
            assert rc != 0
            assert "Previous approval retired" in out
            assert "charter-alongside-code [approvable]" in out
            assert not (sdir / ovr.APPROVAL_FILE).exists()
        for args in (("status",), ("approve", "--reason", "r", "--name", "A")):
            rc2, out2 = _approve(repo, *args)
            assert "Traceback" not in out2, out2

    def test_malformed_approval_fails_closed(self, repo):
        _block_and_approve(repo)
        (_sdir(repo) / ovr.APPROVAL_FILE).write_text("{not json", encoding="utf-8")
        rc, out = _commit(repo)
        assert rc != 0 and "charter-alongside-code [approvable]" in out
        assert not (_sdir(repo) / ovr.APPROVAL_FILE).exists()

    def test_approval_for_other_rule_keeps_it_and_reports_new_rule(self, repo):
        """A newly introduced approvable rule is not covered by an older
        snapshot: the approval is kept, the new rule still needs approval."""
        _stage_code(repo)
        _commit(repo)
        block = _backdate_block(repo)
        block["failures"] = [{"rule": "charter-index-gap", "resolution": "approvable", "message": "m"}]
        ovr.write_approval(_sdir(repo), block, "Architect", "earlier rule")
        rc, out = _commit(repo)
        assert rc != 0
        assert "charter-alongside-code [approvable]" in out
        assert (_sdir(repo) / ovr.APPROVAL_FILE).exists()

    def test_cancel_retires_block_and_approval(self, repo):
        _block_and_approve(repo)
        rc, out = _approve(repo, "cancel")
        assert rc == 0 and "Cancelled" in out
        assert not any((_sdir(repo) / n).exists()
                       for n in (ovr.BLOCK_FILE, ovr.APPROVAL_FILE, ovr.HANDOFF_FILE))
        rc, out = _approve(repo, "status")
        assert "No blocked commit attempt" in out


class TestRetrySafety:
    def test_commit_msg_failure_keeps_approval_for_retry(self, repo):
        _block_and_approve(repo)
        marker = Path(_git(repo, "rev-parse", "--git-dir").stdout.strip())
        marker = marker if marker.is_absolute() else repo / marker
        (marker / "fail-commit-msg").write_text("1", encoding="utf-8")
        rc, out = _commit(repo)
        assert rc != 0
        assert (_sdir(repo) / ovr.APPROVAL_FILE).exists(), out
        assert (_sdir(repo) / ovr.HANDOFF_FILE).exists(), out

        (marker / "fail-commit-msg").unlink()
        rc, out = _commit(repo)
        assert rc == 0, out
        assert "Gator-Override-Approved-By: Architect" in _last_message(repo)
        assert not (_sdir(repo) / ovr.APPROVAL_FILE).exists()

    def test_trailer_values_cannot_inject(self, repo):
        _stage_code(repo)
        _commit(repo)
        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason",
                           "ok\nGator-Architect: mallory\r\nGator-Fake: 1",
                           "--name", "Arch\nGator-Evil: x")
        assert rc == 0, out
        rc, out = _commit(repo)
        assert rc == 0, out
        lines = _last_message(repo).splitlines()
        assert not any(l.startswith("Gator-Architect: mallory") for l in lines)
        assert not any(l.startswith("Gator-Fake") or l.startswith("Gator-Evil") for l in lines)
        reason = [l for l in lines if l.startswith("Gator-Override-Reason:")]
        assert reason == ["Gator-Override-Reason: ok Gator-Architect: mallory Gator-Fake: 1"]


class TestLintEnvelope:
    """#34 change 5 — HIGH/CRITICAL lint joins the envelope; the deprecated
    lint-allow.json no longer suppresses findings on its own."""

    def _stage_sql(self, repo):
        (repo / "migrate.sql").write_text(SQL_DROP_USERS, encoding="utf-8")
        _git(repo, "add", "migrate.sql")

    def test_lint_finding_is_approvable_for_the_exact_change(self, repo):
        self._stage_sql(repo)
        rc, out = _commit(repo)
        assert rc != 0
        assert "SQL-001 [lint]" in out
        block = _backdate_block(repo)
        assert "SQL-001" in ovr.approvable_rules(block)
        rc, out = _approve(repo, "approve", "--reason", "intentional migration", "--name", "Architect")
        assert rc == 0, out
        rc, out = _commit(repo)
        assert rc == 0, out
        rules = [l for l in _last_message(repo).splitlines() if l.startswith("Gator-Override-Rules:")]
        assert rules and "SQL-001" in rules[0]

    def test_lint_allow_json_no_longer_suppresses(self, repo):
        (repo / ".gator" / "lint-allow.json").write_text(
            json.dumps([{"rule": "SQL-001", "file": "migrate.sql"}]), encoding="utf-8")
        self._stage_sql(repo)
        rc, out = _commit(repo)
        assert rc != 0, "an unscoped allowlist entry must not authorize the commit"
        assert "SQL-001 [lint]" in out
        assert "lint-allow-deprecated" in out
        assert "Still blocking despite being listed: SQL-001 in migrate.sql" in out

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
        """Phase 3 review P2: the deprecated allowlist is read-only — an
        unrelated clean commit must not reset or stage it."""
        path, original = self._track_allowlist(repo)
        (repo / "notes.md").write_text("docs\n", encoding="utf-8")
        _git(repo, "add", "notes.md")
        rc, out = _commit(repo)
        assert rc == 0, out
        assert "lint-allow-deprecated" in out
        self._assert_allowlist_untouched(repo, path, original)
        assert ".gator/lint-allow.json" not in _git(
            repo, "show", "--name-only", "--format=", "HEAD").stdout

    def test_lint_allow_json_survives_envelope_approved_lint_commit(self, repo):
        path, original = self._track_allowlist(repo)
        self._stage_sql(repo)
        rc, _ = _commit(repo)
        assert rc != 0
        _backdate_block(repo)
        rc, out = _approve(repo, "approve", "--reason", "migration", "--name", "Architect")
        assert rc == 0, out
        rc, out = _commit(repo)
        assert rc == 0, out
        self._assert_allowlist_untouched(repo, path, original)

    def test_run_layer1_lint_tags_allowlisted(self, repo):
        import precommit_lint
        (repo / ".gator" / "lint-allow.json").write_text(
            json.dumps([{"rule": "SQL-001", "file": "migrate.sql"}]), encoding="utf-8")
        self._stage_sql(repo)
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
        assert "charter-alongside-code [approvable]" in out


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

class TestUnits:
    def test_classify(self):
        assert ovr.classify("charter-alongside-code") == ovr.APPROVABLE
        assert ovr.classify("dangerous-eval", lint_rules={"dangerous-eval"}) == ovr.LINT
        assert ovr.classify("invalid-change-type") == ovr.FIX_REQUIRED
        assert ovr.classify("something-new") == ovr.FIX_REQUIRED  # fail closed

    def test_sanitize(self):
        assert ovr.sanitize_trailer_value("a\r\nb\n  c", 50) == "a b c"
        assert len(ovr.sanitize_trailer_value("x" * 500, 200)) == 200

    def test_inspect_states(self, repo):
        sdir, tree = _sdir(repo), ovr.index_tree(repo)
        assert ovr.inspect(sdir, tree)["state"] == "absent"
        block = ovr.write_block(sdir, tree, [("charter-alongside-code", "m")], ["a.py"],
                                now=1000.0)
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
        lambda a: a.update(approved_rules="charter-alongside-code"),
        lambda a: a.update(approved_rules=[1]),
        lambda a: a.update(approved_by=""),
    ])
    def test_partial_approval_is_malformed(self, repo, mutate):
        sdir, tree = _sdir(repo), ovr.index_tree(repo)
        block = ovr.write_block(sdir, tree, [("charter-alongside-code", "m")], [], now=1000.0)
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
        block = ovr.write_block(sdir, "t", [("invalid-change-type", "m")], [])
        with pytest.raises(ValueError, match="no approvable"):
            ovr.write_approval(sdir, block, "A", "r")
        block = ovr.write_block(sdir, "t", [("charter-alongside-code", "m")], [])
        with pytest.raises(ValueError, match="name"):
            ovr.write_approval(sdir, block, "  ", "r")
        with pytest.raises(ValueError, match="reason"):
            ovr.write_approval(sdir, block, "A", "")
