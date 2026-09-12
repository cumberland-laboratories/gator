"""
Dashboard UI harness internals (Plan A, v2.13.0, §4.3 + §5.2 + §7).

Non-conftest module so pytest's global `conftest` alias resolves
to tests/conftest.py (which other tests import from). This module
carries the builder, parser, finalizers, reader/drain helpers,
snapshot, and seed-repo helpers. `conftest.py` in this directory
imports from here and defines the pytest fixtures.
"""

import hashlib
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


# ── §4.3: the builder ────────────────────────────────────────────


def build_dashboard_fleet(tmp_path_factory, *, extra_registry_size,
                          debug, lifecycle_observer=None):
    """Public builder. `lifecycle_observer`, if given, is a mutable
    dict this function populates INCREMENTALLY inside the same
    try/finally that owns startup, so any single-step failure still
    exposes every handle that had been created before the failure.

    Observer keys populated in order:
      - `proc`           immediately after Popen returns
      - `stdout`, `stderr`   immediately after Popen returns (from proc)
      - `stdout_thread`  after the first reader-thread start succeeds
      - `stderr_thread`  after the second reader-thread start succeeds

    A raise at any step leaves the earlier keys populated so tests
    can post-mortem the state.
    """
    import json  # local — avoids polluting module-level imports

    pre_hash, pre_meta = snapshot_real_registry()

    home = tmp_path_factory.mktemp("gator_ui_home")
    (home / ".gator").mkdir()
    fleet_root = tmp_path_factory.mktemp("gator_ui_fleet")
    alpha = seed_repo(fleet_root, "alpha")
    beta = seed_repo(fleet_root, "beta")

    scratch_entries = []
    for i in range(extra_registry_size):
        scratch_parent = tmp_path_factory.mktemp(
            f"gator_ui_missing_{i:02d}")
        missing_path = scratch_parent / "does_not_exist"
        scratch_entries.append(
            {"name": f"missing-{i:02d}", "path": str(missing_path)})

    registry = {
        "schema": "gator-dashboard-registry-v1",
        "repos": [
            {"name": "alpha", "path": str(alpha["repo"])},
            {"name": "beta", "path": str(beta["repo"])},
        ] + scratch_entries,
    }
    (home / ".gator" / "dashboard-repos.json").write_text(
        json.dumps(registry, indent=2), encoding="utf-8")

    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
    }
    if debug:
        env["GATOR_DASHBOARD_DEBUG"] = "1"
    else:
        env.pop("GATOR_DASHBOARD_DEBUG", None)
    env.pop("GATOR_DASHBOARD_DISCOVERY_ROOTS", None)

    script = find_dashboard_script()
    proc = subprocess.Popen(
        [sys.executable, str(script), "--no-open", "--port", "0"],
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=0,
    )
    # Enter try IMMEDIATELY after successful Popen so ANY failure
    # after — including observer writes, queue construction,
    # threading.Thread.start(), or readiness parsing — reaches
    # the finalizer. A raise in an observer __setitem__ (a caller
    # can pass a dict subclass) must not leak the child.
    # Handles are None-initialized so the conditional cleanup at
    # the bottom knows which resources were actually created.
    stdout_q = stderr_q = None
    stdout_thread = stderr_thread = None
    try:
        if lifecycle_observer is not None:
            # Populate proc + stream handles FIRST so a raise
            # anywhere after this leaves a post-mortem trail. All
            # observer writes are INSIDE the try, so an exception
            # in observer.__setitem__ still triggers cleanup.
            lifecycle_observer["proc"] = proc
            lifecycle_observer["stdout"] = proc.stdout
            lifecycle_observer["stderr"] = proc.stderr
        stdout_q = queue.Queue()
        stderr_q = queue.Queue()
        stdout_thread = spawn_reader_thread(proc.stdout, stdout_q)
        if lifecycle_observer is not None:
            lifecycle_observer["stdout_thread"] = stdout_thread
        stderr_thread = spawn_reader_thread(proc.stderr, stderr_q)
        if lifecycle_observer is not None:
            lifecycle_observer["stderr_thread"] = stderr_thread
        url = read_ready_url(proc, stdout_q, stderr_q,
                             stdout_thread, stderr_thread,
                             timeout=45.0)
        yield {
            "url": url,
            "home": home,
            "server_pid": proc.pid,
            "repos": {
                "alpha": {"path": alpha["repo"],
                          "commits": alpha["commits"]},
                "beta": {"path": beta["repo"],
                         "commits": beta["commits"]},
            },
            "scratch_repo_count": len(scratch_entries),
            "scratch_entries": list(scratch_entries),
            "registry_pre_snapshot": (pre_hash, pre_meta),
        }
    finally:
        terminate_and_wait(proc)
        for t in (stdout_thread, stderr_thread):
            if t is not None:
                t.join(timeout=2.0)
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:
                pass
        post_hash, post_meta = snapshot_real_registry()
        assert post_hash == pre_hash, (
            "real dashboard-repos.json content changed during "
            "test session — harness isolation broken")
        assert post_meta == pre_meta, (
            f"real dashboard-repos.json file identity changed "
            f"during test session (pre={pre_meta}, post={post_meta}) "
            f"— content matched but mtime/inode drifted, indicating "
            f"a same-bytes rewrite or atomic replace")


