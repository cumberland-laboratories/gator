"""B1 Slice 3 platform-specific integration tests.

Two platform tracks:

- **POSIX parser-symmetry (Linux/macOS only)**: seed filenames that
  the current Windows/POSIX parse contract REJECTS but that POSIX
  filesystems can legitimately hold (`CON.txt`, `foo:bar.py`,
  `name.py.`, control-char names). Each pin asserts:
    (a) the file is ABSENT from `/api/repo/<name>/files`
        (discovery-serving symmetry — the walker + parse gate).
    (b) `/api/repo/<name>/file/source/<name>` returns **400**
        (parse reject, per errata E4a — NOT 404). The split
        matters: 400 says "parser said no", 404 says "authorized
        target absent". A parser-symmetry drift would flip 400 to
        404 and go unnoticed without this pin.

- **Windows junction (Windows only)**: create an external
  directory outside the repo containing a valid governance file,
  junction it into `.gator/`, GET `/files`, assert NEITHER the
  junction directory NOR its descendants appear. The walker's
  `_is_reparse_point` gate is load-bearing because `rglob` on
  Windows silently traverses junctions (`is_symlink()` returns
  False), which is exactly the F2 bypass class the r4 rewrite
  closes.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

import pytest


def _url(fleet, path):
    return fleet["url"].rstrip("/") + path


def _get(fleet, path):
    try:
        resp = urllib.request.urlopen(_url(fleet, path), timeout=10)
        return (resp.status, resp.read(), dict(resp.headers))
    except urllib.error.HTTPError as exc:
        return (exc.code, exc.read(), dict(exc.headers))


def _get_json(fleet, path):
    status, body, headers = _get(fleet, path)
    return status, json.loads(body.decode("utf-8")), headers


# ── POSIX parser-symmetry pins (E4a — 400, not 404) ────────────

pytestmark_posix = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows filesystem cannot create these filenames "
           "(colons, trailing dots, control chars reserved by "
           "Win32 filename resolver). Test targets POSIX only.",
)


@pytestmark_posix
def test_files_omits_dos_device_filename_on_posix(
        dashboard_fleet_mutable):
    """CON.txt is a legitimate POSIX filename. Windows would
    reject the name as a DOS device — the parser applies the
    same rejection on both platforms so `/files` and `/file`
    agree that the file is not visible.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]
    victim = alpha / "CON.txt"
    victim.write_text("dos device probe\n", encoding="utf-8")

    _, data, _ = _get_json(fleet, "/api/repo/alpha/files")
    paths = {f["path"] for f in data["files"]}
    assert "source/CON.txt" not in paths, (
        "CON.txt appeared in /files — discovery/serving desync")

    status, body, headers = _get(
        fleet, "/api/repo/alpha/file/source/CON.txt")
    assert status == 400, (
        f"expected 400 (parse reject via E4a), got {status}: "
        f"{body!r}")
    envelope = json.loads(body.decode("utf-8"))
    assert envelope["code"] == 400


@pytestmark_posix
def test_files_omits_ads_colon_filename_on_posix(
        dashboard_fleet_mutable):
    """`foo:bar.py` is a legitimate POSIX filename. On Windows
    it would parse as an ADS reference — the parser rejects on
    both platforms for symmetry.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]
    victim = alpha / "foo:bar.py"
    victim.write_text("ads probe\n", encoding="utf-8")

    _, data, _ = _get_json(fleet, "/api/repo/alpha/files")
    for f in data["files"]:
        assert ":" not in f["path"], (
            f"ADS filename appeared in /files: {f}")

    status, body, _ = _get(
        fleet, "/api/repo/alpha/file/source/foo:bar.py")
    assert status == 400, (
        f"expected 400 (parse reject via E4a), got {status}: "
        f"{body!r}")


@pytestmark_posix
def test_files_omits_trailing_dot_filename_on_posix(
        dashboard_fleet_mutable):
    """`name.py.` is a legitimate POSIX filename. Win32 strips
    trailing dots on normalization, so the parser rejects both
    the trailing-dot form and any name whose strip changes the
    identity.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]
    victim = alpha / "trailing.py."
    victim.write_text("trailing dot probe\n", encoding="utf-8")

    _, data, _ = _get_json(fleet, "/api/repo/alpha/files")
    for f in data["files"]:
        assert not f["path"].endswith("."), (
            f"trailing-dot filename appeared in /files: {f}")

    status, body, _ = _get(
        fleet, "/api/repo/alpha/file/source/trailing.py.")
    assert status == 400


