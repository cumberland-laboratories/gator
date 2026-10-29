"""
Concurrency tests for the Dashboard's shared state (threaded-server plan).

Each test serves the real DashboardHandler from a test-local
ThreadingHTTPServer, so handlers run concurrently even while the
production server is still single-request. Isolation seams:
gator_core.DASHBOARD_REGISTRY, the module-level _REGISTRY_REPOS, and
DashboardHandler.fast_data. Every wait is bounded; failures report the
live thread names and the unexpected outcomes.
"""

import errno
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from conftest import load_script

import gator_core

dashboard = load_script("gator-dashboard")

TIMEOUT = 10


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_repo(root, name, marker):
    """A minimal browsable repo: `.git/` plus `.gator/artifacts/<marker>.md`."""
    repo = root / name
    (repo / ".git").mkdir(parents=True)
    artifacts = repo / ".gator" / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / f"{marker}.md").write_text(f"# {marker}\n", encoding="utf-8")
    return str(repo.resolve())


def _request(url, path, body=None, timeout=TIMEOUT):
    """GET (body None) or authenticated POST. Returns (status, text)."""
    status, text, _ = _request_full(url, path, body, timeout)
    return status, text


def _request_full(url, path, body=None, timeout=TIMEOUT):
    """Like _request, also returning the response headers."""
    if body is None:
        req = Request(url + path)
    else:
        req = Request(url + path, data=json.dumps(body).encode("utf-8"),
                      method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Gator-Dashboard", "1")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8"), resp.headers
    except HTTPError as e:
        return (e.code, e.read().decode("utf-8", errors="replace"),
                e.headers)


def _diagnostics(problems):
    names = sorted(t.name for t in threading.enumerate())
    return f"{len(problems)} problem(s): {problems[:10]}; threads: {names}"


def _repo_key(path):
    agg = dashboard.import_sibling("gator-session-aggregator")
    return agg.session_cache_key(path)


@pytest.fixture
def threaded(monkeypatch, tmp_path):
    """Start a threaded server over a seeded registry.

    `start(records)` seeds the registry file, the published registry and
    a Fleet object, then serves; returns the base URL.
    """
    registry_file = tmp_path / "home" / "dashboard-repos.json"
    monkeypatch.setattr(gator_core, "DASHBOARD_REGISTRY", registry_file)
    saved_fleet = dashboard.DashboardHandler.fast_data
    state = {}

    def start(records, production=False, **server_kw):
        """production=True serves with the real DashboardHTTPServer
        (bounded admission); otherwise a plain ThreadingHTTPServer."""
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        registry_file.write_text(json.dumps({
            "schema": "gator-dashboard-registry-v1",
            "repos": records,
        }, indent=2), encoding="utf-8")
        monkeypatch.setattr(dashboard, "_REGISTRY_REPOS", list(records))
        dashboard.DashboardHandler.fast_data = {
            "generated_at": "seed",
            "repos": [{"name": r["name"], "path": r["path"]} for r in records],
        }
        if production:
            httpd = dashboard.DashboardHTTPServer(
                ("127.0.0.1", 0), dashboard.DashboardHandler, **server_kw)
        else:
            httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                        dashboard.DashboardHandler)
            httpd.daemon_threads = True
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        state["httpd"], state["thread"] = httpd, thread
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    start.registry_file = registry_file
    yield start
    if "httpd" in state:
        state["httpd"].shutdown()
        state["httpd"].server_close()
        state["thread"].join(timeout=5)
    dashboard.DashboardHandler.fast_data = saved_fleet


# ── pin 4: reads stay coherent while the registry changes ─────────────────────


class TestReadCoherenceUnderRegistryChange:

    def test_reads_keep_repo_identity_while_registry_changes(
            self, threaded, tmp_path):
        a = _make_repo(tmp_path, "alpha", "marker-alpha")
        b = _make_repo(tmp_path, "beta", "marker-beta")
        churn = [_make_repo(tmp_path, f"churn{i}", f"marker-churn{i}")
                 for i in range(4)]
        url = threaded([{"name": "alpha", "path": a},
                        {"name": "beta", "path": b}])
        key_a, key_b = _repo_key(a), _repo_key(b)
        stop = threading.Event()
        problems = []

        def churner():
            while not stop.is_set():
                for p in churn:
                    s, t = _request(url, "/api/repos/register", {"path": p})
                    if s not in (200, 409):
                        problems.append(("register", s, t[:200]))
                for p in churn:
                    s, t = _request(url, "/api/repos/remove", {"path": p})
                    if s not in (200, 404):
                        problems.append(("remove", s, t[:200]))

        def reader(i):
            name, own, other = (("alpha", "marker-alpha", "marker-beta")
                                if i % 2 == 0 else
                                ("beta", "marker-beta", "marker-alpha"))
            key = key_a if i % 2 == 0 else key_b
            for path in (f"/api/repo/{name}/files",
                         f"/api/repo-by-key/{key}/sketch-sources"):
                s, t = _request(url, path)
                if s != 200 or own not in t or other in t:
                    problems.append((path, s, t[:200]))
            s, t = _request(url, "/api/data")
            try:
                data = json.loads(t)
                ok = s == 200 and isinstance(data.get("repos"), list) and all(
                    isinstance(r, dict) and "name" in r and "path" in r
                    for r in data["repos"])
            except ValueError:
                ok = False
            if not ok:
                problems.append(("/api/data", s, t[:200]))

        churn_thread = threading.Thread(target=churner, name="churner",
                                        daemon=True)
        churn_thread.start()
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(reader, range(80), timeout=60))
        finally:
            stop.set()
            churn_thread.join(timeout=TIMEOUT)
        assert not problems, _diagnostics(problems)

        # The two seeded repos survived every churn cycle.
        paths = {r["path"] for r in dashboard._registry_snapshot()}
        assert {a, b} <= paths

    def test_duplicate_display_names_never_cross_repositories(
            self, threaded, tmp_path):
        first = _make_repo(tmp_path / "one", "dup", "marker-first")
        second = _make_repo(tmp_path / "two", "dup", "marker-second")
        url = threaded([{"name": "dup", "path": first},
                        {"name": "dup", "path": second}])
        key_first, key_second = _repo_key(first), _repo_key(second)
        assert key_first != key_second
        problems = []

        def check(i):
            # Name routes keep resolving the first registered match.
            s, t = _request(url, "/api/repo/dup/files")
            if s != 200 or "marker-first" not in t or "marker-second" in t:
                problems.append(("name", s, t[:200]))
            # Key routes are exact.
            key, own, other = ((key_first, "marker-first", "marker-second")
                               if i % 2 == 0 else
                               (key_second, "marker-second", "marker-first"))
            s, t = _request(url, f"/api/repo-by-key/{quote(key)}/sketch-sources")
            if s != 200 or own not in t or other in t:
                problems.append(("key", s, t[:200]))

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(check, range(40), timeout=60))
        assert not problems, _diagnostics(problems)

    def test_remove_publishes_new_values_never_mutates_old(
            self, threaded, tmp_path):
        a = _make_repo(tmp_path, "alpha", "marker-alpha")
        b = _make_repo(tmp_path, "beta", "marker-beta")
        url = threaded([{"name": "alpha", "path": a},
                        {"name": "beta", "path": b}])
        old_registry = dashboard._registry_snapshot()
        old_fleet = dashboard._fleet_snapshot()
        old_fleet_repos = list(old_fleet["repos"])

        s, _ = _request(url, "/api/repos/remove", {"path": a})
        assert s == 200

        # The values a concurrent reader may still hold are unchanged.
        assert [r["path"] for r in old_registry] == [a, b]
        assert old_fleet["repos"] == old_fleet_repos
        # The published values no longer contain the removed repo.
        assert [r["path"] for r in dashboard._registry_snapshot()] == [b]
        assert [r["path"] for r in dashboard._fleet_snapshot()["repos"]] == [b]


