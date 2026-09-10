"""B1 content-transport seed extension (Slice 2).

Registers `seed_content_fixtures` (files staged into the initial
seed commit) and `seed_history_commits` (post-seed edits + delete
commits) on the harness module. Import at module scope from
`conftest.py` so the reassignment lands BEFORE any fixture builds
the fleet.

Repositories built via `build_dashboard_fleet` will have:

- `.gator/mission.md` — from the shipped stub seed. Additionally
  overwritten in the `mission-r2` post-seed commit so
  `?version=<seed>` sees the initial body and `?version=<HEAD>`
  sees the second body.
- `.gator/blueprints/sample.svg` — SVG source (governance
  namespace text extension per r3 F6).
- `.gator/blueprints/hero.png` — PNG raw asset in governance
  namespace.
- `.gator/sessions/_active/token.json` — MUST NEVER appear in
  `/files` responses.
- `.gator/.override-approved.json` — hidden override internal;
  MUST NEVER be listed.
- `gator-command/README.md` — governance secondary namespace.
- `source/example.py` — canonical source file at repo root.
- `source/private.pem` — secret material, MUST NEVER be listed.
- `source/.env.local` — secret material, MUST NEVER be listed.
- Post-seed commits recorded in the `commits` map:
  - `mission-r2`: overwrite `.gator/mission.md` body.
  - `gc-deleted`: fully remove `gator-command/` (history for
    files inside it must still be returnable via `/history/`).
"""

import shutil
import subprocess
from pathlib import Path

from . import _harness as _h


# ── B2 Slice 2 (v2.13.0) fixture surfaces ─────────────────────────
#
# `_csp_negative_control.html` — a deliberately incompatible HTML
# file that violates three distinct CSP directives at load time:
#     - style-src-elem (external <link rel="stylesheet">)
#     - img-src        (cross-origin <img src>)
#     - connect-src    (cross-origin fetch())
# Used by the mandatory Playwright detector-liveness pin in
# `test_html_preview.py` to prove the CSP violation listener is
# actually installed and reporting events. Host is
# `https://example.invalid/` — an IANA-reserved TLD that never
# resolves, so no accidental real-network traffic even if a future
# test relaxes CSP during debugging.
_CSP_NEGATIVE_CONTROL_HTML = (
    "<!DOCTYPE html>\n"
    "<html>\n"
    "<head>\n"
    "<title>CSP negative control</title>\n"
    "<!-- style-src-elem violation: external stylesheet -->\n"
    "<link rel=\"stylesheet\" href=\"https://example.invalid/x.css\">\n"
    "</head>\n"
    "<body>\n"
    "<!-- img-src violation: cross-origin image -->\n"
    "<img src=\"https://example.invalid/x.png\" alt=\"probe\">\n"
    "<!-- connect-src violation: cross-origin fetch -->\n"
    "<script>\n"
    "fetch(\"https://example.invalid/api\").catch(function () {});\n"
    "</script>\n"
    "</body>\n"
    "</html>\n"
)


