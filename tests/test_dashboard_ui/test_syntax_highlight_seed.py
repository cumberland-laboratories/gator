"""Syntax-highlight seed extension (2026-09-12).

Registers `seed_syntax_fixtures` on the harness so every repo built
via `build_dashboard_fleet` gains the source files the tokenizer
pins exercise. Imported at module scope from `conftest.py` so the
reassignment lands BEFORE any fixture builds the fleet.

Fixtures landed under `source/` (repo root — the "" namespace_root
in content_policy._text_exts_for). Governance namespaces (`.gator/`
+ `gator-command/`) do not carry .py/.sql files, so the fixtures
must live in source/ to be browsable via `/api/repo/<name>/file/`.

- `source/highlight_sample.py` — Python with keywords, three
  string flavors (single / double / triple), a comment, a
  decorator, a number.
- `source/highlight_sample.sql` — SQL with mixed-case keywords
  (SELECT / from / Where), a `--` line comment, a `/* ... */`
  block comment, and a single-quoted string with a doubled ''
  escape.
- `source/highlight_oversize.py` — a > 500 KB Python file that
  MUST fall back to plain rendering (no `.tok-*` spans). Body is
  a long run of `# comment line N\n` — every line would be a
  comment token, so a regression that ignores the size cap would
  emit thousands of `.tok-comment` spans instead of a single
  `<pre class="md-code-block">`.
"""

from . import _harness as _h


_PY_SAMPLE = '''\
# Sample Python file for the syntax highlighter pin.
"""Module docstring — triple-quoted string."""

from typing import List


@staticmethod
def compute(values: List[int]) -> int:
    """Sum a list of integers, skipping None."""
    total = 0
    for v in values:
        if v is None:
            continue
        total = total + v
    return total


class Widget:
    NAME = 'gator'
    VERSION = 42

    def render(self):
        return f"<{self.NAME} v{self.VERSION}>"
'''


_SQL_SAMPLE = """\
-- Sample SQL file for the syntax highlighter pin.
/* Block comment
   spanning multiple lines. */

SELECT id, name, created_at
  from users
 Where status = 'active'
   AND note = 'it''s fine'
 ORDER BY created_at DESC
 LIMIT 100;
"""


def seed_syntax_fixtures(repo):
    """Write .py + .sql fixtures under `source/` at repo root."""
    (repo / "highlight_sample.py").write_text(
        _PY_SAMPLE, encoding="utf-8")
    (repo / "highlight_sample.sql").write_text(
        _SQL_SAMPLE, encoding="utf-8")

    # Oversize .py file — 60_000 lines of `# comment N\n` clears
    # the 500 KB (== 512_000 char) HIGHLIGHT_MAX_BYTES cap in
    # views/repo.js::renderContentFor with headroom. Each line is
    # ~17 chars; total is ~1 MB. Every character would be a
    # comment token under the highlighter, so a regression that
    # ignores the cap emits thousands of `.tok-comment` spans.
    body = "\n".join(f"# comment {i:05d}" for i in range(60_000))
    (repo / "highlight_oversize.py").write_text(
        body + "\n", encoding="utf-8")


_h.seed_syntax_fixtures = seed_syntax_fixtures  # noqa: reassign stub
