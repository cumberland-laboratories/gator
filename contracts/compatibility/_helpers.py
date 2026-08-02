"""Non-conftest helpers for the contracts compatibility suite.

Kept out of conftest.py because pytest collection can put multiple
conftest.py modules on sys.path with the same short name — importing
plain functions across suites via `from conftest import ...` collides.
Fixtures are safe in conftest.py because pytest resolves them by scope,
not by import path.
"""
from __future__ import annotations


def parse_frontmatter(md_text: str) -> tuple[dict, str]:
    """Parse `---` YAML frontmatter from a markdown document.

    Returns (frontmatter_dict, body). Values are kept as raw strings —
    the contracts layer verifies key presence and canonical values,
    not typed YAML semantics.
    """
    lines = md_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, md_text

    fm: dict[str, str] = {}
    body_start = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = i + 1
            break
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    if body_start is None:
        return fm, ""
    return fm, "\n".join(lines[body_start:])
