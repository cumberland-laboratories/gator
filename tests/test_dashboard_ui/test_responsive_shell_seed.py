"""Plan C Slice 3 seed extension (v2.13.0).

Registers `seed_sidebar_fixtures` on the harness so every repo
built via `build_dashboard_fleet` gains the fixtures Slice 3's pins
need. Imported at module scope from `conftest.py` so the
reassignment lands BEFORE any fixture builds the fleet.

Fixtures landed:

- `.gator/artifacts/many/f00.md` … `f79.md` — 80 short files
  under a nested subdirectory. Exercises the expanded-sidebar
  scroll-overflow pin (`test_expanded_sidebar_scrolls_long_file_tree`).
  Only `section:gator` is default-expanded per `views/repo.js`, so
  `artifacts/` and `many/` are collapsed at mount; the pin
  explicitly expands both to render the 80 rows.
- `.gator/artifacts/long.md` — a Markdown file long enough to
  overflow `.repo-markdown`'s clientHeight, for the Repo-view
  markdown-scroll pin. (The Docs view no longer reads repositories,
  2026-10-13, so the former `.gator/docs/long-docs.md` is gone.)
"""

from . import _harness as _h


def seed_sidebar_fixtures(repo):
    """80 files under .gator/artifacts/many/ (sidebar-overflow pin),
    long docs file (Docs-view scroll pin), long.md (Repo-view
    markdown-scroll pin).
    """
    # 80 nested files for sidebar-overflow.
    (repo / ".gator" / "artifacts").mkdir(exist_ok=True)
    (repo / ".gator" / "artifacts" / "many").mkdir()
    for i in range(80):
        (repo / ".gator" / "artifacts" / "many" / f"f{i:02d}.md"
         ).write_text(f"# entry {i:02d}\n", encoding="utf-8")

    long_body = "\n\n".join(
        f"## Heading {i}\n\nBody paragraph {i} — repeated for length."
        for i in range(1, 201))

    # Long markdown for the Repo-view markdown-scroll pin.
    (repo / ".gator" / "artifacts" / "long.md").write_text(
        f"# Long doc for scroll pin\n\n{long_body}\n",
        encoding="utf-8")


_h.seed_sidebar_fixtures = seed_sidebar_fixtures  # noqa: reassign stub
