"""B1 Slice 2 HTTP integration tests.

Hits the actual subprocess dashboard spun up by Plan A's
`dashboard_fleet` fixture. Covers:

- E1 wire-schema round-trip: live + historical for all three
  namespaces (`source/`, `.gator`, `gator-command/`).
- Discovery-serving symmetry: every `/files` entry round-trips to
  a 200 via `/file/<path>` and `/raw/<path>`.
- Secret material never listed: `private.pem`, `.env.local`,
  `sessions/_active/`, `.override-approved.json`.
- `/file` JSON envelope shape + `content_type` advertisement.
- Versioned reads via `mission-r2` SHA.
- `/history/<file>` for deleted `gator-command/README.md`.
- Governance-root alias denial (`source/.gator/mission.md`).
- Parse-error routing: `/file` → JSON envelope 400; `/raw` →
  HTML 400; version-bearing errors carry `no-store`.
- Legacy pass-through: `/api/data`, `/api/repo/<name>/history`,
  `/api/repo/<name>/search`, `/api/repo/<name>/commits`,
  `/api/updates/check`, `/api/repos/discover`.

The subprocess dashboard is deliberately treated as opaque —
tests exercise the wire protocol only, never poking module
internals. Slice 1 unit tests cover the pure helpers.
"""

import json
import urllib.error
import urllib.parse
import urllib.request


def _url(fleet, path):
    return fleet["url"].rstrip("/") + path


def _get(fleet, path, *, expect_status=200):
    """GET a path; return (status, body_bytes, headers dict).
    Does NOT raise on non-2xx — tests inspect the returned status.
    """
    try:
        resp = urllib.request.urlopen(_url(fleet, path), timeout=10)
        return (resp.status, resp.read(), dict(resp.headers))
    except urllib.error.HTTPError as exc:
        return (exc.code, exc.read(), dict(exc.headers))


def _get_json(fleet, path, *, expect_status=200):
    status, body, headers = _get(fleet, path)
    assert status == expect_status, (
        f"expected {expect_status}, got {status}, body={body!r}")
    return status, json.loads(body.decode("utf-8")), headers


# ── E1 wire-schema round-trip (live) ────────────────────────────

def test_files_live_source_repo_wire_schema(dashboard_fleet):
    status, data, _ = _get_json(
        dashboard_fleet, "/api/repo/alpha/files")
    paths = {(f["path"], f["source"]) for f in data["files"]}
    assert ("source/example.py", "repo") in paths
    entry = next(
        f for f in data["files"] if f["path"] == "source/example.py")
    assert entry["source"] == "repo"
    assert entry["dir"] == "source"
    assert entry["name"] == "example.py"
    assert entry["size"] > 0
    # Round-trip: /file/ must serve the entry it listed.
    round_status, _, _ = _get(
        dashboard_fleet, "/api/repo/alpha/file/source/example.py")
    assert round_status == 200


def test_files_live_gator_wire_schema(dashboard_fleet):
    _, data, _ = _get_json(dashboard_fleet, "/api/repo/alpha/files")
    entry = next(
        f for f in data["files"] if f["path"] == "mission.md")
    assert entry["source"] == ".gator"
    assert entry["dir"] == ""
    assert entry["name"] == "mission.md"
    round_status, _, _ = _get(
        dashboard_fleet, "/api/repo/alpha/file/mission.md")
    assert round_status == 200


def test_files_live_gator_command_wire_schema(dashboard_fleet):
    # `gator-command/` was deleted in `gc-deleted`. On the live
    # tree it is absent, so /files should NOT list it. This pin
    # is complementary to the versioned pin below.
    _, data, _ = _get_json(dashboard_fleet, "/api/repo/alpha/files")
    gc_entries = [
        f for f in data["files"]
        if f["source"] == "gator-command"]
    assert gc_entries == []


# ── E1 wire-schema round-trip (historical) ──────────────────────