# ── pin 4c: registry writers for different paths never lose an update ─────────


class TestRegistryWriters:

    def test_concurrent_registers_for_different_paths_all_persist(
            self, threaded, tmp_path):
        url = threaded([])
        paths = [_make_repo(tmp_path, f"repo{i}", f"marker-{i}")
                 for i in range(12)]
        barrier = threading.Barrier(len(paths), timeout=TIMEOUT)

        def register(p):
            barrier.wait()
            return _request(url, "/api/repos/register", {"path": p})

        with ThreadPoolExecutor(max_workers=len(paths)) as pool:
            results = list(pool.map(register, paths, timeout=60))
        problems = [(p, s, t[:200]) for p, (s, t) in zip(paths, results)
                    if s != 200]
        assert not problems, _diagnostics(problems)

        persisted = json.loads(
            threaded.registry_file.read_text(encoding="utf-8"))["repos"]
        assert sorted(str(Path(r["path"]).resolve()) for r in persisted) \
            == sorted(paths)
        assert sorted(r["path"] for r in dashboard._registry_snapshot()) \
            == sorted(paths)

    def test_registry_responses_are_sent_outside_the_writer_lock(
            self, threaded, tmp_path, monkeypatch):
        """Every register/remove outcome, success or rejection, is written
        after _STATE_WRITE_LOCK is released; the durable update stays
        serialized."""
        existing = _make_repo(tmp_path, "existing", "marker-existing")
        fresh = _make_repo(tmp_path, "fresh", "marker-fresh")
        failing = _make_repo(tmp_path, "failing", "marker-failing")
        url = threaded([{"name": "existing", "path": existing}])
        held = []
        original_send = dashboard.DashboardHandler._send_json

        def recording_send(handler, data, status=200, **kw):
            if handler.path.startswith("/api/repos/"):
                held.append((handler.path, status,
                             dashboard._STATE_WRITE_LOCK.locked()))
            return original_send(handler, data, status, **kw)

        monkeypatch.setattr(dashboard.DashboardHandler, "_send_json",
                            recording_send)
        original_ensure = gator_core.ensure_dashboard_registry_entry

        def ensure(path, source="gator-init"):
            if str(Path(path).resolve()) == failing:
                return {"status": "error", "detail": "simulated failure"}
            return original_ensure(path, source=source)

        monkeypatch.setattr(gator_core, "ensure_dashboard_registry_entry",
                            ensure)

        cases = [
            ("/api/repos/register", existing, 409),   # already registered
            ("/api/repos/register", failing, 500),    # registry write failed
            ("/api/repos/register", fresh, 200),      # added
            ("/api/repos/remove", str(tmp_path / "absent"), 404),
            ("/api/repos/remove", fresh, 200),
        ]
        for path, repo, expected in cases:
            status, text = _request(url, path, {"path": repo})
            assert status == expected, (path, repo, status, text[:200])

        assert [(p, s) for p, s, _ in held] == [(p, e) for p, _, e in cases]
        locked = [(p, s) for p, s, was_locked in held if was_locked]
        assert not locked, f"responses sent under _STATE_WRITE_LOCK: {locked}"
        assert [r["path"] for r in dashboard._registry_snapshot()] == [existing]

    def test_concurrent_register_and_remove_for_different_paths(
            self, threaded, tmp_path):
        keep = [_make_repo(tmp_path, f"keep{i}", f"marker-keep{i}")
                for i in range(6)]
        add = [_make_repo(tmp_path, f"add{i}", f"marker-add{i}")
               for i in range(6)]
        url = threaded([{"name": Path(p).name, "path": p} for p in keep])
        jobs = ([("/api/repos/register", p) for p in add]
                + [("/api/repos/remove", p) for p in keep[:3]])
        barrier = threading.Barrier(len(jobs), timeout=TIMEOUT)

        def run(job):
            barrier.wait()
            return _request(url, job[0], {"path": job[1]})

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            results = list(pool.map(run, jobs, timeout=60))
        problems = [(j, s, t[:200]) for j, (s, t) in zip(jobs, results)
                    if s != 200]
        assert not problems, _diagnostics(problems)

        expected = sorted(keep[3:] + add)
        persisted = json.loads(
            threaded.registry_file.read_text(encoding="utf-8"))["repos"]
        assert sorted(str(Path(r["path"]).resolve()) for r in persisted) \
            == expected
        assert sorted(r["path"] for r in dashboard._registry_snapshot()) \
            == expected
        fleet_paths = {r["path"] for r in dashboard._fleet_snapshot()["repos"]}
        assert not fleet_paths & set(keep[:3])


# ── checkpoint 2 helpers ──────────────────────────────────────────────────────


dashboard_data = sys.modules["dashboard.data"]


class Gate:
    """A test-controlled hold point: `enter()` blocks until `release()`."""

    def __init__(self):
        self.entered = threading.Event()
        self._released = threading.Event()
        self.calls = 0

    def enter(self):
        self.calls += 1
        self.entered.set()
        assert self._released.wait(TIMEOUT), "gate was never released"

    def release(self):
        self._released.set()


