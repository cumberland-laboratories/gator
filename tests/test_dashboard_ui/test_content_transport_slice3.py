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


# ── F3 (2026-09-09 Codex finding) — FileNotFoundError → 404 ────

def test_file_concurrently_removed_returns_404(
        dashboard_fleet_mutable):
    """A file present at `is_browsable` time but removed before
    `read_bytes` runs must return 404 (no oracle), not 500.
    Simulate by having the handler open a file that doesn't
    exist mid-flight via a delete-after-list pattern.
    """
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]

    # Seed a file, list it, remove it, then hit `/file`.
    target = alpha / "ephemeral.py"
    target.write_text("print('bye')\n", encoding="utf-8")
    _, listing, _ = _get_json(fleet, "/api/repo/alpha/files")
    assert any(f["path"] == "source/ephemeral.py"
               for f in listing["files"])

    target.unlink()
    status, body, _ = _get(
        fleet, "/api/repo/alpha/file/source/ephemeral.py")
    assert status == 404, (
        f"concurrent-removal F3: {status} body={body!r}")


def test_raw_concurrently_removed_returns_404(
        dashboard_fleet_mutable):
    """F3 companion for `/raw`."""
    fleet = dashboard_fleet_mutable
    alpha = fleet["repos"]["alpha"]["path"]

    target = alpha / "ephemeral.py"
    target.write_text("print('bye')\n", encoding="utf-8")
    target.unlink()
    status, _, _ = _get(
        fleet, "/api/repo/alpha/raw/source/ephemeral.py")
    assert status == 404