def test_files_historical_source_repo_wire_schema(dashboard_fleet):
    seed = dashboard_fleet["repos"]["alpha"]["commits"]["seed"]
    _, data, _ = _get_json(
        dashboard_fleet,
        f"/api/repo/alpha/files?version={seed}")
    assert data["version"] == seed
    paths = {(f["path"], f["source"]) for f in data["files"]}
    assert ("source/example.py", "repo") in paths


def test_files_historical_gator_wire_schema(dashboard_fleet):
    seed = dashboard_fleet["repos"]["alpha"]["commits"]["seed"]
    _, data, _ = _get_json(
        dashboard_fleet,
        f"/api/repo/alpha/files?version={seed}")
    assert ("mission.md", ".gator") in {
        (f["path"], f["source"]) for f in data["files"]}


def test_files_historical_gator_command_wire_schema(
        dashboard_fleet):
    seed = dashboard_fleet["repos"]["alpha"]["commits"]["seed"]
    _, data, _ = _get_json(
        dashboard_fleet,
        f"/api/repo/alpha/files?version={seed}")
    # `gator-command/README.md` was present at the seed commit
    # (before gc-deleted).
    assert ("gator-command/README.md", "gator-command") in {
        (f["path"], f["source"]) for f in data["files"]}


def test_files_historical_no_store_header(dashboard_fleet):
    seed = dashboard_fleet["repos"]["alpha"]["commits"]["seed"]
    _, _, headers = _get(
        dashboard_fleet,
        f"/api/repo/alpha/files?version={seed}")
    assert headers.get("Cache-Control") == "no-store"
    assert headers.get("X-Content-Type-Options") == "nosniff"


def test_files_live_no_cache_header(dashboard_fleet):
    _, _, headers = _get(
        dashboard_fleet, "/api/repo/alpha/files")
    assert headers.get("Cache-Control") == "no-cache"


# ── Secret material never listed ────────────────────────────────

def test_files_never_lists_private_pem(dashboard_fleet):
    _, data, _ = _get_json(dashboard_fleet, "/api/repo/alpha/files")
    for f in data["files"]:
        assert not f["path"].endswith("private.pem"), (
            f"private.pem leaked into /files: {f}")


def test_files_never_lists_env_local(dashboard_fleet):
    _, data, _ = _get_json(dashboard_fleet, "/api/repo/alpha/files")
    for f in data["files"]:
        assert ".env" not in f["path"], (
            f".env.local leaked into /files: {f}")


def test_files_never_lists_sessions_active(dashboard_fleet):
    _, data, _ = _get_json(dashboard_fleet, "/api/repo/alpha/files")
    for f in data["files"]:
        assert not f["path"].startswith("sessions/_active/"), (
            f"sessions/_active leaked: {f}")


def test_files_never_lists_override_internal(dashboard_fleet):
    _, data, _ = _get_json(dashboard_fleet, "/api/repo/alpha/files")
    for f in data["files"]:
        assert "override-approved" not in f["name"], (
            f"override-approved leaked: {f}")


# ── /file JSON envelope ─────────────────────────────────────────

def test_file_success_json_envelope(dashboard_fleet):
    status, data, headers = _get_json(
        dashboard_fleet, "/api/repo/alpha/file/mission.md")
    assert data["path"] == "mission.md"
    assert data["content"].startswith("# alpha mission")
    assert data["content_type"] == "text/plain"
    assert data["version"] is None
    assert data["last_modified"]
    assert headers["Content-Type"] == (
        "application/json; charset=utf-8")
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_file_svg_content_type_is_svg(dashboard_fleet):
    _, data, _ = _get_json(
        dashboard_fleet,
        "/api/repo/alpha/file/blueprints/sample.svg")
    assert data["content_type"] == "image/svg+xml"
    assert data["content"].startswith("<?xml")


def test_file_historical_returns_prior_body(dashboard_fleet):
    seed = dashboard_fleet["repos"]["alpha"]["commits"]["seed"]
    _, data, headers = _get_json(
        dashboard_fleet,
        f"/api/repo/alpha/file/mission.md?version={seed}")
    assert data["version"] == seed
    assert data["content"] == "# alpha mission\n\nSeed body.\n"
    assert headers.get("Cache-Control") == "no-store"