def _in_thread(fn, *args):
    """Run fn(*args) on a thread; return a callable that joins and returns."""
    out = {}

    def run():
        out["value"] = fn(*args)

    t = threading.Thread(target=run, daemon=True)
    t.start()

    def result():
        t.join(TIMEOUT)
        assert not t.is_alive(), _diagnostics(["request thread did not finish"])
        return out["value"]

    return result


def _wait_until(predicate, what):
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(_diagnostics([f"timed out waiting for {what}"]))


def _refresh_idle():
    return not dashboard.DashboardHandler._refresh_lock.locked()


# ── pin 3: refresh is single-flight and reconciles with removals ───────────────


class TestRefreshSingleFlight:

    def test_concurrent_refreshes_admit_one_collection(
            self, threaded, tmp_path, monkeypatch):
        a = _make_repo(tmp_path, "alpha", "marker-alpha")
        url = threaded([{"name": "alpha", "path": a}])
        gate = Gate()

        def collect(registry):
            gate.enter()
            return {"generated_at": "new",
                    "repos": [{"name": r["name"], "path": r["path"]}
                              for r in registry]}

        monkeypatch.setattr(dashboard, "collect_standalone_data", collect)
        barrier = threading.Barrier(10, timeout=TIMEOUT)

        def refresh(_):
            barrier.wait()
            return _request(url, "/api/refresh")

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(refresh, range(10), timeout=60))
        statuses = sorted(json.loads(t)["status"] for _, t in results)
        assert statuses == ["already_refreshing"] * 9 + ["refreshing"], statuses
        assert gate.entered.wait(TIMEOUT)

        # While the collection runs, readers see the whole old object.
        s, t = _request(url, "/api/data")
        assert s == 200 and json.loads(t)["generated_at"] == "seed"
        assert json.loads(_request(url, "/api/refresh")[1])["status"] \
            == "already_refreshing"

        gate.release()
        _wait_until(_refresh_idle, "refresh to finish")
        assert gate.calls == 1
        assert json.loads(_request(url, "/api/data")[1])["generated_at"] == "new"
        # The lock was released: the next refresh is admitted again.
        assert json.loads(_request(url, "/api/refresh")[1])["status"] \
            == "refreshing"
        _wait_until(_refresh_idle, "second refresh to finish")

    def test_refresh_does_not_resurrect_a_repo_removed_meanwhile(
            self, threaded, tmp_path, monkeypatch):
        a = _make_repo(tmp_path, "alpha", "marker-alpha")
        b = _make_repo(tmp_path, "beta", "marker-beta")
        url = threaded([{"name": "alpha", "path": a},
                        {"name": "beta", "path": b}])
        gate = Gate()

        def collect(registry):
            rows = [{"name": r["name"], "path": r["path"]} for r in registry]
            gate.enter()
            return {"generated_at": "new", "repos": rows}

        monkeypatch.setattr(dashboard, "collect_standalone_data", collect)
        assert json.loads(_request(url, "/api/refresh")[1])["status"] \
            == "refreshing"
        assert gate.entered.wait(TIMEOUT)
        assert _request(url, "/api/repos/remove", {"path": a})[0] == 200
        gate.release()
        _wait_until(_refresh_idle, "refresh to finish")
        fleet = json.loads(_request(url, "/api/data")[1])
        assert fleet["generated_at"] == "new"
        assert [r["path"] for r in fleet["repos"]] == [b]

    def test_failed_collection_releases_admission(
            self, threaded, monkeypatch):
        url = threaded([])

        def collect(registry):
            raise RuntimeError("simulated collection failure")

        monkeypatch.setattr(dashboard, "collect_standalone_data", collect)
        assert json.loads(_request(url, "/api/refresh")[1])["status"] \
            == "refreshing"
        _wait_until(_refresh_idle, "failed refresh to release the lock")
        assert json.loads(_request(url, "/api/data")[1])["generated_at"] \
            == "seed"


# ── pins 4a–4c: remove is ordered against every same-path mutation ─────────────


def _gatorized(tmp_path, name):
    return _make_repo(tmp_path, name, f"marker-{name}")


def _plain(tmp_path, name):
    repo = tmp_path / name
    (repo / ".git").mkdir(parents=True)
    return str(repo.resolve())


class TestCommitPolicyRoute:
    """POST /api/repo/<name>/commit-policy: this machine's level for the
    clone, written to Git's private area through precommit_local_policy,
    never into the repository; Enterprise-managed repositories are refused."""

    def _repo(self, tmp_path, name="pol"):
        repo = Path(_gatorized(tmp_path, name))
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        return repo

    def test_warn_then_strict_writes_only_the_private_file(self, threaded, tmp_path):
        repo = self._repo(tmp_path)
        url = threaded([{"name": "pol", "path": str(repo)}])
        private = repo / ".git" / "gator-commit-policy.json"
        s, t = _request(url, "/api/repo/pol/commit-policy", {"level": "warn"})
        assert s == 200 and json.loads(t) == {"status": "ok", "commit_policy": "warn"}, t
        assert json.loads(private.read_text(encoding="utf-8"))["level"] == "warn"
        assert not (repo / ".gator" / "config.json").exists()
        fleet = {r["name"]: r for r in dashboard._fleet_snapshot()["repos"]}
        assert fleet["pol"]["commit_policy"] == "warn"
        s, t = _request(url, "/api/repo/pol/commit-policy", {"level": "strict"})
        assert s == 200 and json.loads(t)["commit_policy"] == "strict", t
        assert not private.exists()

    @pytest.mark.parametrize("body", [{"level": "off"}, {"level": "loose"}, {},
                                      {"enforcement_level": "warn"}])
    def test_other_levels_are_refused(self, threaded, tmp_path, body):
        repo = self._repo(tmp_path)
        url = threaded([{"name": "pol", "path": str(repo)}])
        s, t = _request(url, "/api/repo/pol/commit-policy", body)
        assert s == 400 and "strict or warn" in t, (s, t)
        assert not (repo / ".git" / "gator-commit-policy.json").exists()

    def test_enterprise_managed_is_refused(self, threaded, tmp_path):
        repo = self._repo(tmp_path)
        (repo / ".gator" / "enterprise.json").write_text('{"enabled": true}', encoding="utf-8")
        url = threaded([{"name": "pol", "path": str(repo)}])
        s, t = _request(url, "/api/repo/pol/commit-policy", {"level": "warn"})
        assert s == 409 and "Enterprise" in t, (s, t)
        assert not (repo / ".git" / "gator-commit-policy.json").exists()

    def test_retired_config_route_writes_nothing(self, threaded, tmp_path):
        repo = self._repo(tmp_path)
        url = threaded([{"name": "pol", "path": str(repo)}])
        s, _ = _request(url, "/api/repo/pol/config", {"enforcement_level": "warn"})
        assert s != 200
        assert not (repo / ".gator" / "config.json").exists()