# ── §5.2: Ready-protocol parser + finalizers ────────────────────


def read_ready_url(proc, stdout_q, stderr_q,
                   stdout_thread, stderr_thread, timeout):
    deadline = time.monotonic() + timeout
    stdout_lines = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(_terminate_then_finalize(
                proc, stdout_thread, stderr_thread, stderr_q,
                reason=(f"dashboard did not print `Ready on <url>` "
                        f"within {timeout}s"),
                stdout_lines=stdout_lines,
            ))
        try:
            line = stdout_q.get(timeout=min(0.5, remaining))
        except queue.Empty:
            if proc.poll() is not None:
                raise RuntimeError(_finalize_after_exit(
                    proc, stdout_thread, stderr_thread, stderr_q,
                    reason=(f"dashboard child exited early with code "
                            f"{proc.returncode}"),
                    stdout_lines=stdout_lines,
                ))
            continue
        if line is None:
            raise RuntimeError(_finalize_after_exit(
                proc, stdout_thread, stderr_thread, stderr_q,
                reason=None,
                stdout_lines=stdout_lines,
            ))
        stdout_lines.append(line)
        if line.startswith("Ready on "):
            return line[len("Ready on "):].strip()


def _finalize_after_exit(proc, stdout_thread, stderr_thread,
                         stderr_q, reason, stdout_lines,
                         grace=1.0):
    if proc.poll() is None:
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            terminate_reason = reason
            if terminate_reason is None:
                terminate_reason = (
                    f"stdout closed but child did not exit within "
                    f"{grace}s")
            return _terminate_then_finalize(
                proc, stdout_thread, stderr_thread, stderr_q,
                reason=terminate_reason,
                stdout_lines=stdout_lines,
            )
    if reason is None:
        reason = (f"dashboard child exited early with code "
                  f"{proc.returncode}")
    stdout_thread.join(timeout=1.0)
    stderr_thread.join(timeout=1.0)
    return ready_failure_msg(
        reason=reason,
        stdout_lines=stdout_lines,
        stderr_text=drain_queue(stderr_q),
    )


def _terminate_then_finalize(proc, stdout_thread, stderr_thread,
                             stderr_q, reason, stdout_lines):
    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
    stdout_thread.join(timeout=1.0)
    stderr_thread.join(timeout=1.0)
    return ready_failure_msg(
        reason=reason,
        stdout_lines=stdout_lines,
        stderr_text=drain_queue(stderr_q),
    )


