"""
Dashboard UI harness self-pins (Plan A, v2.13.0, §8).

These tests exercise the harness itself: isolation, Ready protocol,
debug seam, EOF/early-exit parser, process lifecycle, module loader.
"""

import queue
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ._harness import (
    drain_queue,
    find_dashboard_script,
    read_ready_url,
    ready_failure_msg,
    spawn_reader_thread,
    terminate_and_wait,
)


# ── §8.1: isolation + registry ────────────────────────────────────


def test_harness_registry_is_isolated_from_real_home(dashboard_fleet):
    """Parent-side write pin. The write-isolation assertion lives in
    `_build_dashboard_fleet`'s finally block (both hash AND
    (mtime, inode) checks); this test uses the fixture so the
    assertion runs at session teardown. The complementary
    read-isolation pin is `test_debug_registry_state_matches_seeded_fleet`.
    """
    assert dashboard_fleet["url"].startswith("http://127.0.0.1:")


# ── §8.2: port + Ready protocol ───────────────────────────────────


def test_harness_reports_serving_port_number_and_is_reachable(
    dashboard_fleet,
):
    url = dashboard_fleet["url"]
    assert re.fullmatch(r"http://127\.0\.0\.1:\d+/", url), url
    with urllib.request.urlopen(url, timeout=5) as r:
        assert r.status == 200
        assert r.headers.get_content_type() == "text/html"


def test_dashboard_repo_flag_prints_open_url_after_ready(tmp_path):
    """F4 pin: --no-open --repo NAME must still surface a
    repo-scoped URL. The public Ready line stays base_url; an
    indented `  Open: <base>/?repo=<name>` line follows.
    """
    home = tmp_path / "home"
    (home / ".gator").mkdir(parents=True)
    (home / ".gator" / "dashboard-repos.json").write_text(
        '{"schema": "gator-dashboard-registry-v1", "repos": []}',
        encoding="utf-8",
    )
    env = {**_clean_env(), "HOME": str(home), "USERPROFILE": str(home)}
    proc = subprocess.Popen(
        [sys.executable, str(find_dashboard_script()),
         "--no-open", "--port", "0", "--repo", "alpha"],
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
    )
    stdout_q = queue.Queue()
    stderr_q = queue.Queue()
    stdout_thread = spawn_reader_thread(proc.stdout, stdout_q)
    stderr_thread = spawn_reader_thread(proc.stderr, stderr_q)
    try:
        deadline = time.monotonic() + 45.0
        raw_lines = []
        ready_url = None
        open_line = None
        while time.monotonic() < deadline:
            try:
                line = stdout_q.get(timeout=0.5)
            except queue.Empty:
                if proc.poll() is not None:
                    raise RuntimeError(
                        f"child exited early with {proc.returncode}")
                continue
            if line is None:
                raise RuntimeError("child closed stdout early")
            raw_lines.append(line)
            if line.startswith("Ready on "):
                ready_url = line[len("Ready on "):].strip()
            if line.startswith("  Open: "):
                open_line = line[len("  Open: "):].strip()
                break
        assert ready_url is not None, f"no Ready line; stdout={raw_lines!r}"
        assert open_line is not None, f"no Open line; stdout={raw_lines!r}"
        m = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/", ready_url)
        assert m, ready_url
        # Open line MUST carry the repo query on the same host+port.
        expected = f"http://127.0.0.1:{m.group(1)}/?repo=alpha"
        assert open_line == expected, (open_line, expected)
    finally:
        terminate_and_wait(proc)
        stdout_thread.join(timeout=2.0)
        stderr_thread.join(timeout=2.0)
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:
                pass


