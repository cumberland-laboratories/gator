#!/usr/bin/env python3
"""
gator --explain — orient an AI session that has no governed repository.

Prints a short fixed introduction, the installed paths of the shipped
Welcome documents to read (in order), and a live "Where you are" section:
installed version, whether the working directory is a governed repository,
the governed repositories registered on this machine, and what to do next.

It never writes anything. The documents are the same files the Dashboard
serves; nothing here is a second copy to maintain.

@reads: templates/gator-starter/docs/*.html (paths only), ~/.gator/dashboard-repos.json, git
@writes: stdout only
"""

import sys
from pathlib import Path

from gator_core import (
    ensure_utf8_stdout, find_gator_root, get_version, git, read_dashboard_registry,
)

SCRIPTS_DIR = Path(__file__).resolve().parent
DOCS_DIR = SCRIPTS_DIR.parent / "templates" / "gator-starter" / "docs"

# Reading order (Architect, 2026-11-09). start-a-session.html is left out on
# purpose: the session-opening prompt the user pasted comes from that page.
READING_ORDER = (
    ("gator-overview.html", "Gator overview"),
    ("gatorize-a-repo.html", "Gatorize a repo"),
    ("what-gator-can-do.html", "What Gator can do"),
)

INTRO = (
    "Gator is a Git-native semantic layer for AI-assisted engineering. It gives "
    "coding agents a reviewed map of each repository (charters), checks at commit "
    "time that the map and the code stay in step, and keeps the human Architect in "
    "charge of decisions. If your session was told to run `gator init` and it found "
    "no governed repository, read the documents below, then use \"Where you are\" "
    "to decide what to do next."
)


def _governed_repos():
    """Registered repositories that are governed roots themselves.

    Uses `find_gator_root()`, so the machine-state rule is the same one every
    Gator command applies: ~/.gator/ never makes home a repository.
    """
    repos = []
    for entry in read_dashboard_registry():
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            continue
        path = Path(entry["path"])
        try:
            root = find_gator_root(str(path)) if path.is_dir() else None
            if root and Path(root).resolve() == path.resolve():
                repos.append((entry.get("name") or path.name, path))
        except OSError:
            continue
    return repos


def where_you_are(cwd):
    """The live situation lines and the next step, as plain text lines."""
    lines = [f"  Gator version: {get_version()}", f"  Working directory: {cwd}"]
    top, in_git = git("rev-parse", "--show-toplevel", cwd=str(cwd))
    root = find_gator_root(str(cwd))
    if root:
        lines.append(f"  Governed repository: {root}")
        lines += ["", "  Next: run `gator init` here and follow its session-opening reads."]
        return lines
    if in_git and top:
        lines.append(f"  Git repository: {top} (not governed by Gator)")
    else:
        lines.append("  Not inside a Git repository.")
    repos = _governed_repos()
    if repos:
        lines += ["", "  Governed repositories on this machine:"]
        lines += [f"    - {name}: {path}" for name, path in repos]
        lines += ["", "  Next: ask the Architect which repository to work in, change to it, "
                      "and run `gator init` there."]
    else:
        lines += ["", "  No governed repositories are registered on this machine."]
        lines += ["", "  Next: tell the Architect. Gatorizing a repository is the Architect's "
                      "decision (`gator gatorize <path>`)."]
    if in_git and top:
        lines.append("  This Git repository can be gatorized only if the Architect decides so.")
    return lines


def render(cwd=None):
    cwd = Path(cwd or Path.cwd()).resolve()
    out = ["", "  Gator — orientation for an AI session", "", f"  {INTRO}", "",
           "  Read these documents, in order:"]
    for i, (name, title) in enumerate(READING_ORDER, 1):
        path = DOCS_DIR / name
        note = "" if path.is_file() else "  (missing from this install)"
        out.append(f"    {i}. {title}: {path}{note}")
    out += ["", "  Where you are:"] + where_you_are(cwd) + [""]
    return "\n".join(out)


def main():
    ensure_utf8_stdout()
    print(render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