class TestRemoveVersusSamePath:

    @pytest.fixture
    def runner(self, monkeypatch):
        """Gate the lifecycle subprocess (`data.run_text`) and record calls."""
        gate = Gate()
        gate.invocations = []

        def run_text(*args, **kw):
            gate.invocations.append(args)
            gate.enter()
            return "done", "", 0

        monkeypatch.setattr(dashboard_data, "run_text", run_text)
        return gate

    @pytest.mark.parametrize("verb,maker", [
        ("update", _gatorized), ("gatorize", _plain)])
    def test_remove_waits_out_a_running_lifecycle_action(
            self, threaded, tmp_path, runner, verb, maker):
        repo = maker(tmp_path, "target")
        url = threaded([{"name": "target", "path": repo}])

        pending = _in_thread(_request, url, f"/api/repo/target/{verb}", {})
        assert runner.entered.wait(TIMEOUT)
        s, t = _request(url, "/api/repos/remove", {"path": repo})
        assert s == 409 and "another change is running" in t, (s, t)
        assert [r["path"] for r in dashboard._registry_snapshot()] == [repo]

        runner.release()
        s, t = pending()
        assert s == 200 and json.loads(t)["status"] == "ok", t
        assert _request(url, "/api/repos/remove", {"path": repo})[0] == 200

    @pytest.mark.parametrize("verb,body,maker", [
        ("update", {}, _gatorized),
        ("gatorize", {}, _plain),
        ("commit-policy", {"level": "warn"}, _gatorized),
        ("topology", {"topology": "standalone"}, _gatorized),
    ])
    def test_same_path_action_during_and_after_remove(
            self, threaded, tmp_path, runner, monkeypatch, verb, body, maker):
        repo = maker(tmp_path, "target")
        url = threaded([{"name": "target", "path": repo}])
        gate = Gate()
        original_remove = gator_core.remove_dashboard_repo

        def remove(path):
            gate.enter()
            return original_remove(path)

        monkeypatch.setattr(gator_core, "remove_dashboard_repo", remove)
        removing = _in_thread(_request, url, "/api/repos/remove", {"path": repo})
        assert gate.entered.wait(TIMEOUT)

        s, t = _request(url, f"/api/repo/target/{verb}", body)
        assert s == 409 and "another change is running" in t, (s, t)

        gate.release()
        assert removing()[0] == 200
        s, t = _request(url, f"/api/repo/target/{verb}", body)
        assert s == 404, (s, t)
        assert runner.invocations == []
        assert not (Path(repo) / ".git" / "gator-commit-policy.json").exists()

    def test_action_whose_target_is_removed_before_it_locks_gets_404(
            self, threaded, tmp_path, runner, monkeypatch):
        """The route resolved its target, then a remove completed before the
        action took the repository lock: the re-check refuses it."""
        repo = _gatorized(tmp_path, "target")
        url = threaded([{"name": "target", "path": repo}])
        gate = Gate()
        original = dashboard._resolve_action_target

        def resolve(*args):
            found = original(*args)
            gate.enter()
            return found

        monkeypatch.setattr(dashboard, "_resolve_action_target", resolve)
        pending = _in_thread(_request, url, "/api/repo/target/update", {})
        assert gate.entered.wait(TIMEOUT)
        assert _request(url, "/api/repos/remove", {"path": repo})[0] == 200
        gate.release()
        s, t = pending()
        assert s == 404 and "not found" in t, (s, t)
        assert runner.invocations == []

    def test_register_versus_remove_and_register_for_one_path(
            self, threaded, tmp_path, monkeypatch):
        repo = _plain(tmp_path, "target")
        url = threaded([])
        gate = Gate()
        original_ensure = gator_core.ensure_dashboard_registry_entry

        def ensure(path, source="gator-init"):
            gate.enter()
            return original_ensure(path, source=source)

        monkeypatch.setattr(gator_core, "ensure_dashboard_registry_entry",
                            ensure)
        registering = _in_thread(_request, url, "/api/repos/register",
                                 {"path": repo})
        assert gate.entered.wait(TIMEOUT)
        for path in ("/api/repos/register", "/api/repos/remove"):
            s, t = _request(url, path, {"path": repo})
            assert s == 409 and "another change is running" in t, (path, s, t)
        gate.release()
        assert registering()[0] == 200
        assert [r["path"] for r in dashboard._registry_snapshot()] == [repo]
        persisted = json.loads(
            threaded.registry_file.read_text(encoding="utf-8"))["repos"]
        assert [str(Path(r["path"]).resolve()) for r in persisted] == [repo]


# ── audit sessions run one at a time ──────────────────────────────────────────


class TestAuditSerialization:

    def test_audit_requests_never_overlap(self, threaded, monkeypatch):
        url = threaded([])
        active, peak, lock = [0], [0], threading.Lock()

        def resolve(**kw):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with lock:
                active[0] -= 1
            return {"data": {"sessions": []}, "status": 200}

        monkeypatch.setattr(dashboard, "_resolve_audit_sessions", resolve)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(
                lambda _: _request(url, "/api/audit/sessions?fleet=true"),
                range(6), timeout=60))
        assert all(s == 200 for s, _ in results)
        assert peak[0] == 1


# ── pin 5: racing Loop mutations keep one valid outcome ───────────────────────