def test_dashboard_port_zero_prints_reachable_ready_url(tmp_path):
    """Regression pin for --port 0 → server_address[1] → column-0
    Ready line → reachable chain (including the trailing-slash
    contract).
    """
    home = tmp_path / "home"
    (home / ".gator").mkdir(parents=True)
    (home / ".gator" / "dashboard-repos.json").write_text(
        '{"schema": "gator-dashboard-registry-v1", "repos": []}',
        encoding="utf-8",
    )
    env = {
        **_clean_env(),
        "HOME": str(home),
        "USERPROFILE": str(home),
    }
    proc = subprocess.Popen(
        [sys.executable, str(find_dashboard_script()),
         "--no-open", "--port", "0"],
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=0,
    )
    stdout_q = queue.Queue()
    stderr_q = queue.Queue()
    stdout_thread = spawn_reader_thread(proc.stdout, stdout_q)
    stderr_thread = spawn_reader_thread(proc.stderr, stderr_q)
    raw_lines = []
    try:
        # Collect raw stdout until we see the Ready line.
        deadline = time.monotonic() + 45.0
        url = None
        while time.monotonic() < deadline:
            try:
                line = stdout_q.get(timeout=0.5)
            except queue.Empty:
                if proc.poll() is not None:
                    raise RuntimeError(
                        f"child exited early with {proc.returncode}; "
                        f"stdout={raw_lines!r}")
                continue
            if line is None:
                raise RuntimeError(
                    f"child closed stdout early; stdout={raw_lines!r}")
            raw_lines.append(line)
            if line.startswith("Ready on "):
                # (a) raw-stdout regex — accept \r?\n so Windows
                # CRLF-terminated stdout also passes; the column-0 +
                # 127.0.0.1 + trailing-slash contract is the pin.
                assert re.fullmatch(
                    r"Ready on http://127\.0\.0\.1:\d+/\r?\n",
                    line), repr(line)
                url = line[len("Ready on "):].strip()
                break
        assert url is not None, f"Ready never emitted; stdout={raw_lines!r}"
        # (b) parsed URL regex — trailing slash required
        m = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/", url)
        assert m, url
        assert int(m.group(1)) > 0
        # (c) HTTP GET → 200 text/html
        with urllib.request.urlopen(url, timeout=5) as r:
            assert r.status == 200
            assert r.headers.get_content_type() == "text/html"
    finally:
        terminate_and_wait(proc)
        stdout_thread.join(timeout=2.0)
        stderr_thread.join(timeout=2.0)
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:
                pass


# ── §8.3: debug seam ──────────────────────────────────────────────


def test_debug_seam_present_when_env_var_set(gator_page_readonly):
    typ = gator_page_readonly.evaluate(
        "typeof window.__gator_debug")
    assert typ == "object"


def test_debug_seam_absent_when_env_var_unset(page,
                                              dashboard_fleet_debug_off):
    page.goto(dashboard_fleet_debug_off["url"])
    typ = page.evaluate("typeof window.__gator_debug")
    assert typ == "undefined"
    # Belt + suspenders: the meta tag must not be in the served HTML.
    with urllib.request.urlopen(dashboard_fleet_debug_off["url"],
                                timeout=5) as r:
        body = r.read().decode("utf-8")
    assert 'meta name="gator-debug"' not in body


def test_debug_seam_getters_return_snapshots_not_live_refs(
    page, dashboard_fleet,
):
    """F2: pin BOTH (a) the getter reflects real `_treeState` and
    (b) mutating a returned snapshot doesn't affect subsequent
    calls. A constant-returning stub would pass (b) alone; (a)
    catches that failure mode.
    """
    # Navigate directly into the Repo view for `alpha` — the
    # `?repo=<name>` route pre-loads it and populates `_treeState`
    # via `resetTreeStateFor(repoName)` in repo.js.
    page.goto(dashboard_fleet["url"] + "?repo=alpha")

    # Wait for the sidebar-driven state to actually populate.
    # `_treeState.repoName` becomes "alpha" as part of the repo
    # view load; then a file gets selected (defaultFile or the
    # persisted selection) which sets `_treeState.selectedFile`.
    page.wait_for_function(
        "() => window.__gator_debug"
        " && window.__gator_debug.sidebar.repoName === 'alpha'"
        " && window.__gator_debug.sidebar.expandedDirs.length > 0",
        timeout=15000,
    )

    result = page.evaluate("""() => {
        const first = window.__gator_debug.sidebar;
        // (a) getter reflects real state: repoName is the loaded
        // repo, expandedDirs is populated (at minimum the default
        // 'section:gator' entry after resetTreeStateFor).
        const reflectsRealState = (
            first.repoName === 'alpha'
            && Array.isArray(first.expandedDirs)
            && first.expandedDirs.length > 0
        );
        // (b) mutating the returned snapshot does not affect the
        // next getter call — the getter must build a fresh
        // snapshot per call, not hand back a live reference.
        first.expandedDirs.push('spoofed:injection');
        first.repoName = 'spoofed';
        const second = window.__gator_debug.sidebar;
        const snapshotIsolated = (
            second.repoName === 'alpha'
            && !second.expandedDirs.includes('spoofed:injection')
        );
        return { reflectsRealState, snapshotIsolated,
                 firstExpanded: first.expandedDirs,
                 secondRepoName: second.repoName };
    }""")
    assert result["reflectsRealState"], (
        f"getter does not reflect real _treeState: {result!r}")
    assert result["snapshotIsolated"], (
        f"getter returned a mutable live reference — expected a "
        f"fresh snapshot on the second call: {result!r}")