@pytestmark_posix
def test_files_omits_control_char_filename_on_posix(
        dashboard_fleet_mutable):
    """Control chars in filenames are legal on POSIX but rejected
    by `parse_logical_path` step 6 (regex `[\\x00-\\x1f]`). The
    file must be absent from /files. The URL must not
    round-trip — /file returns 400.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]
    victim = alpha / "bell\x07file.py"
    victim.write_text("control char probe\n", encoding="utf-8")

    _, data, _ = _get_json(fleet, "/api/repo/alpha/files")
    for f in data["files"]:
        assert "\x07" not in f["path"], (
            f"control-char filename appeared: {f}")


@pytestmark_posix
def test_parser_symmetry_scanner_and_url_agree_on_posix(
        dashboard_fleet_mutable):
    """Composite pin: a well-formed source file is listed AND
    round-trips; a well-formed source file with a parser-
    rejecting name is absent AND round-trips to 400. This is
    the r6 F4 canonical-logical + parse_logical_path predicate
    exercised end-to-end.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]
    (alpha / "legit.py").write_text("legit\n", encoding="utf-8")
    (alpha / "CON.md").write_text("device\n", encoding="utf-8")

    _, data, _ = _get_json(fleet, "/api/repo/alpha/files")
    paths = {f["path"] for f in data["files"]}
    assert "source/legit.py" in paths
    assert "source/CON.md" not in paths

    ok_status, _, _ = _get(
        fleet, "/api/repo/alpha/file/source/legit.py")
    bad_status, _, _ = _get(
        fleet, "/api/repo/alpha/file/source/CON.md")
    assert ok_status == 200
    assert bad_status == 400


# ── Windows junction pin (F2) ──────────────────────────────────

