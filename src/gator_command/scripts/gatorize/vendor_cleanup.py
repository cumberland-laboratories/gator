"""Repository vendor cleanup — Gator keeps no AI-tool files in repositories.

Gator's session hooks now live in each AI tool's user-level settings (see
`machine_integration.py`), and its four slash commands are retired. This
module plans and applies the one-time removal of what earlier Gator
versions put into a repository:

  - Gator's hook entries in `.claude/settings.json`, `.codex/hooks.json`
    and `.gemini/settings.json` (a closed list);
  - the four Gator command files in `.claude/commands/`, only when their
    content is a version Gator shipped (`RETIRED_COMMANDS`).

User-owned content stays: other hooks and settings, a command file the
user edited, `.claude/settings.local.json`. `gator update` reaches these
functions through its `gatorize` sibling import (the #78 seam).

Staging rule: a file that was wholly Gator's is deleted (`git rm` when
tracked, so the deletion is staged); a file that also holds user content
is rewritten without Gator's entries and left unstaged for review.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from machine_integration import (  # noqa: E402
    _Malformed, _atomic_write_json, _read_json, strip_managed_entries,
)

ELIGIBLE_SETTINGS = (".claude/settings.json", ".codex/hooks.json",
                     ".gemini/settings.json")

# SHA-256 of every shipped version of each retired command, content
# normalized to "\n" line endings. Computed once (2026-11-11) from the
# history of `templates/gator-starter/commands/<name>.md` in this
# repository (`git log --all --follow`) and of `*commands/<name>.md` in the
# pre-monorepo repositories (gator-command, gator-legacy-pre-monorepo):
# 36 versions. Content matching none of these is user-owned.
RETIRED_COMMANDS = {
    ".claude/commands/init.md": frozenset({
        "075778da81ea9d7a99d7f2deb24ddc91054722ec997607435f59bc7a425a7e2b",
        "60369c33c19bb5f3af06559323635eec1b14f4f1a9dec618f99649c5efe82406",
        "6875697eec1ce8d53738c42da14efc839af0d7f3afa17ea1022ee064e986d3af",
        "78b084dd1d9baa62f1d20a41b8b16de2bbd22184b64990c7546d0f747ece503c",
        "abed20bc796a6abc41382591b311d1332ae5552c5141a8bbe45c797f9f982e6a",
        "cabb4da80e417a01d98ae26ad9521ac8329e610f812f7688e02aab19c03a87a7",
        "e694f1f5bb4bf1ba21e047c1b1908474bb81c2875d383536996faad4c5f5909c",
        "f21db482da4de917e957c37573c318a8737c27c9edc8b3d31b8ac2c7b787c5b7",
    }),
    ".claude/commands/update.md": frozenset({
        "58d29fa1d710b344248d2e2beefee86629a2cc45ad345f99a42103305e2bcaf1",
        "9aef214a2937422393457d2e92060e59057ed343ddc0ee6a951c6dc373cf33af",
        "bc4a3c33f5aa234c5034cb9cee52e968194475d3ba25cd2e871ffb8e982b3a26",
        "e3d5895aab0aa4fd60e8d4c21e7cd51ecf07c9aafa8ff2f61ae6b81de456ea1e",
    }),
    ".claude/commands/commit.md": frozenset({
        "0b3ae568cda8a978acadddc7b964a21ba069cccb4bdb23ef9ae2be7a77692df6",
        "0cbd55589170577f29a76329b13debe891a2003fa9d0528d91486e485bc2f0db",
        "19fd9216322527d803f613769e11f59e14b430a5efafdc7dacb9486d2112eb08",
        "6dfbadc85de097716042cb8dd82ba217165edee498e037cedb7778040b99c1b1",
        "8a18f46c6566a1445801292db084390d75feb18e20c5cfb9c20540a4b8882bc1",
        "b4eda1cc3814a96ade86e017384b7344634277a64bdf3072cdd892e494dda626",
        "b63b2730109fc35fe0c70d6d6e73f15e4da9ebac4e58e44ca663ec40e30472d9",
        "c41e30cd4cfae211db3621672197ef18774a328a7562f7c92ab19e064454e1de",
        "e0522bfe8c1a898adddcb3f49e052842ebd9ef57cd2c716f23db35f0732df892",
        "fab213523f2baa431626b24e69092c29d48c8e9288bc323d8dae02729ac58109",
    }),
    ".claude/commands/loop-join.md": frozenset({
        "01719a619414382931cdcdb3bd40a544ef82ea54f24db77451f16e89715afb71",
        "24d39d398534b2458c21fac41a72c7bef6bca2dfe8684489b56d35e660a2f4c9",
        "2d5ce01800d31ae34a3a2f058e69d0bf88904c506abe11f76a1d583b254bb427",
        "39a4e716e789909022709909d4d9ec1e03bb3c3ccfe392354596270ecfee6bfb",
        "3eaccfa43ea8cbfb4571b77a37cb983f71f84a8e34c09765759b92dd5acb1cec",
        "442bf4bd5977d351ed616d7714c3aacdac1a088ebc4952e2c2d00e786d6be137",
        "5b09f02b531925d2757cbb9a28dffd361ed942c8e38ad5927b654838f28867a1",
        "647a9905cd58d7e949e11329b2842fa8f87d34419263d63b3da1bb0e04a33b38",
        "9f07ae91e58e66e469a7da02c985d3a4242c51fb231d96ce28efb46d2b8753ea",
        "ccf3860b571f97fe5674a945d505efd69e2b5889445ffac8fac07df78e0c91bd",
        "da2ad909cea3429d2b1491453c9f856f0c1ca7c0d228368b508ff83b4bb60302",
        "e35d9a186394ea97436053b3e3fb29aadeeec0f3b48a1a6e1c32906a55b8631a",
        "eb3a4cf7f6520103fbf0ae4e9a3975a4f59752280c89d13e2fe0d690db944694",
        "eec31f9276f8328f5e28356ab7262539e93b5a9222fe4665bfb215c491734836",
    }),
}

_EMPTY_DIRS = (".claude/commands", ".claude", ".codex", ".gemini")


def _digest(path):
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _is_tracked(repo_root, rel):
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", "--", rel],
            capture_output=True, text=True)
    except OSError:
        return False
    return result.returncode == 0


def plan_vendor_cleanup(repo_root):
    """Read-only. Returns the exact actions, sorted by path:
    [{"path", "action": "delete"|"strip"|"user-owned", "tracked"}].
    `user-owned` is a note for reporting; it is never applied."""
    repo_root = Path(repo_root)
    actions = []
    for rel in ELIGIBLE_SETTINGS:
        path = repo_root / rel
        if not path.is_file():
            continue
        status, doc = _read_json(path)
        if status != "ok":
            continue
        try:
            stripped, removed = strip_managed_entries(doc)
        except _Malformed:
            continue
        if not removed:
            continue
        action = "delete" if stripped == {} else "strip"
        actions.append({"path": rel, "action": action,
                        "tracked": _is_tracked(repo_root, rel)})
    for rel, digests in RETIRED_COMMANDS.items():
        path = repo_root / rel
        if not path.is_file():
            continue
        try:
            shipped = _digest(path) in digests
        except OSError:
            continue
        actions.append({"path": rel,
                        "action": "delete" if shipped else "user-owned",
                        "tracked": _is_tracked(repo_root, rel)})
    return sorted(actions, key=lambda a: a["path"])


def apply_vendor_cleanup(repo_root, actions):
    """Apply exactly the delete/strip actions given; returns them.

    delete + tracked → `git rm` (deletion staged); delete + untracked →
    unlink; strip → rewritten without Gator's entries, left unstaged.
    Then removes `.claude/commands/`, `.claude/`, `.codex/`, `.gemini/`
    when they are empty on disk."""
    repo_root = Path(repo_root)
    applied = []
    for action in actions:
        rel, kind = action["path"], action["action"]
        path = repo_root / rel
        if kind == "delete":
            if action.get("tracked"):
                # -f: the plan already found the working copy wholly Gator's,
                # so a local modification (for example an edited timeout)
                # must not abort the update.
                subprocess.run(["git", "-C", str(repo_root), "rm", "-q", "-f", "--", rel],
                               check=True, capture_output=True)
            else:
                path.unlink()
        elif kind == "strip":
            status, doc = _read_json(path)
            if status != "ok":
                continue
            doc, _ = strip_managed_entries(doc)
            _atomic_write_json(path, doc)
        else:
            continue
        applied.append(dict(action))
    if applied:
        for rel in _EMPTY_DIRS:
            folder = repo_root / rel
            try:
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
            except OSError:
                pass
    return applied


def format_vendor_cleanup(actions, predicted=False):
    """Human lines for a planned (`predicted`) or applied cleanup."""
    if not actions:
        return []
    head = ("  AI-tool files Gator will remove (now kept per machine):"
            if predicted else "  AI-tool files Gator removed (now kept per machine):")
    lines = [head]
    for action in actions:
        rel, kind = action["path"], action["action"]
        if kind == "delete":
            lines.append(f"    - {rel}" + (" (deletion staged)"
                                             if action.get("tracked") and not predicted else ""))
        elif kind == "strip":
            lines.append(f"    ~ {rel}: Gator's hooks "
                         + ("will be removed" if predicted else "removed")
                         + "; your entries stay — review and commit")
        elif kind == "user-owned":
            lines.append(f"    = {rel}: left in place (user-edited)")
    return lines