def test_debug_registry_state_matches_seeded_fleet(dashboard_fleet):
    with urllib.request.urlopen(
        dashboard_fleet["url"] + "api/__gator_debug/registry_state",
        timeout=5,
    ) as r:
        assert r.status == 200
        payload = _read_json(r)
    expected = {
        ("alpha", str(dashboard_fleet["repos"]["alpha"]["path"])),
        ("beta", str(dashboard_fleet["repos"]["beta"]["path"])),
    }
    for entry in dashboard_fleet["scratch_entries"]:
        expected.add((entry["name"], entry["path"]))
    got = {(r["name"], r["path"]) for r in payload["registry_repos"]}
    assert got == expected, f"registry drift: only-in-got={got-expected}, only-in-expected={expected-got}"
    assert payload["count"] == len(expected)


def test_debug_registry_endpoint_404_when_debug_off(
    dashboard_fleet_debug_off,
):
    url = (dashboard_fleet_debug_off["url"]
           + "api/__gator_debug/registry_state")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(url, timeout=5)
    assert excinfo.value.code == 404


def test_dashboard_data_endpoint_lists_only_seeded_repos(
    dashboard_fleet,
):
    with urllib.request.urlopen(
        dashboard_fleet["url"] + "api/data", timeout=15,
    ) as r:
        assert r.status == 200
        payload = _read_json(r)
    repos = _extract_fleet_repos(payload)
    accessible = [r for r in repos if r.get("accessible", True)]
    accessible_names = {r.get("name") for r in accessible}
    assert accessible_names == {"alpha", "beta"}, accessible_names
    by_name = {r.get("name"): r for r in accessible}
    for name in ("alpha", "beta"):
        assert Path(by_name[name].get("path")).resolve() \
            == dashboard_fleet["repos"][name]["path"].resolve()


# ── §8.4: EOF / early-exit parser (in-process, deterministic) ────


class _FakeProc:
    """Minimal `Popen`-shaped stub for parser unit tests. Does not
    spawn a process; behaviors are prescriptive.
    """
    def __init__(self, *, returncode_on_wait=None,
                 wait_raises=False):
        self.returncode = None
        self._wait_result = returncode_on_wait
        self._wait_raises = wait_raises
        self.calls = []
        self.stdout = None
        self.stderr = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.calls.append(("wait", timeout))
        if self._wait_raises:
            raise subprocess.TimeoutExpired(cmd="fake",
                                            timeout=timeout)
        self.returncode = self._wait_result
        return self._wait_result

    def terminate(self):
        self.calls.append(("terminate", None))
        raise AssertionError("terminate must not be called on the "
                             "EOF-before-poll path")

    def kill(self):
        self.calls.append(("kill", None))


class _DummyThread:
    def join(self, timeout=None):
        return None


def test_ready_url_parser_reports_returncode_on_eof_before_poll():
    proc = _FakeProc(returncode_on_wait=2)
    stdout_q = queue.Queue()
    stderr_q = queue.Queue()
    stdout_q.put(None)  # EOF sentinel
    stderr_q.put("boom: config error\n")
    stderr_q.put(None)
    with pytest.raises(RuntimeError) as excinfo:
        read_ready_url(proc, stdout_q, stderr_q,
                        _DummyThread(), _DummyThread(), timeout=1.0)
    msg = str(excinfo.value)
    assert "exited early with code 2" in msg
    assert "boom: config error" in msg
    assert proc.returncode == 2


def test_ready_url_parser_supplies_fallback_reason_when_child_wont_exit_after_eof():
    proc = _FakeProc(wait_raises=True)

    # Rebind `terminate`/`kill` to plain no-op recorders — this
    # scenario legitimately terminates after wait raises.
    proc.calls = []

    def _terminate():
        proc.calls.append(("terminate", None))

    def _kill():
        proc.calls.append(("kill", None))
        proc.returncode = -9

    proc.terminate = _terminate
    proc.kill = _kill

    stdout_q = queue.Queue()
    stderr_q = queue.Queue()
    stdout_q.put(None)
    stderr_q.put(None)
    with pytest.raises(RuntimeError) as excinfo:
        read_ready_url(proc, stdout_q, stderr_q,
                        _DummyThread(), _DummyThread(), timeout=1.0)
    msg = str(excinfo.value)
    assert "stdout closed but child did not exit within" in msg
    assert "None" not in msg.splitlines()[0], msg