@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Junctions are Windows-only.",
)
def test_files_rejects_windows_junction(
        dashboard_fleet_mutable, tmp_path_factory):
    """Create an external directory containing a valid governance
    file, junction it into `<alpha>/.gator/junctioned`, then GET
    `/files`. Neither the junction nor its descendants may appear.

    Requires the walker's `_is_reparse_point` gate — `rglob` on
    Windows silently traverses junctions, so this is the F2
    bypass class the r4 walker rewrite closes.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]

    external = tmp_path_factory.mktemp("junction_target")
    (external / "smuggled.md").write_text(
        "must never appear\n", encoding="utf-8")

    junction_path = alpha / ".gator" / "junctioned"
    r = subprocess.run(
        ["cmd", "/c", "mklink", "/J",
         str(junction_path), str(external)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        pytest.skip(
            f"mklink /J failed (permission?): {r.stderr!r}")

    try:
        _, data, _ = _get_json(fleet, "/api/repo/alpha/files")
    finally:
        # Junction cleanup — `rmdir` on a junction removes the
        # junction only, not the target. Do this in a finally
        # so a failing assert doesn't leak the junction.
        subprocess.run(
            ["cmd", "/c", "rmdir", str(junction_path)],
            capture_output=True)

    paths = {f["path"] for f in data["files"]}
    for p in paths:
        assert "junctioned" not in p, (
            f"junction leaked into /files: {p}")
        assert "smuggled.md" not in p, (
            f"junction descendant leaked into /files: {p}")


# ── Cross-platform: symlink dir also rejected (belt/suspenders) ─

@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Cross-platform symlink test — Windows requires "
           "elevated privileges by default.",
)
def test_files_rejects_symlink_directory_on_posix(
        dashboard_fleet_mutable, tmp_path_factory):
    """POSIX equivalent of the junction test. A symlinked
    directory pointing outside the repo must be pruned before
    descent.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]

    external = tmp_path_factory.mktemp("symlink_target")
    (external / "external-leak.md").write_text(
        "must never appear\n", encoding="utf-8")

    symlink_path = alpha / ".gator" / "symlinked"
    try:
        os.symlink(str(external), str(symlink_path),
                   target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation failed: {exc}")

    try:
        _, data, _ = _get_json(fleet, "/api/repo/alpha/files")
    finally:
        try:
            os.unlink(str(symlink_path))
        except OSError:
            pass

    for f in data["files"]:
        assert "symlinked" not in f["path"], (
            f"symlink dir leaked into /files: {f}")
        assert "external-leak" not in f["path"], (
            f"symlink descendant leaked: {f}")


# ── F1 (2026-09-09 Codex finding) — in-repo reparse alias ──────
#
# Direct-route pins for the in-repo policy alias. The scanner
# already rejects reparse points, so /files discovery is clean.
# The bypass was via a GUESSED direct URL — `is_browsable` runs
# on the LOGICAL path, `_contained_repo_path` resolves through
# the alias, and the handler serves the aliased target. F1 fix
# walks the unresolved path from the namespace base rejecting
# any reparse-point component.

@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Junctions are Windows-only.",
)
def test_raw_rejects_in_repo_junction_alias(
        dashboard_fleet_mutable):
    """Create an in-repo junction that aliases into a protected
    namespace (`.gator/sessions/_active`). Direct URL request
    for the aliased path MUST NOT serve the protected content.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]

    # Namespace-root guard rejects `source/` prefixed by
    # `.gator/` or `gator-command/`, so the alias uses a
    # plausible-but-benign source-namespace directory name.
    junction_path = alpha / "public"
    target = alpha / ".gator" / "sessions" / "_active"
    r = subprocess.run(
        ["cmd", "/c", "mklink", "/J",
         str(junction_path), str(target)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        pytest.skip(
            f"mklink /J failed (permission?): {r.stderr!r}")

    try:
        status, body, _ = _get(
            fleet,
            "/api/repo/alpha/raw/source/public/token.json")
    finally:
        subprocess.run(
            ["cmd", "/c", "rmdir", str(junction_path)],
            capture_output=True)

    assert status == 404, (
        f"F1 alias bypass: {status} body={body!r}")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX symlink test — Windows path uses junctions.",
)
def test_raw_rejects_in_repo_symlink_alias(
        dashboard_fleet_mutable):
    """POSIX equivalent — an in-repo symlink aliasing into
    `.gator/sessions/_active` MUST NOT serve via `/raw`.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]

    symlink_path = alpha / "public"
    target = alpha / ".gator" / "sessions" / "_active"
    try:
        os.symlink(str(target), str(symlink_path),
                   target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation failed: {exc}")

    try:
        status, _, _ = _get(
            fleet,
            "/api/repo/alpha/raw/source/public/token.json")
    finally:
        try:
            os.unlink(str(symlink_path))
        except OSError:
            pass

    assert status == 404, (
        f"F1 alias bypass on POSIX: {status}")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX symlink test.",
)
def test_file_rejects_in_repo_symlink_alias(
        dashboard_fleet_mutable):
    """F1 companion for `/file` — the JSON envelope endpoint must
    also refuse to serve the aliased protected content.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]

    symlink_path = alpha / "public"
    target = alpha / ".gator" / "sessions" / "_active"
    try:
        os.symlink(str(target), str(symlink_path),
                   target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation failed: {exc}")

    try:
        status, _, _ = _get(
            fleet,
            "/api/repo/alpha/file/source/public/token.json")
    finally:
        try:
            os.unlink(str(symlink_path))
        except OSError:
            pass

    assert status == 404


# ── F3 (2026-09-09 Codex findings) — 404 error taxonomy ─────────
#
# The remediation caught the plan's §8b.3 taxonomy: live-read
# handlers must return 404 (not 500) on `FileNotFoundError` and
# `PermissionError` from `read_bytes()`.  Testing the branches
# splits into two problems:
#
# 1. `PermissionError`: deterministic on POSIX via `chmod 0`, which
#    lets `_contained_repo_path.resolve(strict=True)` and
#    `target.is_file()` both succeed while `read_bytes()` raises
#    `PermissionError`. That reaches the remediated branch.
#
# 2. `FileNotFoundError`: hard to hit deterministically because
#    `_contained_repo_path.resolve(strict=True)` catches the missing
#    file BEFORE `read_bytes()` runs. The two exception classes are
#    handled by the SAME `except (FileNotFoundError, PermissionError)`
#    clause, so the POSIX permission pin proves the branch works.
#    A source-grep pin below guards against silent removal of
#    `FileNotFoundError` from the clause.
#
# The prior tests named `test_*_concurrently_removed_returns_404`
# were renamed to reflect what they actually exercise (containment
# resolve → 404) and repurposed to preserve their taxonomy value.


def test_file_missing_target_returns_404_via_containment(
        dashboard_fleet_mutable):
    """A URL that names a missing file returns 404 through the
    `target is None` branch of `_contained_repo_path.resolve(strict=
    True)`. Not the `read_bytes` exception branch — this pin covers
    the containment-resolve path only.
    """
    fleet = dashboard_fleet_mutable
    status, _, _ = _get(
        fleet, "/api/repo/alpha/file/source/does_not_exist.py")
    assert status == 404


def test_raw_missing_target_returns_404_via_containment(
        dashboard_fleet_mutable):
    fleet = dashboard_fleet_mutable
    status, _, _ = _get(
        fleet, "/api/repo/alpha/raw/source/does_not_exist.py")
    assert status == 404


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX chmod-0 pattern; Windows permission model "
           "does not readily produce PermissionError from read.",
)
def test_file_unreadable_target_returns_404_on_posix(
        dashboard_fleet_mutable):
    """F3 branch pin: an existing but unreadable file makes
    `_contained_repo_path` succeed (parent readable, target
    exists, `is_file()` True) while `read_bytes()` raises
    `PermissionError` — reaching the remediated
    `except (FileNotFoundError, PermissionError)` branch in
    `_handle_file`. Response must be 404 (no oracle), not 500.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]
    target = alpha / "unreadable.py"
    target.write_text("secret\n", encoding="utf-8")
    os.chmod(str(target), 0)

    try:
        status, body, _ = _get(
            fleet, "/api/repo/alpha/file/source/unreadable.py")
    finally:
        try:
            os.chmod(str(target), 0o644)
        except OSError:
            pass

    assert status == 404, (
        f"F3 PermissionError branch failed: {status} body={body!r}")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX chmod-0 pattern.",
)
def test_raw_unreadable_target_returns_404_on_posix(
        dashboard_fleet_mutable):
    """F3 branch pin for `/raw`."""
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]
    target = alpha / "unreadable.py"
    target.write_text("secret\n", encoding="utf-8")
    os.chmod(str(target), 0)

    try:
        status, _, _ = _get(
            fleet, "/api/repo/alpha/raw/source/unreadable.py")
    finally:
        try:
            os.chmod(str(target), 0o644)
        except OSError:
            pass

    assert status == 404


