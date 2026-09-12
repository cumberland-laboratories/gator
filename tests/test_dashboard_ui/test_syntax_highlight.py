"""Read-only Python + SQL syntax highlighting pins (2026-09-12).

Pins the shipped `views/syntax.js` + `views/repo.js
renderContentFor` behavior end-to-end through the real Dashboard
shell:

  - `.py` file → tokenized (keywords, strings, comments,
    decorators, numbers appear as `.tok-*` spans).
  - `.sql` file → tokenized with case-insensitive keyword match
    (`SELECT` / `from` / `Where` all classified as keywords).
    Line + block comments and single-quoted strings with `''`
    escapes tokenized.
  - Oversize `.py` (> 500 KB) → plain `<pre class="md-code-block">`
    fallback, NO `.tok-*` spans.
  - Escape-order invariant: the shipped `<` inside a Python string
    literal renders as literal `<` in .textContent AND as `&lt;`
    in .innerHTML — proves escape ran exactly once on the token
    value (not zero times → XSS hole; not twice → `&amp;lt;`).

Fixtures shipped by `test_syntax_highlight_seed.py` under
`source/` in every seeded repo.
"""


def _click_source_file(page, fleet, filename, *, repo="alpha"):
    """Navigate to a repo, expand the `source/` sidebar section
    (collapsed by default per repo.js `expandAncestors`), click the
    named source file, and wait for the plain content branch to
    render (`.repo-markdown .md-code-block` is present).
    """
    origin = fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=" + repo, wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)

    # Expand the source/ top-level section — collapsed by default
    # per views/repo.js. Section toggle button is
    # `.repo-sidebar-section[data-toggle="section:source"]`; its
    # contents element is nextElementSibling with `display:none`
    # while collapsed.
    page.evaluate(
        "() => {"
        "  const btn = document.querySelector("
        "    '.repo-sidebar-section[data-toggle=\"section:source\"]');"
        "  if (!btn) return;"
        "  const contents = btn.nextElementSibling;"
        "  if (contents && contents.style.display === 'none') {"
        "    btn.click();"
        "  }"
        "}"
    )

    filepath = "source/" + filename
    selector = f'.repo-file-item[data-path="{filepath}"]'
    page.wait_for_selector(selector, state="attached", timeout=10000)
    page.evaluate(
        "(sel) => document.querySelector(sel).click()", selector)
    page.wait_for_selector(
        ".repo-markdown .md-code-block", timeout=10000)


def _token_texts(page, css_class):
    """Return the .textContent of every `.<css_class>` span inside
    the rendered code block, in document order.
    """
    return page.evaluate(
        "(cls) => Array.from(document.querySelectorAll("
        "  '.repo-markdown .md-code-block .' + cls))"
        "  .map(el => el.textContent)",
        css_class,
    )


# ── Python pins ─────────────────────────────────────────────────

def test_py_file_marks_code_block_with_language(
        page, dashboard_fleet):
    """The .py content branch emits `.md-code-block` with
    `data-lang="python"` — proves `renderContentFor` took the
    highlight branch, not the plain fallback.
    """
    _click_source_file(page, dashboard_fleet, "highlight_sample.py")
    lang = page.evaluate(
        "() => document.querySelector("
        "  '.repo-markdown .md-code-block').getAttribute('data-lang')"
    )
    assert lang == "python", (
        f"expected data-lang=python on .py render; got {lang!r}")


def test_py_file_tokenizes_keywords_strings_comments(
        page, dashboard_fleet):
    """Python fixture has `def`/`class`/`for`/`if`/`return`/`from`
    (keywords), `'gator'` + triple-quoted docstring (strings),
    `# Sample …` (comment), `@staticmethod` (decorator), and `42`
    (number). Assert every category surfaced at least once.
    """
    _click_source_file(page, dashboard_fleet, "highlight_sample.py")

    keywords = _token_texts(page, "tok-keyword")
    assert "def" in keywords
    assert "class" in keywords
    assert "return" in keywords
    assert "from" in keywords

    comments = _token_texts(page, "tok-comment")
    assert any(c.startswith("#") for c in comments), (
        f"no `#…` comment token surfaced; comments={comments!r}")

    strings = _token_texts(page, "tok-string")
    assert any("'gator'" == s for s in strings), (
        f"single-quoted 'gator' string missing; strings={strings!r}")
    assert any(s.startswith('"""') and s.endswith('"""')
               for s in strings), (
        f"triple-quoted docstring missing; strings={strings!r}")

    decorators = _token_texts(page, "tok-decorator")
    assert "@staticmethod" in decorators

    numbers = _token_texts(page, "tok-number")
    assert "42" in numbers
    assert "0" in numbers


