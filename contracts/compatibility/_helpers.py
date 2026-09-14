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


# ── Pinned Cumberland Content-Security-Policy ────────────────────
#
# Shared between `test_cumberland_visual_invariants.py` (validates
# the shipped templates carry it) and `test_cumberland_computed_style.py`
# (builds fixtures that exercise the Layer 2 boundary against
# forbidden CSS shapes). Kept HERE — a single source of truth — so
# the two modules can never drift; a hand-edited fixture in one
# module would exercise a policy no template carries, giving a
# green boundary test against a phantom guarantee (Codex round-13
# LOW).
#
# Round-14 F2 addition (2026-09-14).

PINNED_CSP_CONTENT = (
    "default-src 'none'; style-src 'unsafe-inline'; "
    "script-src 'none'; img-src 'none'; font-src 'none'; "
    "frame-src 'none'; object-src 'none'; base-uri 'none'; "
    "form-action 'none'"
)


def pinned_csp_meta_string() -> str:
    """Compose the full `<meta http-equiv=...>` string authors paste
    into templates. Kept in ONE place so the pinned content and the
    meta-string never drift."""
    return (
        '<meta http-equiv="Content-Security-Policy" '
        f'content="{PINNED_CSP_CONTENT}">'
    )