class TestLoopRaces:

    @pytest.fixture
    def loops(self):
        import test_dashboard_loops as tdl
        return tdl

    def _reap(self, url, rk, loop_id):
        with dashboard._LOOP_HOSTS_LOCK:
            entries = [v for k, v in dashboard._LOOP_HOSTS.items()
                       if k[1] == loop_id]
        _request(url, f"/api/repo-by-key/{rk}/loops/{loop_id}/end",
                 {"reason": "test cleanup"})
        for entry in entries:
            entry.thread.join(timeout=10)
            assert not entry.thread.is_alive()

    def test_two_extends_give_one_transition(self, threaded, tmp_path, loops):
        repo, rk, loop_id = loops._setup_loop_with_tokens(
            tmp_path, "race", stage="max_rounds_exceeded", blocked=True)
        loop_dir = repo / ".gator" / "loops" / loop_id
        url = threaded([{"name": "race", "path": str(repo), "repo_key": rk}])
        barrier = threading.Barrier(2, timeout=TIMEOUT)

        def extend(i):
            barrier.wait()
            return _request(
                url, f"/api/repo-by-key/{rk}/loops/{loop_id}/extend",
                {"rounds": 2, "message": f"race {i}"})

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(extend, range(2), timeout=60))
            statuses = sorted(s for s, _ in results)
            assert statuses in ([200, 409], [200, 503]), results
            events = [json.loads(line)["event"] for line in
                      (loop_dir / "events.jsonl").read_text(
                          encoding="utf-8").splitlines() if line.strip()]
            assert events.count("loop_extended") == 1
            session = json.loads((loop_dir / "session.json").read_text(
                encoding="utf-8"))
            assert session["status"]["max_rounds"] == 5
            with dashboard._LOOP_HOSTS_LOCK:
                hosted = [k for k in dashboard._LOOP_HOSTS if k[1] == loop_id]
            assert len(hosted) <= 1
        finally:
            self._reap(url, rk, loop_id)

    def test_two_starts_give_one_loop(self, threaded, tmp_path, loops):
        repo = tmp_path / "repo-start-race"
        (repo / ".gator").mkdir(parents=True)
        sketch = repo / "sketch.md"
        sketch.write_text("# Sketch\n\nRace.\n", encoding="utf-8")
        rk = loops._repo_key(repo)
        url = threaded([{"name": "start-race", "path": str(repo.resolve()),
                         "repo_key": rk}])
        barrier = threading.Barrier(2, timeout=TIMEOUT)

        def start(i):
            barrier.wait()
            return _request(url, f"/api/repo-by-key/{rk}/loops/start",
                            {"feature": f"race{i}", "sketch_path": str(sketch)})

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(start, range(2), timeout=60))
        statuses = sorted(s for s, _ in results)
        assert statuses == [201, 409], results
        created = [json.loads(t)["loop_id"] for s, t in results if s == 201]
        loop_dirs = [d.name for d in (repo / ".gator" / "loops").iterdir()
                     if d.is_dir()]
        assert loop_dirs == created
        self._reap(url, rk, created[0])

    @pytest.mark.parametrize("action,body", [
        ("pause", {}),
        ("interject", {"message": "note"}),
        ("unblock", {"no_response": True}),
        ("end", {"reason": "x"}),
        ("extend", {"rounds": 1, "message": "more"}),
    ])
    def test_session_lock_timeout_maps_to_503(
            self, threaded, tmp_path, loops, monkeypatch, action, body):
        stage = {"unblock": "paused_by_architect",
                 "extend": "max_rounds_exceeded"}.get(action, "plan_drafting")
        repo, rk, loop_id = loops._setup_loop_with_tokens(
            tmp_path, f"busy-{action}", stage=stage,
            blocked=stage != "plan_drafting")
        loop_dir = repo / ".gator" / "loops" / loop_id
        url = threaded([{"name": "busy", "path": str(repo), "repo_key": rk}])
        before = (loop_dir / "session.json").read_bytes()
        session_mod = sys.modules["session"]

        def timed_out(fd):
            raise OSError(errno.EDEADLK, "Resource deadlock avoided")

        monkeypatch.setattr(session_mod, "_lock_exclusive", timed_out)
        s, t = _request(
            url, f"/api/repo-by-key/{rk}/loops/{loop_id}/{action}", body)
        assert s == 503 and json.loads(t) == {"error": "loop is busy; retry"}, \
            (s, t)
        assert (loop_dir / "session.json").read_bytes() == before

    @pytest.mark.skipif(sys.platform != "win32",
                        reason="msvcrt.locking times out only on Windows; "
                               "POSIX flock(LOCK_EX) waits without a timeout")
    def test_real_windows_session_lock_contention_maps_to_503(
            self, threaded, tmp_path, loops):
        """Hold the real session.lock from another handle: the Loop
        transaction's msvcrt.locking(LK_LOCK) gives up after about 10 s with
        the OS's own error, and the Dashboard reports 503, writing nothing."""
        import msvcrt
        repo, rk, loop_id = loops._setup_loop_with_tokens(
            tmp_path, "contended", stage="plan_drafting")
        loop_dir = repo / ".gator" / "loops" / loop_id
        url = threaded([{"name": "contended", "path": str(repo),
                         "repo_key": rk}])
        before = (loop_dir / "session.json").read_bytes()
        lock_path = loop_dir / "session.lock"
        lock_path.touch(exist_ok=True)
        with open(lock_path, "r+") as holder:
            msvcrt.locking(holder.fileno(), msvcrt.LK_LOCK, 1)
            try:
                start = time.monotonic()
                s, t = _request(
                    url, f"/api/repo-by-key/{rk}/loops/{loop_id}/pause",
                    {}, timeout=60)
                waited = time.monotonic() - start
            finally:
                msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 1)
        assert s == 503 and json.loads(t) == {"error": "loop is busy; retry"},             (s, t)
        assert waited >= 5, f"returned after {waited:.1f}s, before the lock timed out"
        assert (loop_dir / "session.json").read_bytes() == before

    def test_other_session_lock_errors_are_not_reported_busy(
            self, threaded, tmp_path, loops, monkeypatch):
        """A non-contention OSError keeps its old behavior (unhandled: the
        connection drops) and never becomes the retryable 503."""
        repo, rk, loop_id = loops._setup_loop_with_tokens(
            tmp_path, "ioerror", stage="plan_drafting")
        loop_dir = repo / ".gator" / "loops" / loop_id
        url = threaded([{"name": "ioerror", "path": str(repo),
                         "repo_key": rk}])
        before = (loop_dir / "session.json").read_bytes()

        def broken(fd):
            # EIO stays a plain OSError (EACCES would become PermissionError,
            # which the route already maps to 409).
            raise OSError(errno.EIO, "I/O error")

        monkeypatch.setattr(sys.modules["session"], "_lock_exclusive", broken)
        with pytest.raises(OSError):
            _request(url, f"/api/repo-by-key/{rk}/loops/{loop_id}/pause", {})
        assert (loop_dir / "session.json").read_bytes() == before

    def test_only_the_lock_timeout_errno_counts_as_busy(self):
        assert dashboard._loop_lock_busy(OSError(errno.EDEADLK, "x"))
        assert dashboard._loop_lock_busy(OSError(errno.EBUSY, "x"))  # SessionBusyError (#61)
        assert not dashboard._loop_lock_busy(OSError(errno.EIO, "x"))
        assert not dashboard._loop_lock_busy(OSError("no errno"))