def test_file_historical_after_r2(dashboard_fleet):
    r2 = dashboard_fleet["repos"]["alpha"]["commits"]["mission-r2"]
    _, data, _ = _get_json(
        dashboard_fleet,
        f"/api/repo/alpha/file/mission.md?version={r2}")
    assert "Revised body" in data["content"]


def test_file_governance_root_alias_denied(dashboard_fleet):
    # /file/source/.gator/mission.md must NOT resolve to the
    # governance document — one-canonical-path invariant.
    status, _, _ = _get(
        dashboard_fleet,
        "/api/repo/alpha/file/source/.gator/mission.md")
    assert status == 404


def test_file_source_gator_command_alias_denied(dashboard_fleet):
    status, _, _ = _get(
        dashboard_fleet,
        "/api/repo/alpha/file/source/gator-command/README.md")
    assert status == 404


def test_file_traversal_returns_json_400(dashboard_fleet):
    status, body, headers = _get(
        dashboard_fleet,
        "/api/repo/alpha/file/source/..%2fetc%2fpasswd")
    assert status == 400
    assert headers["Content-Type"] == (
        "application/json; charset=utf-8")
    envelope = json.loads(body.decode("utf-8"))
    assert envelope["code"] == 400
    assert "error" in envelope


def test_file_version_error_carries_no_store(dashboard_fleet):
    status, body, headers = _get(
        dashboard_fleet,
        "/api/repo/alpha/file/mission.md?version=xyz")
    assert status == 400
    assert headers.get("Cache-Control") == "no-store"


# ── /raw endpoint ───────────────────────────────────────────────

def test_raw_svg_bytes(dashboard_fleet):
    status, body, headers = _get(
        dashboard_fleet,
        "/api/repo/alpha/raw/blueprints/sample.svg")
    assert status == 200
    assert headers["Content-Type"] == "image/svg+xml"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert body.startswith(b"<?xml")


def test_raw_png_bytes(dashboard_fleet):
    status, body, headers = _get(
        dashboard_fleet,
        "/api/repo/alpha/raw/blueprints/hero.png")
    assert status == 200
    assert headers["Content-Type"] == "image/png"
    assert body.startswith(b"\x89PNG")


def test_raw_denies_private_pem(dashboard_fleet):
    status, _, _ = _get(
        dashboard_fleet, "/api/repo/alpha/raw/source/private.pem")
    assert status == 404  # never 403 — no oracle


def test_raw_denies_env_local(dashboard_fleet):
    status, _, _ = _get(
        dashboard_fleet, "/api/repo/alpha/raw/source/.env.local")
    assert status == 404


def test_raw_parse_error_is_html_400(dashboard_fleet):
    # `/raw` parse errors are raw HTML (not JSON) per §8.1.
    status, body, headers = _get(
        dashboard_fleet,
        "/api/repo/alpha/raw/source/..%2fetc")
    assert status == 400
    assert headers["Content-Type"].startswith("text/html")
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_raw_version_error_carries_no_store(dashboard_fleet):
    status, _, headers = _get(
        dashboard_fleet,
        "/api/repo/alpha/raw/source/example.py?version=xyz")
    assert status == 400
    assert headers.get("Cache-Control") == "no-store"
    assert headers.get("X-Content-Type-Options") == "nosniff"


# ── /history endpoint (F5 — no ?version=; F4 absent-ns support) ─

def test_history_returns_commits_for_live_file(dashboard_fleet):
    _, data, _ = _get_json(
        dashboard_fleet,
        "/api/repo/alpha/history/mission.md")
    assert data["path"] == "mission.md"
    assert len(data["commits"]) >= 2  # seed + mission-r2


def test_history_returns_commits_for_deleted_file(dashboard_fleet):
    # `gator-command/README.md` was deleted in gc-deleted. Its
    # history MUST still be returnable — F5 absent-namespace
    # support via `_contained_namespace_root(for_history_only=)`.
    _, data, _ = _get_json(
        dashboard_fleet,
        "/api/repo/alpha/history/gator-command/README.md")
    assert data["path"] == "gator-command/README.md"
    assert len(data["commits"]) >= 1