def test_ready_url_parser_fails_loudly_on_live_silent_child(tmp_path):
    """Real subprocess: sleeps 60s without writing stdout, prints
    to stderr once. Parser must raise RuntimeError within a bounded
    time and include both the "did not print" reason and the
    stderr text.
    """
    child_script = tmp_path / "silent_child.py"
    child_script.write_text(
        "import sys, time\n"
        "sys.stderr.write('warming up\\n')\n"
        "sys.stderr.flush()\n"
        "time.sleep(60)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, str(child_script)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
    )
    stdout_q = queue.Queue()
    stderr_q = queue.Queue()
    stdout_thread = spawn_reader_thread(proc.stdout, stdout_q)
    stderr_thread = spawn_reader_thread(proc.stderr, stderr_q)
    started = time.monotonic()
    try:
        with pytest.raises(RuntimeError) as excinfo:
            read_ready_url(proc, stdout_q, stderr_q,
                            stdout_thread, stderr_thread,
                            timeout=1.0)
    finally:
        terminate_and_wait(proc)
        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:
                pass
    elapsed = time.monotonic() - started
    assert elapsed < 5.0, elapsed
    msg = str(excinfo.value)
    assert "did not print" in msg
    assert "warming up" in msg


@pytest.mark.slow
def test_ready_url_parser_smoke_real_child_early_exit(tmp_path):
    """Real subprocess smoke: stdout.close() + sleep(0.3) + exit(2).
    Timing can hit either the EOF-sentinel branch or the queue-empty
    poll branch; both are acceptable. Wall-clock coverage that the
    deterministic pins do not provide.
    """
    child_script = tmp_path / "early_exit_child.py"
    child_script.write_text(
        "import sys, time\n"
        "sys.stdout.close()\n"
        "time.sleep(0.3)\n"
        "sys.exit(2)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, str(child_script)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
    )
    stdout_q = queue.Queue()
    stderr_q = queue.Queue()
    stdout_thread = spawn_reader_thread(proc.stdout, stdout_q)
    stderr_thread = spawn_reader_thread(proc.stderr, stderr_q)
    try:
        with pytest.raises(RuntimeError) as excinfo:
            read_ready_url(proc, stdout_q, stderr_q,
                            stdout_thread, stderr_thread,
                            timeout=5.0)
    finally:
        terminate_and_wait(proc)
        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:
                pass
    msg = str(excinfo.value)
    assert ("exited early" in msg) or ("stdout closed" in msg), msg


def test_ready_failure_msg_drains_stderr_exactly_once():
    q = queue.Queue()
    q.put("line1\n")
    q.put("line2\n")
    q.put(None)
    first = drain_queue(q)
    second = drain_queue(q)
    assert first == "line1\nline2\n"
    assert second == ""


# ── §8.5: process lifecycle ──────────────────────────────────────


class _FakeProcEscalation:
    """FakeProc for the escalation pin. Records call order.
    poll() returns None until kill() is called, then returns -9.
    First wait raises TimeoutExpired; second wait sets returncode
    and returns it.
    """
    def __init__(self):
        self.returncode = None
        self.call_order = []
        self._wait_count = 0
        self._killed = False
        self.stdout = None
        self.stderr = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.call_order.append("terminate")

    def kill(self):
        self.call_order.append("kill")
        self._killed = True

    def wait(self, timeout=None):
        self.call_order.append("wait")
        self._wait_count += 1
        if self._wait_count == 1:
            raise subprocess.TimeoutExpired(cmd="fake",
                                            timeout=timeout)
        if self._killed:
            self.returncode = -9
        return self.returncode


def test_terminate_and_wait_escalates_to_kill_when_wait_times_out():
    proc = _FakeProcEscalation()
    terminate_and_wait(proc, timeout=0.1)
    assert proc.call_order == ["terminate", "wait", "kill", "wait"]
    assert proc.returncode == -9


@pytest.mark.slow
@pytest.mark.skipif(sys.platform == "win32",
                    reason=("Popen.terminate is forceful on Windows; "
                            "busy loop does not model survive-terminate"))