# ── pin 6: restart and upgrade drain in-flight POSTs, bounded ─────────────────


class TestRestartDrain:

    @pytest.fixture(autouse=True)
    def fresh_gate(self, monkeypatch):
        """Each test gets its own gate (draining is one-way per process)."""
        monkeypatch.setattr(dashboard, "_LIFECYCLE_GATE",
                            dashboard._LifecycleGate())

    @pytest.fixture
    def lifecycle(self, monkeypatch):
        """Record restart/upgrade calls instead of replacing the process."""
        calls = []
        done = threading.Event()

        def record(kind):
            def fn():
                calls.append((kind, time.monotonic()))
                done.set()
            return fn

        monkeypatch.setattr(dashboard, "_restart_server", record("restart"))
        monkeypatch.setattr(dashboard, "upgrade_and_restart", record("upgrade"))
        return calls, done

    @pytest.fixture
    def held_register(self, monkeypatch):
        """A register POST that stays in flight until released."""
        gate = Gate()
        original = gator_core.ensure_dashboard_registry_entry

        def ensure(path, source="gator-init"):
            gate.enter()
            return original(path, source=source)

        monkeypatch.setattr(gator_core, "ensure_dashboard_registry_entry",
                            ensure)
        return gate

    def test_restart_waits_for_an_in_flight_loop_post(
            self, threaded, tmp_path, lifecycle, monkeypatch):
        import test_dashboard_loops as loops
        calls, done = lifecycle
        repo, rk, loop_id = loops._setup_loop_with_tokens(
            tmp_path, "drain", stage="plan_drafting")
        url = threaded([{"name": "drain", "path": str(repo), "repo_key": rk}])
        session_mod = sys.modules["session"]
        real_lock = session_mod._lock_exclusive
        gate = Gate()

        def held_lock(fd):
            real_lock(fd)
            gate.enter()

        monkeypatch.setattr(session_mod, "_lock_exclusive", held_lock)
        pausing = _in_thread(
            _request, url, f"/api/repo-by-key/{rk}/loops/{loop_id}/pause", {})
        assert gate.entered.wait(TIMEOUT)

        # The restart request itself answers at once.
        start = time.monotonic()
        s, t = _request(url, "/api/restart", {})
        assert s == 200 and json.loads(t) == {"status": "restarting"}
        assert time.monotonic() - start < 2
        # While draining: new POSTs are refused, reads are still served.
        s, t = _request(url, "/api/repos/register",
                        {"path": _plain(tmp_path, "late")})
        assert s == 503 and json.loads(t) == {"error": "dashboard is restarting"}
        assert _request(url, "/api/data")[0] == 200
        time.sleep(0.3)
        assert calls == [], "restart ran while a Loop POST was in flight"

        released_at = time.monotonic()
        gate.release()
        assert pausing()[0] == 200
        assert done.wait(TIMEOUT)
        assert [k for k, _ in calls] == ["restart"]
        assert calls[0][1] >= released_at
        session = json.loads((repo / ".gator" / "loops" / loop_id
                              / "session.json").read_text(encoding="utf-8"))
        assert session["status"]["stage"] == "paused_by_architect"

    def test_restart_proceeds_after_the_drain_bound(
            self, threaded, tmp_path, lifecycle, held_register, monkeypatch):
        calls, done = lifecycle
        monkeypatch.setattr(dashboard, "_DRAIN_SECONDS", 0.5)
        url = threaded([])
        registering = _in_thread(_request, url, "/api/repos/register",
                                 {"path": _plain(tmp_path, "slow")})
        assert held_register.entered.wait(TIMEOUT)
        start = time.monotonic()
        assert _request(url, "/api/restart", {})[0] == 200
        assert done.wait(TIMEOUT), "restart never ran past the bound"
        assert 0.4 <= calls[0][1] - start < 5
        held_register.release()
        assert registering()[0] == 200

    @pytest.mark.parametrize("first,second", [
        (("/api/restart", "restarting", "restart"),
         ("/api/updates/upgrade", "upgrading", "upgrade")),
        (("/api/updates/upgrade", "upgrading", "upgrade"),
         ("/api/restart", "restarting", "restart")),
    ], ids=["restart-then-upgrade", "upgrade-then-restart"])
    def test_one_coordinator_and_truthful_responses_during_a_drain(
            self, threaded, lifecycle, held_register, tmp_path, first, second):
        """A repeat of the active action is acknowledged idempotently; the
        other action is refused with 409 naming the active one. Either way
        only the first action runs."""
        calls, done = lifecycle
        url = threaded([])
        registering = _in_thread(_request, url, "/api/repos/register",
                                 {"path": _plain(tmp_path, "slow")})
        assert held_register.entered.wait(TIMEOUT)
        first_path, first_status, first_kind = first
        second_path, second_status, _ = second

        for _ in range(2):  # the first request, then an idempotent repeat
            s, t = _request(url, first_path, {})
            assert s == 200 and json.loads(t) == {"status": first_status}, (s, t)
        s, t = _request(url, second_path, {})
        assert s == 409, (second_path, s, t)
        assert json.loads(t) == {"error": f"dashboard is already {first_status}",
                                 "status": first_status}
        assert second_status not in t

        held_register.release()
        assert registering()[0] == 200
        assert done.wait(TIMEOUT)
        time.sleep(0.3)
        assert [k for k, _ in calls] == [first_kind]

    def test_upgrade_drains_then_upgrades(self, threaded, lifecycle):
        calls, done = lifecycle
        url = threaded([])
        s, t = _request(url, "/api/updates/upgrade", {})
        assert s == 200 and json.loads(t) == {"status": "upgrading"}
        assert done.wait(TIMEOUT)
        assert [k for k, _ in calls] == ["upgrade"]

    def test_coordinator_start_failure_undoes_draining(
            self, lifecycle, monkeypatch):
        """Called directly on a stub handler: patching threading.Thread for
        a live request would also break the server's own worker threads."""
        calls, _ = lifecycle
        sent = []

        class StubHandler:
            def _send_json(self, data, status=200, **kw):
                sent.append((status, data))

        class NoThread:
            def __init__(self, *a, **kw):
                pass

            def start(self):
                raise RuntimeError("can't start new thread")

        with monkeypatch.context() as m:
            m.setattr(dashboard.threading, "Thread", NoThread)
            started = dashboard.DashboardHandler._start_lifecycle(
                StubHandler(), dashboard._restart_server, "restarting",
                "dashboard-restart")
        assert started is False
        assert sent and sent[0][0] == 500 and "could not start" in sent[0][1]["error"]
        assert not dashboard._LIFECYCLE_GATE.draining
        assert dashboard._LIFECYCLE_GATE.enter()  # POSTs are admitted again
        dashboard._LIFECYCLE_GATE.leave()
        assert calls == []