def test_py_string_containing_angle_brackets_is_escaped_once(
        page, dashboard_fleet):
    """Escape-order invariant. The fixture contains
    `return f"<{self.NAME} v{self.VERSION}>"` — literal `<` and `>`
    inside a Python f-string. After the highlighter runs the
    rendered pane MUST have:

      - `.textContent` containing the literal `<` and `>`
        (would fail if the highlighter did NOT escape — the
        browser would parse `<gator>` as a real tag and drop it
        from text nodes; also an XSS surface if source had
        `<script>` instead).
      - `.innerHTML` containing `&lt;` (would fail if double-
        escape mistake turned it into `&amp;lt;`).

    Pinning both sides catches an "escape zero times" and an
    "escape twice" regression in the same pin.
    """
    _click_source_file(page, dashboard_fleet, "highlight_sample.py")
    text_content = page.evaluate(
        "() => document.querySelector("
        "  '.repo-markdown .md-code-block').textContent"
    )
    inner_html = page.evaluate(
        "() => document.querySelector("
        "  '.repo-markdown .md-code-block').innerHTML"
    )
    assert "<" in text_content, (
        "literal `<` missing from rendered text — either the "
        "highlighter did not escape (browser parsed the char as "
        "markup) or the fixture drifted")
    assert ">" in text_content
    assert "&lt;" in inner_html, (
        "innerHTML should contain the entity-escaped `&lt;` — "
        "if it contains raw `<` inside a span, the highlighter is "
        "leaking unescaped source into HTML (XSS surface); if it "
        "contains `&amp;lt;`, the source was double-escaped")
    assert "&amp;lt;" not in inner_html, (
        "double-escape detected: `&amp;lt;` in innerHTML means "
        "escHtml ran on already-escaped content")


# ── SQL pins ─────────────────────────────────────────────────────

def test_sql_file_marks_code_block_with_language(
        page, dashboard_fleet):
    _click_source_file(page, dashboard_fleet, "highlight_sample.sql")
    lang = page.evaluate(
        "() => document.querySelector("
        "  '.repo-markdown .md-code-block').getAttribute('data-lang')"
    )
    assert lang == "sql", (
        f"expected data-lang=sql on .sql render; got {lang!r}")


def test_sql_keyword_match_is_case_insensitive(
        page, dashboard_fleet):
    """SQL fixture uses mixed-case keywords: `SELECT`, lowercase
    `from`, capitalized `Where`. All three must classify as
    `.tok-keyword` with their original case preserved in the
    rendered token text.
    """
    _click_source_file(page, dashboard_fleet, "highlight_sample.sql")
    keywords = _token_texts(page, "tok-keyword")
    assert "SELECT" in keywords, (
        f"upper-case SELECT missing from keywords; got {keywords!r}")
    assert "from" in keywords, (
        f"lower-case from missing from keywords; got {keywords!r}")
    assert "Where" in keywords, (
        f"capitalized Where missing from keywords; got {keywords!r}")
    # Non-keyword identifiers (table + column names) must NOT be
    # classified as keywords.
    assert "users" not in keywords
    assert "id" not in keywords


def test_sql_comments_and_strings_tokenize(page, dashboard_fleet):
    """Both comment flavors (`-- …` line + `/* … */` block) and a
    single-quoted string with a `''` escape MUST surface.
    """
    _click_source_file(page, dashboard_fleet, "highlight_sample.sql")

    comments = _token_texts(page, "tok-comment")
    assert any(c.startswith("--") for c in comments), (
        f"no `--` line comment; comments={comments!r}")
    assert any(c.startswith("/*") and c.endswith("*/")
               for c in comments), (
        f"no `/* … */` block comment; comments={comments!r}")

    strings = _token_texts(page, "tok-string")
    assert any(s == "'active'" for s in strings), (
        f"'active' string missing; strings={strings!r}")
    # Doubled-quote escape: the tokenizer MUST NOT split
    # `'it''s fine'` into two adjacent strings.
    assert any(s == "'it''s fine'" for s in strings), (
        f"doubled-quote escape mishandled — expected single "
        f"'it''s fine' token, got strings={strings!r}")


# ── Size-cap fallback ───────────────────────────────────────────

def test_oversize_py_falls_back_to_plain(
        page, dashboard_fleet):
    """A `.py` file larger than HIGHLIGHT_MAX_BYTES (500 KB) MUST
    render via the plain `<pre class="md-code-block">` branch —
    no `data-lang` attribute, no `.tok-*` spans. Pins the size cap
    in `views/repo.js::renderContentFor`.
    """
    _click_source_file(page, dashboard_fleet, "highlight_oversize.py")
    code_block = page.locator(".repo-markdown .md-code-block").first
    lang = code_block.get_attribute("data-lang")
    assert lang is None, (
        f"oversize .py should skip highlighting; got data-lang={lang!r}")

    tok_count = page.evaluate(
        "() => document.querySelectorAll("
        "  '.repo-markdown .md-code-block [class^=\"tok-\"]').length"
    )
    assert tok_count == 0, (
        f"oversize .py leaked {tok_count} token spans — size cap "
        f"regressed in renderContentFor")