def _repo_root():
    """Walk up from this file to the repo root (containing `.gator/`)."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / ".gator").is_dir():
            return parent
    return None


def _copy_shipped_blueprints(repo):
    """B2 Slice 2 (v2.13.0) fixture helper (per r14 §M2).

    Copies every `*.html` file under `.gator/blueprints/` and
    `src/gator_command/templates/gator-starter/blueprints/` in the
    source checkout into the test repo pre-seed commit, so the
    Playwright CSP-compat pin can GET each via `/raw/`.

    Disk destinations chosen so each namespace's canonical URL
    prefix under B1 is `blueprints/shipped/<name>` (implicit
    `.gator` prefix) and `gator-command/shipped-templates/<name>`
    (explicit `gator-command` prefix). The r14 §M1 seed→URL
    mapping table records both.

    Silently skips when the source checkout is not present (e.g.
    running from an installed wheel). Degraded coverage rather
    than hard fail; the compat pin becomes a skip in that case.
    """
    root = _repo_root()
    if root is None:
        return

    # `.gator/blueprints/*.html` → `<test-repo>/.gator/blueprints/shipped/`
    src_gator = root / ".gator" / "blueprints"
    if src_gator.is_dir():
        dst_gator = repo / ".gator" / "blueprints" / "shipped"
        dst_gator.mkdir(parents=True, exist_ok=True)
        for src_file in sorted(src_gator.glob("*.html")):
            assert src_file.suffix == ".html", src_file
            shutil.copy2(str(src_file),
                         str(dst_gator / src_file.name))

    # `src/gator_command/templates/gator-starter/blueprints/*.html`
    #   → `<test-repo>/gator-command/shipped-templates/`
    src_pkg = (
        root / "src" / "gator_command" / "templates"
        / "gator-starter" / "blueprints"
    )
    if src_pkg.is_dir():
        dst_pkg = repo / "gator-command" / "shipped-templates"
        dst_pkg.mkdir(parents=True, exist_ok=True)
        for src_file in sorted(src_pkg.glob("*.html")):
            assert src_file.suffix == ".html", src_file
            shutil.copy2(str(src_file),
                         str(dst_pkg / src_file.name))


def seed_content_fixtures(repo):
    """Extra fixture files landed in the initial seed commit."""
    (repo / ".gator" / "blueprints").mkdir()
    (repo / ".gator" / "blueprints" / "sample.svg").write_text(
        '<?xml version="1.0"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" '
        'height="10"><rect width="10" height="10"/></svg>\n',
        encoding="utf-8")
    (repo / ".gator" / "blueprints" / "hero.png").write_bytes(
        # Minimal valid 1×1 PNG.
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108"
            "060000001f15c4890000000d49444154789c62000100000005"
            "00010d0a2db40000000049454e44ae426082"))

    active = repo / ".gator" / "sessions" / "_active"
    active.mkdir(parents=True)
    (active / "token.json").write_text(
        '{"secret": "must-not-leak"}\n', encoding="utf-8")

    (repo / ".gator" / ".override-approved.json").write_text(
        '{"approved": true}\n', encoding="utf-8")

    # B2 Slice 2 (v2.13.0) — CSP negative-control fixture for
    # the mandatory Playwright detector-liveness pin. See
    # `_CSP_NEGATIVE_CONTROL_HTML` module constant above.
    (repo / ".gator" / "blueprints"
        / "_csp_negative_control.html").write_text(
            _CSP_NEGATIVE_CONTROL_HTML, encoding="utf-8")

    gc = repo / "gator-command"
    gc.mkdir()
    (gc / "README.md").write_text(
        "# gator-command README\n", encoding="utf-8")

    # B2 Slice 2 (v2.13.0) — copy every shipped HTML blueprint
    # (both audit roots) into the test repo so the Playwright
    # CSP-compat pin has real bytes to load. See
    # `_copy_shipped_blueprints` docstring for the seed→URL
    # mapping.
    _copy_shipped_blueprints(repo)

    (repo / "example.py").write_text(
        "def hello():\n    return 'world'\n", encoding="utf-8")
    # `.pem` suffix is what the denylist matches. Body is a
    # placeholder — no real key material — because `SEC-003`
    # scans for `BEGIN <TYPE> KEY` fingerprints in tracked files.
    (repo / "private.pem").write_text(
        "placeholder secret material\n", encoding="utf-8")
    (repo / ".env.local").write_text(
        "SECRET_TOKEN=must-not-leak\n", encoding="utf-8")


def seed_history_commits(repo, name):
    """Post-seed commits so version-scoped tests have inspectable
    history. Returns a `{label: sha}` map merged into the fleet
    fixture's `commits`.

    F4 fixture split (2026-09-09 Codex finding): only `alpha`
    deletes `gator-command/` so the deleted-file `/history/` pin
    has a repo to exercise. `beta` preserves `gator-command/`
    intact so the live E1 wire-schema pin has a positive
    `source == "gator-command"` case to assert.
    """
    def _git(*args):
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True, capture_output=True)

    def _rev():
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True)
        return out.stdout.strip()

    (repo / ".gator" / "mission.md").write_text(
        f"# {name} mission — r2\n\nRevised body.\n",
        encoding="utf-8")
    _git("add", "-A")
    _git("commit", "-q", "-m", "mission r2")
    mission_r2 = _rev()

    result = {"mission-r2": mission_r2}
    if name == "alpha":
        import shutil
        shutil.rmtree(repo / "gator-command")
        _git("add", "-A")
        _git("commit", "-q", "-m", "remove gator-command/")
        result["gc-deleted"] = _rev()
    return result


_h.seed_content_fixtures = seed_content_fixtures
_h.seed_history_commits = seed_history_commits
