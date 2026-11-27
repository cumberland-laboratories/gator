"""Scaffolding cleanup — authoring templates leave the folders people browse.

Since #109, a folder's `_template.md` lives in managed space
(`.gator/.includes/<folder>/`), and the rarely used folders (`threads/`,
`active-threads/`, `policies/`, `field-guides/`, and the user
`reference-notes/`) exist only once someone puts content in them; their
README lives in `.includes/` too. This module plans and applies the
one-time removal of what earlier Gator versions left at the user-visible
root of a v2 repository:

  - every `.gator/<folder>/_template.md`;
  - in an on-demand folder that holds nothing else, its `README.md` and
    `.gitkeep`, and then the empty folder.

Gator shipped and refreshed all of these files (`gator update` overwrote
them on every run), so removing them loses nothing; the managed copies
replace them. A folder with any other file is kept. `gator update` reaches
these functions through its `gatorize` sibling import, like the vendor
cleanup. Staging rule: a tracked file is removed with `git rm` (deletion
staged for the operator to commit); an untracked one is unlinked.
"""

import subprocess
from pathlib import Path

SCAFFOLD_DIRS = (
    "charters", "artifacts", "procedures", "blueprints",
    "reference-notes", "threads", "active-threads", "policies", "field-guides",
)
ON_DEMAND_DIRS = frozenset({
    "reference-notes", "threads", "active-threads", "policies", "field-guides",
})
_GATOR_OWNED_IN_ON_DEMAND = frozenset({"README.md", "_template.md", ".gitkeep"})


def _is_tracked(repo_root, rel):
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", "--", rel],
            capture_output=True, text=True)
    except OSError:
        return False
    return result.returncode == 0


def plan_scaffold_cleanup(repo_root):
    """Read-only. The exact removals, sorted by path:
    [{"path", "action": "delete", "tracked"}]. [] on a v1 layout (no
    `.gator/.includes/`), where shipped content still lives at the root."""
    repo_root = Path(repo_root)
    gator = repo_root / ".gator"
    if not (gator / ".includes").is_dir():
        return []
    rels = []
    for name in SCAFFOLD_DIRS:
        folder = gator / name
        if not folder.is_dir():
            continue
        if (folder / "_template.md").is_file():
            rels.append(f".gator/{name}/_template.md")
        if name in ON_DEMAND_DIRS:
            try:
                entries = list(folder.iterdir())
            except OSError:
                continue
            if all(e.is_file() and e.name in _GATOR_OWNED_IN_ON_DEMAND for e in entries):
                for e in entries:
                    if e.name != "_template.md":
                        rels.append(f".gator/{name}/{e.name}")
    return [{"path": rel, "action": "delete", "tracked": _is_tracked(repo_root, rel)}
            for rel in sorted(rels)]


def apply_scaffold_cleanup(repo_root, actions):
    """Apply exactly the planned deletions; returns the applied actions.
    Then removes each on-demand folder that is left empty on disk."""
    repo_root = Path(repo_root)
    applied = []
    for action in actions:
        if action.get("action") != "delete":
            continue
        rel = action["path"]
        path = repo_root / rel
        try:
            if action.get("tracked"):
                # -f: these files were Gator's; a local edit must not abort
                # the update (gator update overwrote them on every run).
                subprocess.run(["git", "-C", str(repo_root), "rm", "-q", "-f", "--", rel],
                               check=True, capture_output=True)
            elif path.is_file():
                path.unlink()
            else:
                continue
        except (OSError, subprocess.CalledProcessError):
            continue
        applied.append(dict(action))
    if applied:
        for name in ON_DEMAND_DIRS:
            folder = repo_root / ".gator" / name
            try:
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
            except OSError:
                pass
    return applied


def format_scaffold_cleanup(actions, predicted=False):
    """Human lines for a planned (`predicted`) or applied cleanup."""
    if not actions:
        return []
    head = ("  Scaffolding Gator will remove (templates now live in .gator/.includes/):"
            if predicted else
            "  Scaffolding Gator removed (templates now live in .gator/.includes/):")
    lines = [head]
    for action in actions:
        staged = action.get("tracked") and not predicted
        lines.append(f"    - {action['path']}" + (" (deletion staged)" if staged else ""))
    return lines