# ── checkpoint 4: the production threaded server ──────────────────────────────


def _browsable_repo(root, name):
    """A repo with a Markdown and an HTML document in `.gator/artifacts/`."""
    path = _make_repo(root, name, f"marker-{name}")
    (Path(path) / ".gator" / "artifacts" / "page.html").write_text(
        f"<!doctype html><title>{name}</title><p>page-{name}</p>\n",
        encoding="utf-8")
    return path


@pytest.fixture
def gated_listing(monkeypatch):
    """Hold every live /files listing inside its repository walk."""
    gate = Gate()
    original = dashboard._iter_scanner_files

    def held(*args, **kw):
        gate.enter()
        yield from original(*args, **kw)

    monkeypatch.setattr(dashboard, "_iter_scanner_files", held)
    yield gate
    gate.release()


class TestThreadedServer:

    def test_slow_listing_does_not_block_document_reads(
            self, threaded, tmp_path, gated_listing):
        """Pin 1: with a real /files handler held mid-walk, a /file and an
        HTML /raw for the same repository answer at once."""
        a = _browsable_repo(tmp_path, "alpha")
        url = threaded([{"name": "alpha", "path": a}], production=True)
        listing = _in_thread(_request, url, "/api/repo/alpha/files")
        assert gated_listing.entered.wait(TIMEOUT)

        for path, expect in (
                ("/api/repo/alpha/file/artifacts/marker-alpha.md",
                 "# marker-alpha"),
                ("/api/repo/alpha/raw/artifacts/page.html",
                 "page-alpha")):
            start = time.monotonic()
            s, t = _request(url, path, timeout=5)
            elapsed = time.monotonic() - start
            assert s == 200 and expect in t, (path, s, t[:200])
            assert elapsed < 2, f"{path} waited {elapsed:.2f}s behind /files"

        gated_listing.release()
        s, t = listing()
        assert s == 200 and "marker-alpha" in t

    def test_worker_cap_queues_excess_requests(
            self, threaded, tmp_path, gated_listing):
        """With every worker busy, the next request waits in the backlog
        (no refusal, no extra thread) and is served once a worker frees."""
        a = _browsable_repo(tmp_path, "alpha")
        url = threaded([{"name": "alpha", "path": a}], production=True,
                       max_workers=2)
        held = [_in_thread(_request, url, "/api/repo/alpha/files")
                for _ in range(2)]
        _wait_until(lambda: gated_listing.calls >= 2, "two held listings")
        queued = _in_thread(_request, url, "/api/data")
        time.sleep(0.5)
        workers = [t for t in threading.enumerate()
                   if t.name == "dashboard-request"]
        assert len(workers) == 2, _diagnostics(["worker count"])

        gated_listing.release()
        assert queued()[0] == 200
        assert all(h()[0] == 200 for h in held)

    def test_heavy_routes_share_a_bounded_pool(
            self, threaded, tmp_path, gated_listing, monkeypatch):
        """Heavy routes wait for a heavy slot (503 after the bound), while
        small reads keep their own workers."""
        monkeypatch.setattr(dashboard, "_HEAVY_SLOTS",
                            threading.BoundedSemaphore(1))
        monkeypatch.setattr(dashboard, "_HEAVY_TIMEOUT", 0.5)
        a = _browsable_repo(tmp_path, "alpha")
        url = threaded([{"name": "alpha", "path": a}], production=True)
        listing = _in_thread(_request, url, "/api/repo/alpha/files")
        assert gated_listing.entered.wait(TIMEOUT)

        s, t = _request(url, "/api/repo/alpha/search?q=marker")
        assert s == 503 and json.loads(t) == {"error": "dashboard busy; retry"}
        s, _ = _request(url, "/api/repo/alpha/file/artifacts/marker-alpha.md")
        assert s == 200

        gated_listing.release()
        assert listing()[0] == 200
        s, t = _request(url, "/api/repo/alpha/search?q=marker")
        assert s == 200 and "marker-alpha" in t

    def test_main_serves_with_the_threaded_server(self):
        import inspect
        source = inspect.getsource(dashboard.main)
        assert source.count("DashboardHTTPServer((") == 2
        assert "HTTPServer((" not in source.replace("DashboardHTTPServer((", "")
        assert dashboard.DashboardHandler.protocol_version == "HTTP/1.0"


class TestConcurrentReads:

    def test_mixed_reads_across_two_repositories(self, threaded, tmp_path):
        """Pin 2: concurrent /files, /raw, /api/data and Loop /status
        across two repositories keep identity and security headers."""
        import test_dashboard_loops as loops
        repos = {}
        for name in ("alpha", "beta"):
            repo, rk, loop_id = loops._setup_loop_with_tokens(
                tmp_path, name, stage="plan_drafting")
            (repo / ".git").mkdir()
            artifacts = repo / ".gator" / "artifacts"
            artifacts.mkdir(parents=True)
            (artifacts / f"marker-{name}.md").write_text(f"# {name}\n",
                                                         encoding="utf-8")
            (artifacts / "page.html").write_text(
                f"<!doctype html><p>page-{name}</p>\n", encoding="utf-8")
            repos[name] = (str(repo.resolve()), rk, loop_id)
        url = threaded([{"name": n, "path": p, "repo_key": rk}
                        for n, (p, rk, _) in repos.items()], production=True)
        problems = []

        def check(i):
            name = ("alpha", "beta")[i % 2]
            other = ("beta", "alpha")[i % 2]
            _, rk, loop_id = repos[name]
            s, t, h = _request_full(url, f"/api/repo/{name}/files")
            if s != 200 or f"marker-{name}" not in t or f"marker-{other}" in t:
                problems.append(("files", name, s))
            if h.get("X-Content-Type-Options") != "nosniff":
                problems.append(("files-headers", name, dict(h)))
            s, t, h = _request_full(
                url, f"/api/repo/{name}/raw/artifacts/page.html")
            if s != 200 or f"page-{name}" not in t:
                problems.append(("raw", name, s))
            if ("frame-ancestors" not in (h.get("Content-Security-Policy") or "")
                    or "Sec-Fetch-Dest" not in (h.get("Vary") or "")
                    or h.get("X-Content-Type-Options") != "nosniff"):
                problems.append(("raw-headers", name, dict(h)))
            s, t = _request(url, f"/api/repo-by-key/{rk}/loops/{loop_id}/status")
            if s != 200 or json.loads(t).get("loop_id") != loop_id:
                problems.append(("status", name, s, t[:120]))
            s, t = _request(url, "/api/data")
            if s != 200 or len(json.loads(t)["repos"]) != 2:
                problems.append(("data", s))

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(check, range(40), timeout=90))
        assert not problems, _diagnostics(problems)