def test_terminate_and_wait_reaps_real_child_smoke(tmp_path):
    """Real-child smoke: POSIX-only, readiness sentinel closes the
    handler-install race. Bounded readiness wait + full try/finally
    cleanup even if readiness times out or an assertion fails.
    """
    child_script = tmp_path / "ignore_sigterm_child.py"
    child_script.write_text(
        "import signal, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "sys.stdout.write('ready\\n')\n"
        "sys.stdout.flush()\n"
        "while True:\n"
        "    signal.pause()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, str(child_script)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
    )
    stdout_q = queue.Queue()
    stderr_q = queue.Queue()
    stdout_thread = spawn_reader_thread(proc.stdout, stdout_q)
    stderr_thread = spawn_reader_thread(proc.stderr, stderr_q)
    try:
        deadline = time.monotonic() + 5.0
        seen_ready = False
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                line = stdout_q.get(timeout=min(0.5, remaining))
            except queue.Empty:
                if proc.poll() is not None:
                    raise RuntimeError(ready_failure_msg(
                        reason=(f"child exited without readiness; "
                                f"returncode={proc.returncode}"),
                        stdout_lines=[],
                        stderr_text=drain_queue(stderr_q),
                    ))
                continue
            if line is None:
                raise RuntimeError(ready_failure_msg(
                    reason="child closed stdout before readiness",
                    stdout_lines=[],
                    stderr_text=drain_queue(stderr_q),
                ))
            if line.startswith("ready"):
                seen_ready = True
                break
        assert seen_ready, "child never printed readiness sentinel"
        terminate_and_wait(proc, timeout=0.5)
        assert proc.poll() is not None
    finally:
        terminate_and_wait(proc)
        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:
                pass


def test_direct_script_launch_owns_server_process(dashboard_fleet):
    psutil = pytest.importorskip("psutil")
    parent = psutil.Process(dashboard_fleet["server_pid"])
    children = parent.children(recursive=True)
    assert children == [], f"unexpected grandchildren: {children}"


def test_fixture_teardown_joins_reader_threads_and_closes_pipes(
    dashboard_fleet_lifecycle_probe,
):
    fleet, _observer = dashboard_fleet_lifecycle_probe
    with urllib.request.urlopen(fleet["url"], timeout=5) as r:
        assert r.status == 200
    # Assertions on thread exit + pipe closure run in the fixture's
    # teardown (see conftest.py::dashboard_fleet_lifecycle_probe).


def test_builder_reaps_child_when_reader_thread_start_raises(
    tmp_path_factory, monkeypatch,
):
    """F1 pin: post-Popen setup failure must still reap the child,
    close both pipes, and settle any thread that had started
    before the failure. Uses the `lifecycle_observer` seam that
    `build_dashboard_fleet` populates INCREMENTALLY — proc + both
    streams populated immediately after Popen, first reader thread
    populated after its start returns. The observer is the
    authoritative post-mortem surface.
    """
    from . import _harness as h

    real_spawn = h.spawn_reader_thread
    call_count = {"n": 0}

    def flaky_spawn(stream, q):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return real_spawn(stream, q)
        raise RuntimeError("simulated second-thread start failure")

    monkeypatch.setattr(h, "spawn_reader_thread", flaky_spawn)

    observer = {}
    with pytest.raises(RuntimeError,
                       match="simulated second-thread start failure"):
        gen = h.build_dashboard_fleet(
            tmp_path_factory, extra_registry_size=0, debug=False,
            lifecycle_observer=observer)
        next(gen)  # drives startup — raise propagates through finally

    # Observer must have captured proc + streams immediately after
    # Popen, and the first thread after its start succeeded. The
    # second thread was never created (spawn raised); the key is
    # absent, not None.
    assert observer.get("proc") is not None, (
        "observer missing `proc` — should be populated immediately "
        "after Popen so tests can post-mortem startup failures")
    assert observer.get("stdout") is not None
    assert observer.get("stderr") is not None
    assert observer.get("stdout_thread") is not None, (
        "observer missing `stdout_thread` — first spawn succeeded "
        "and should have populated this before the second raised")
    assert "stderr_thread" not in observer, (
        "observer has `stderr_thread` — second spawn raised so this "
        "key must not appear; incremental population contract broken")

    proc = observer["proc"]
    stdout = observer["stdout"]
    stderr = observer["stderr"]
    first_thread = observer["stdout_thread"]

    # Give the reaped child + first reader thread a moment to
    # settle (terminate_and_wait already waited on proc.wait; the
    # reader thread joins on EOF from the closed pipe, which is
    # immediate once the process is reaped).
    first_thread.join(timeout=2.0)

    # (1) Child was reaped — proc.returncode set (not None).
    assert proc.returncode is not None, (
        f"child not reaped after setup failure: poll={proc.poll()}")
    # (2) Both pipes were closed by the finalizer.
    assert stdout.closed is True, (
        "proc.stdout leaked open after setup failure")
    assert stderr.closed is True, (
        "proc.stderr leaked open after setup failure")
    # (3) The first reader thread settled.
    assert first_thread.is_alive() is False, (
        "first reader thread leaked after setup failure")