def test_read_exception_clause_names_both_error_classes():
    """Source-grep guard: the F3 fix relies on catching BOTH
    `FileNotFoundError` and `PermissionError` before the general
    `OSError` clause in `_handle_file` and `_handle_raw`. Since
    `FileNotFoundError` is hard to hit deterministically at the
    read-bytes call site (containment resolve normally catches
    missing files first), this static pin guards against silent
    removal of either exception class from either clause.
    """
    from pathlib import Path as _Path
    src = (_Path(__file__).resolve().parents[2]
           / "src" / "gator_command" / "scripts"
           / "gator-dashboard.py").read_text(encoding="utf-8")
    # Both handlers must catch (FileNotFoundError, PermissionError)
    # BEFORE the general OSError branch.  The order matters:
    # PermissionError is an OSError subclass, so a bare OSError
    # first would swallow the 404 taxonomy.
    for handler_name in ("_handle_file", "_handle_raw"):
        # Locate the handler body.
        idx = src.find(f"def {handler_name}(self, req):")
        assert idx >= 0, f"missing handler {handler_name}"
        # Slice to the next handler def or ~5000 chars.
        body = src[idx:idx + 5000]
        specific_idx = body.find(
            "except (FileNotFoundError, PermissionError)")
        general_idx = body.find("except OSError")
        assert specific_idx >= 0, (
            f"{handler_name} missing "
            f"except (FileNotFoundError, PermissionError) clause")
        assert general_idx > specific_idx, (
            f"{handler_name}: specific clause must precede "
            f"general OSError so subclasses aren't swallowed")


def test_reparse_check_uses_python_3_9_compatible_stat():
    """F1 (2026-09-09 Codex re-review) source-grep: the reparse
    walker must NOT call `Path.stat(follow_symlinks=False)` — that
    kwarg is 3.10+ and would crash on the declared 3.9 floor. The
    fix routes Path/str objects through `os.stat(os.fspath(x),
    follow_symlinks=False)` and preserves the DirEntry cache-hit
    only when the input `isinstance(entry_or_path, os.DirEntry)`.
    """
    from pathlib import Path as _Path
    src = (_Path(__file__).resolve().parents[2]
           / "src" / "gator_command" / "scripts"
           / "gator-dashboard.py").read_text(encoding="utf-8")
    # Locate _is_reparse_point.
    idx = src.find("def _is_reparse_point(")
    assert idx >= 0
    body = src[idx:idx + 3000]
    # DirEntry branch must be gated on isinstance so a Path never
    # reaches the follow_symlinks= call.
    assert "isinstance(entry_or_path, os.DirEntry)" in body, (
        "_is_reparse_point must gate DirEntry-specific stat call "
        "behind isinstance so Path inputs don't hit the 3.10+ "
        "Path.stat(follow_symlinks=) kwarg on 3.9")