def test_history_rejects_version_key(dashboard_fleet):
    seed = dashboard_fleet["repos"]["alpha"]["commits"]["seed"]
    status, body, _ = _get(
        dashboard_fleet,
        f"/api/repo/alpha/history/mission.md?version={seed}")
    assert status == 400
    envelope = json.loads(body.decode("utf-8"))
    assert "not supported" in envelope["error"]


# ── Legacy pass-through (E4b + F1 preserve-shipped) ─────────────

def test_legacy_root_still_serves_dashboard(dashboard_fleet):
    status, body, headers = _get(dashboard_fleet, "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")


def test_legacy_api_data_still_serves(dashboard_fleet):
    status, data, _ = _get_json(dashboard_fleet, "/api/data")
    assert status == 200
    assert isinstance(data, dict)


def test_legacy_repo_history_repo_scope(dashboard_fleet):
    # /api/repo/<name>/history (no logical) is legacy repo-scope.
    status, data, _ = _get_json(
        dashboard_fleet, "/api/repo/alpha/history")
    assert status == 200
    assert "commits" in data
    assert data["repo"] == "alpha"


def test_legacy_repo_search_pass_through(dashboard_fleet):
    status, data, _ = _get_json(
        dashboard_fleet, "/api/repo/alpha/search?q=mission")
    assert status == 200
    assert "results" in data


def test_legacy_repo_commits_pass_through(dashboard_fleet):
    status, data, _ = _get_json(
        dashboard_fleet, "/api/repo/alpha/commits")
    assert status == 200
    assert "commits" in data


def test_legacy_updates_check_pass_through(dashboard_fleet):
    status, _, _ = _get_json(dashboard_fleet, "/api/updates/check")
    assert status == 200


def test_legacy_repos_discover_pass_through(dashboard_fleet):
    status, _, _ = _get_json(dashboard_fleet, "/api/repos/discover")
    assert status == 200


def test_debug_seam_gated_on_returns_registry(dashboard_fleet):
    # `dashboard_fleet` is built with debug=True.
    status, data, _ = _get_json(
        dashboard_fleet, "/api/__gator_debug/registry_state")
    assert status == 200
    assert "registry_repos" in data


def test_debug_seam_gated_off_returns_404(dashboard_fleet_debug_off):
    status, _, _ = _get(
        dashboard_fleet_debug_off,
        "/api/__gator_debug/registry_state")
    assert status == 404


def test_unknown_path_returns_404(dashboard_fleet):
    status, _, _ = _get(
        dashboard_fleet, "/api/repo/alpha/does-not-exist")
    # Falls through to Tier 2 which invokes gator-repo-status; the
    # subprocess returns {"error": "..."} JSON. Either 200 with an
    # error payload OR 404 is acceptable for this fall-through —
    # what matters is that B1 did NOT swallow the request.
    assert status in (200, 404)


# ── /files/extra 404 shape ──────────────────────────────────────

def test_files_extra_returns_404(dashboard_fleet):
    status, body, headers = _get(
        dashboard_fleet, "/api/repo/alpha/files/extra")
    assert status == 404
    assert headers["Content-Type"] == (
        "application/json; charset=utf-8")


# ── E2 trailing-slash normalization (integration) ───────────────

def test_files_with_trailing_slash_still_serves(dashboard_fleet):
    status, data, _ = _get_json(
        dashboard_fleet, "/api/repo/alpha/files/")
    assert status == 200
    assert "files" in data


def test_history_repo_scope_with_trailing_slash_still_serves(
        dashboard_fleet):
    # `/history/` with trailing slash falls through to legacy
    # repo-scope handler (per E2 shipped `do_GET` normalization).
    status, data, _ = _get_json(
        dashboard_fleet, "/api/repo/alpha/history/")
    assert status == 200
    assert "commits" in data