def test_builder_reaps_child_when_observer_setitem_raises(
    tmp_path_factory,
):
    """F1 companion pin: even a raise in the observer's own
    __setitem__ must not leak the child. The `try/finally` MUST
    enclose the first observer write — any earlier startup step
    is outside the ownership contract.

    Uses a dict subclass that raises AFTER the `proc` key is
    stored so the test can still inspect the reaped child.
    """
    from . import _harness as h

    class RaisingObserver(dict):
        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            # Raise AFTER retaining the value so post-mortem still
            # sees `proc`. Skip the first raise so `proc` lands;
            # raise on the next write (stdout).
            if key == "stdout":
                raise RuntimeError(
                    "simulated observer __setitem__ failure")

    observer = RaisingObserver()
    with pytest.raises(RuntimeError,
                       match="simulated observer __setitem__ failure"):
        gen = h.build_dashboard_fleet(
            tmp_path_factory, extra_registry_size=0, debug=False,
            lifecycle_observer=observer)
        next(gen)

    proc = observer.get("proc")
    assert proc is not None, (
        "observer.__setitem__ raised BEFORE `proc` was captured — "
        "the try/finally must enclose the first observer write")
    # The `stdout` key WAS stored (raise happens after super() write)
    # so we can also introspect it.
    stdout = observer.get("stdout")
    stderr = observer.get("stderr")
    assert stdout is not None
    assert stderr is None, (
        "observer must have raised on the `stdout` write before "
        "reaching `stderr` — otherwise this pin is testing the "
        "wrong scenario")

    # Child was reaped and both proc-owned pipes closed by the
    # finalizer, even though the raise happened during the first
    # observer write (before queues/threads/readiness).
    assert proc.returncode is not None, (
        f"child not reaped when observer __setitem__ raised: "
        f"poll={proc.poll()}")
    assert stdout.closed is True, (
        "proc.stdout leaked open when observer __setitem__ raised")
    # `stderr` handle from proc itself (not via observer) — fetch
    # from proc directly because the observer never captured it.
    assert proc.stderr.closed is True, (
        "proc.stderr leaked open when observer __setitem__ raised")


# ── §8.6: module loader ──────────────────────────────────────────


def test_dashboard_module_fixture_provides_importable_object(
    dashboard_module,
):
    import sys as _sys
    import subprocess as _subprocess
    assert dashboard_module.__name__ == "gator_dashboard_test"
    assert _sys.modules["gator_dashboard_test"] is dashboard_module
    assert callable(dashboard_module.main)
    assert callable(dashboard_module.DashboardHandler)
    assert dashboard_module.subprocess is _subprocess


# ── helpers ──────────────────────────────────────────────────────


def _clean_env():
    env = {**__import__("os").environ}
    env.pop("GATOR_DASHBOARD_DEBUG", None)
    env.pop("GATOR_DASHBOARD_DISCOVERY_ROOTS", None)
    return env


def _read_json(response):
    import json
    return json.loads(response.read().decode("utf-8"))


def _extract_fleet_repos(payload):
    """Walk the /api/data payload for the fleet-row list. Shape may
    have evolved across dashboard versions; try a few candidate
    keys and fall back to searching for a list of dicts with `name`.
    """
    if isinstance(payload, dict):
        for key in ("repos", "fleet", "rows"):
            v = payload.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        for v in payload.values():
            if isinstance(v, dict):
                for key in ("repos", "fleet", "rows"):
                    inner = v.get(key)
                    if isinstance(inner, list) and inner \
                            and isinstance(inner[0], dict):
                        return inner
    return []
