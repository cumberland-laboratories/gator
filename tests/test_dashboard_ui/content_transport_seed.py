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

import subprocess

from . import _harness as _h


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

    gc = repo / "gator-command"
    gc.mkdir()
    (gc / "README.md").write_text(
        "# gator-command README\n", encoding="utf-8")

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