# ── F3 in-process branch pins (Codex 3rd-review LOW, 2026-09-09) ─
#
# The chmod-0 pins are POSIX-only AND can be bypassed by a
# privileged reader (root, container with DAC_OVERRIDE), and the
# `FileNotFoundError` branch is impossible to reach via filesystem
# state alone — `_contained_repo_path.resolve(strict=True)` catches
# missing files first. Solve both with cross-platform in-process
# tests that inject a faulty target through the `_contained_repo_path`
# seam so `target.is_file()` returns True while `target.read_bytes()`
# raises the exception. This deterministically reaches the
# remediated `except (FileNotFoundError, PermissionError)` clause
# on ANY platform, ANY Python version.


class _RecordingShim:
    """Minimum request-handler shim covering the surface both
    `_handle_file` and `_handle_raw` (and their delegatees
    `_send_json`, `_send_json_error`, `_raw_error_direct`,
    `_raw_error_from_req`) touch. Records status/headers/body so
    tests can assert exact 404 shapes.
    """

    def __init__(self):
        import io as _io
        self.wfile = _io.BytesIO()
        self.status_calls = []
        self.headers = []
        self.end_headers_calls = 0

    def send_response(self, status, message=None):
        self.status_calls.append((status, message))

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        self.end_headers_calls += 1


def _bind_all(dashboard_module, shim, names):
    """Bind unbound handler methods to the shim so `self.X()` works
    for every method the handler-under-test invokes.
    """
    Handler = dashboard_module.DashboardHandler
    for name in names:
        method = getattr(Handler, name)
        object.__setattr__(shim, name,
                           method.__get__(shim, Handler))


def _make_faulty_target(exception_cls):
    """Return a mock target that behaves like a real file
    ready to be read, then raises `exception_cls` on
    `read_bytes()`.  Also raises on `stat()` so `_mtime_iso`
    returns None (matches the JSON envelope shape for
    unreadable-mtime cases).
    """
    from unittest.mock import MagicMock
    m = MagicMock()
    m.is_file.return_value = True
    m.read_bytes.side_effect = exception_cls("test-induced")
    m.stat.side_effect = OSError("stat suppressed for test")
    return m


def _make_req(dashboard_module, endpoint, logical_path, *,
              version_present=False, version_value=""):
    return dashboard_module.Request(
        endpoint=endpoint,
        repo_name="alpha",
        logical_path=logical_path,
        version_present=version_present,
        version_value=version_value,
        query=({"version": [version_value]} if version_present
               else {}),
    )


def _install_stubs(dashboard_module, monkeypatch, target):
    """Patch `_contained_repo_path` to return `target` and
    `_resolve_repo_path` to return a benign non-empty value so
    both handlers reach the read step.
    """
    monkeypatch.setattr(
        dashboard_module, "_contained_repo_path",
        lambda *a, **kw: target)
    monkeypatch.setattr(
        dashboard_module, "_resolve_repo_path",
        lambda *a, **kw: "/synthetic/repo")


def _run_file_handler(dashboard_module, monkeypatch, exception_cls):
    target = _make_faulty_target(exception_cls)
    _install_stubs(dashboard_module, monkeypatch, target)
    shim = _RecordingShim()
    _bind_all(dashboard_module, shim,
              ("_send_json", "_send_json_error", "_handle_file"))
    req = _make_req(dashboard_module, "file", "source/x.py")
    shim._handle_file(req)
    return shim


def _run_raw_handler(dashboard_module, monkeypatch, exception_cls):
    target = _make_faulty_target(exception_cls)
    _install_stubs(dashboard_module, monkeypatch, target)
    shim = _RecordingShim()
    _bind_all(dashboard_module, shim,
              ("_send_json", "_send_json_error",
               "_raw_error_direct", "_raw_error_from_req",
               "_handle_raw"))
    req = _make_req(dashboard_module, "raw", "source/x.py")
    shim._handle_raw(req)
    return shim


def test_file_permission_error_branch_returns_404(
        dashboard_module, monkeypatch):
    """F3 in-process branch pin — `PermissionError` on `read_bytes`
    (after containment succeeds) MUST return 404 JSON envelope
    from `_handle_file`. Cross-platform; not dependent on
    filesystem permissions or platform.
    """
    shim = _run_file_handler(
        dashboard_module, monkeypatch, PermissionError)
    assert shim.status_calls == [(404, None)]
    body = json.loads(shim.wfile.getvalue().decode("utf-8"))
    assert body == {"error": "not found", "code": 404}
    values = dict(shim.headers)
    assert values["Content-Type"] == (
        "application/json; charset=utf-8")