class TestContentPolicyUnderConcurrency:

    NEGATIVE = [
        "/api/repo/alpha/file/..%2F..%2Fsecret.md",
        "/api/repo/alpha/file/.gator/../../secret.md",
        "/api/repo/alpha/raw/source/.git/config",
        "/api/repo/alpha/file/override-request.json",
        "/api/repo/alpha/raw/override-approved.json",
        "/api/repo/alpha/file/missing.md",
        "/api/repo/alpha/raw/artifacts/CON.md",
        "/api/repo/alpha/file/artifacts/marker-alpha.md.",
        "/api/repo/nosuch/files",
        "/api/repo/alpha/files?version=notasha",
    ]

    def test_negative_requests_answer_identically_when_concurrent(
            self, threaded, tmp_path):
        """Pin 7 (subset): denied, traversal, reserved-name, missing and
        malformed requests give byte-identical answers serially and under
        16-way concurrency (no state leaks between simultaneous requests)."""
        a = _browsable_repo(tmp_path, "alpha")
        (Path(a) / ".gator" / "override-request.json").write_text(
            "{}", encoding="utf-8")
        (Path(a).parent / "secret.md").write_text("secret", encoding="utf-8")
        url = threaded([{"name": "alpha", "path": a}], production=True)
        serial = {p: _request(url, p) for p in self.NEGATIVE}
        assert all(s >= 400 for s, _ in serial.values()), serial
        assert not any(t == "secret" for _, t in serial.values())

        jobs = self.NEGATIVE * 8
        barrier = threading.Barrier(16, timeout=TIMEOUT)

        def run(path):
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
            return path, _request(url, path)

        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(run, jobs, timeout=90))
        mismatched = [(p, r[0], serial[p][0]) for p, r in results
                      if r != serial[p]]
        assert not mismatched, _diagnostics(mismatched)


class TestMixedStress:

    def test_mixed_reads_and_mutations_stay_coherent(
            self, threaded, tmp_path, monkeypatch):
        """Pin 8: 400 mixed requests over 12 threads, bounded overall; no
        unexpected status, no crossed identity, a coherent end state."""
        import test_dashboard_loops as loops
        repo, rk, loop_id = loops._setup_loop_with_tokens(
            tmp_path, "stress", stage="plan_drafting")
        (repo / ".git").mkdir()
        (repo / ".gator" / "artifacts").mkdir(parents=True)
        (repo / ".gator" / "artifacts" / "marker-stress.md").write_text(
            "# stress\n", encoding="utf-8")
        stress = str(repo.resolve())
        beta = _browsable_repo(tmp_path, "beta")
        # The commit-policy writes resolve Git's private path: a real repository.
        subprocess.run(["git", "init", "-q", beta], check=True, capture_output=True)
        churn = [_plain(tmp_path, f"churn{i}") for i in range(4)]
        url = threaded([{"name": "stress", "path": stress, "repo_key": rk},
                        {"name": "beta", "path": beta}], production=True)

        def collect(registry):
            return {"generated_at": "refreshed",
                    "repos": [{"name": r["name"], "path": r["path"]}
                              for r in registry]}

        monkeypatch.setattr(dashboard, "collect_standalone_data", collect)
        ok = {200}
        plan = []
        for i in range(400):
            kind = i % 8
            if kind == 0:
                plan.append(("GET", "/api/repo/stress/files", None, ok,
                             "marker-stress", "marker-beta"))
            elif kind == 1:
                plan.append(("GET", "/api/repo/beta/files", None, ok,
                             "marker-beta", "marker-stress"))
            elif kind == 2:
                plan.append(("GET", "/api/repo/beta/raw/artifacts/page.html",
                             None, ok, "page-beta", None))
            elif kind == 3:
                plan.append(("GET", f"/api/repo-by-key/{rk}/loops/{loop_id}/status",
                             None, ok, loop_id, None))
            elif kind == 4:
                plan.append(("GET", "/api/data", None, ok, None, None))
            elif kind == 5:
                p = churn[(i // 8) % 4]
                plan.append(("POST", "/api/repos/register", {"path": p},
                             {200, 409}, None, None))
            elif kind == 6:
                p = churn[(i // 8 + 2) % 4]
                plan.append(("POST", "/api/repos/remove", {"path": p},
                             {200, 404, 409}, None, None))
            elif (i // 8) % 2:
                plan.append(("GET", "/api/refresh", None, ok, None, None))
            else:
                plan.append(("POST", "/api/repo/beta/commit-policy",
                             {"level": "warn"},
                             {200, 409}, None, None))
        problems = []

        def run(item):
            method, path, body, allowed, own, other = item
            try:
                s, t = _request(url, path, body if method == "POST" else None)
            except OSError as exc:
                problems.append((path, "exception", repr(exc)))
                return
            if s not in allowed:
                problems.append((path, s, t[:160]))
            elif s == 200 and own and (own not in t or (other and other in t)):
                problems.append((path, "identity", t[:160]))

        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(run, plan, timeout=90))
        elapsed = time.monotonic() - start
        assert not problems, _diagnostics(problems)
        assert elapsed < 90
        _wait_until(_refresh_idle, "refresh to settle")

        # End state: the seeded repos survive; registry file and snapshot agree.
        snapshot = sorted(r["path"] for r in dashboard._registry_snapshot())
        persisted = sorted(str(Path(r["path"]).resolve()) for r in json.loads(
            threaded.registry_file.read_text(encoding="utf-8"))["repos"])
        assert snapshot == persisted
        assert {stress, beta} <= set(snapshot)
        assert json.loads((Path(beta) / ".git" / "gator-commit-policy.json").read_text(
            encoding="utf-8"))["level"] == "warn"
        assert not (Path(beta) / ".gator" / "config.json").exists()