def ready_failure_msg(reason, stdout_lines, stderr_text):
    return (f"{reason}\n"
            f"--- stdout ---\n{''.join(stdout_lines)}\n"
            f"--- stderr ---\n{stderr_text}")


def spawn_reader_thread(stream, q):
    def _pump():
        try:
            for line in iter(stream.readline, b""):
                q.put(line.decode("utf-8", errors="replace"))
        finally:
            q.put(None)
    t = threading.Thread(target=_pump, daemon=True)
    t.start()
    return t


def drain_queue(q):
    parts = []
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            break
        if item is None:
            break
        parts.append(item)
    return "".join(parts)


def terminate_and_wait(proc, timeout=5.0):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                pass


def find_dashboard_script():
    import gator_command
    pkg_dir = Path(gator_command.__file__).parent
    script = pkg_dir / "scripts" / "gator-dashboard.py"
    if not script.is_file():
        raise RuntimeError(
            f"gator-dashboard.py not found at {script}")
    return script


def snapshot_real_registry():
    """Opaque fingerprint of the real ~/.gator/dashboard-repos.json.
    Parent-side only. MUST NOT parse contents, MUST NOT write.
    """
    real = Path.home() / ".gator" / "dashboard-repos.json"
    if not real.is_file():
        return None, None
    data = real.read_bytes()
    st = real.stat()
    return hashlib.sha256(data).hexdigest(), (st.st_mtime, st.st_ino)


# ── §7: seed repo ────────────────────────────────────────────────


def seed_repo(fleet_root, name):
    repo = fleet_root / name
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")

    (repo / ".gator").mkdir()
    (repo / ".gator" / "mission.md").write_text(
        f"# {name} mission\n\nSeed body.\n", encoding="utf-8")

    # Extension seams for Plans B and C and the syntax-highlight
    # increment. All module-level no-op stubs (below); each
    # feature's seed module overrides them by reassigning
    # `_harness.seed_content_fixtures` / `seed_sidebar_fixtures` /
    # `seed_syntax_fixtures` when its fixtures load. Called BEFORE
    # the seed commit so any files each seed writes land in the
    # initial commit.
    seed_content_fixtures(repo)
    seed_sidebar_fixtures(repo)
    seed_syntax_fixtures(repo)

    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"seed {name}")
    commits = {"seed": _rev_parse_head(repo)}
    # B1 Slice 2 (v2.13.0) — post-seed hook for history commits.
    # Plan B's `content_transport_seed` module reassigns
    # `seed_history_commits` to add extra commits (e.g. a
    # `.gator/mission.md` overwrite so `?version=<sha>` has a
    # prior blob to serve). Returns a `{label: sha}` dict merged
    # into `commits` so tests can reference specific historical
    # SHAs by label.
    extra = seed_history_commits(repo, name) or {}
    commits.update(extra)
    return {"repo": repo, "commits": commits}


def seed_content_fixtures(repo):
    """No-op stub. Plan B (safe-content-transport) reassigns this
    in `_harness` to add files its pins need.
    """
    return None


def seed_history_commits(repo, name):
    """No-op stub. Plan B reassigns this in `_harness` to add
    post-seed commits (edits + deletions) so version-scoped
    endpoints have an inspectable git history.
    """
    return None


def seed_sidebar_fixtures(repo):
    """No-op stub. Plan C (responsive-shell-and-sidebar) reassigns
    this in `_harness` to add sidebar-overflow fixtures.
    """
    return None


def seed_syntax_fixtures(repo):
    """No-op stub. The read-only Python/SQL syntax-highlighting
    increment reassigns this in `_harness` from
    `test_syntax_highlight_seed.py` to add `source/` fixtures the
    tokenizer pins exercise.
    """
    return None


def _rev_parse_head(repo):
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, encoding="utf-8", check=True,
    )
    return out.stdout.strip()


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True)