def test_file_file_not_found_branch_returns_404(
        dashboard_module, monkeypatch):
    """F3 in-process branch pin — `FileNotFoundError` on
    `read_bytes` (containment already succeeded; the file was
    concurrently removed) MUST return 404 from `_handle_file`.
    This is the branch that filesystem state cannot reach
    deterministically.
    """
    shim = _run_file_handler(
        dashboard_module, monkeypatch, FileNotFoundError)
    assert shim.status_calls == [(404, None)]
    body = json.loads(shim.wfile.getvalue().decode("utf-8"))
    assert body == {"error": "not found", "code": 404}


def test_file_general_oserror_stays_500(
        dashboard_module, monkeypatch):
    """Complementary pin — a non-FileNotFoundError,
    non-PermissionError `OSError` still returns 500 (the
    remediation preserved the general branch).
    """
    shim = _run_file_handler(
        dashboard_module, monkeypatch, OSError)
    assert shim.status_calls == [(500, None)]


def test_raw_permission_error_branch_returns_404(
        dashboard_module, monkeypatch):
    """F3 in-process branch pin — `PermissionError` on
    `read_bytes` MUST return 404 HTML envelope from
    `_handle_raw` (via `_raw_error_from_req` → `_raw_error_direct`).
    """
    shim = _run_raw_handler(
        dashboard_module, monkeypatch, PermissionError)
    assert shim.status_calls == [(404, "not found")]
    values = dict(shim.headers)
    assert values["Content-Type"] == "text/html;charset=utf-8"
    assert values["X-Content-Type-Options"] == "nosniff"


def test_raw_file_not_found_branch_returns_404(
        dashboard_module, monkeypatch):
    """F3 in-process branch pin — `FileNotFoundError` on
    `read_bytes` MUST return 404 from `_handle_raw`.
    """
    shim = _run_raw_handler(
        dashboard_module, monkeypatch, FileNotFoundError)
    assert shim.status_calls == [(404, "not found")]


def test_raw_general_oserror_stays_500(
        dashboard_module, monkeypatch):
    """Complementary pin for `_handle_raw` — non-remediated
    `OSError` subclasses still surface as 500.
    """
    shim = _run_raw_handler(
        dashboard_module, monkeypatch, OSError)
    assert shim.status_calls == [(500, "read failed: test-induced")]


def test_reparse_check_uses_os_stat_for_path_inputs(
        dashboard_module, tmp_path):
    """F1 functional pin: for Path inputs, `_is_reparse_point` must
    route the second stat call (after `is_symlink()`) through
    `os.stat(os.fspath(path), follow_symlinks=False)` — a 3.3+ API
    — NOT through `Path.stat(follow_symlinks=False)` which is 3.10+
    and would crash on the declared 3.9 floor with `TypeError`.

    Observe by recording every `os.stat` call inside the helper.
    Note: `Path.is_symlink()` on 3.13 internally calls `Path.stat`
    with the kwarg, but on 3.9 it uses `os.lstat` directly — so
    mocking `Path.stat` breaks the 3.13 test path. Recording
    `os.stat` calls avoids the version-specific `is_symlink()`
    plumbing and directly proves the fix contract: the fallback
    stat for Path inputs uses the 3.3+ `os.stat` call.
    """
    import os as _os
    from unittest import mock

    ordinary_file = tmp_path / "regular.py"
    ordinary_file.write_text("x = 1\n", encoding="utf-8")

    original_os_stat = _os.stat
    calls = []

    def _record_stat(*args, **kwargs):
        calls.append((args, kwargs))
        return original_os_stat(*args, **kwargs)

    with mock.patch.object(_os, "stat", _record_stat):
        result = dashboard_module._is_reparse_point(ordinary_file)

    assert result is False
    # For a Path input the helper must invoke os.stat with
    # follow_symlinks=False at least once — the 3.9-safe path.
    fspath_str = str(ordinary_file)
    matched = [
        (a, kw) for (a, kw) in calls
        if a and str(a[0]) == fspath_str
        and kw.get("follow_symlinks") is False]
    assert matched, (
        "expected _is_reparse_point to call "
        "os.stat(os.fspath(path), follow_symlinks=False) for "
        f"Path input; recorded calls: {calls}")
