# Implementation Plan: Safe Readable Markdown for Loop Artifact Excerpts (#45)

## Executive Summary

- **Proposal:** add a small, dependency-free, deliberately limited Markdown renderer (`views/loop-markdown.js`) that builds DOM with `createElement`/`createTextNode` only. The renderer never parses artifact text as HTML. The Loop artifact inspector uses it for expanded artifact bodies.
- **Key decision:** do not reuse `repo.js` `renderMarkdown()`. It builds HTML strings and passes `javascript:` links, arbitrary `<img src>` and `target=_blank` without `rel`. Do not add a third-party library either, because the shell has no CSP and the charter requires a dependency-free UI.
- **Raw view:** each expanded artifact gets a Rendered/Raw button pair with `aria-pressed` and a text caption. Raw is the existing `<pre class="loop-artifact-pre">` filled by `textContent` from the same fetched string.
- **Verification:** Playwright tests cover representative and adversarial Markdown, a DOM allowlist walk, raw/rendered parity, MutationObserver zero-mutation polls, stale-fetch ordering, the oversize/failure fallbacks, and snapshot inlining.

## Summary

The Loop workspace currently shows every artifact body as escaped text in a `<pre>`. This plan adds a client-side rendering seam in the Loop artifact section only. The seam turns the fetched artifact string into a safe DOM fragment under a fixed element and attribute allowlist. The same string is also kept as an exact Raw view. Server routes, loop storage, schemas, authorization and the Repository browser stay unchanged.

## Context Checked

- `architect-brief.md` (loop directory): "Design should be modular, and select simplicity over complexity where appropriate." This drives the separate small module, the limited subset, and no new dependency.
- `sketch.md` (loop directory): scope, the five decisions, acceptance focus and the scope guard.
- `.gator/charters/scripts-dashboard-ui.md`: Loop workspace incremental-rendering invariants (#38: `renderArtifacts()` reconciliation, `MUTABLE_ARTIFACTS`, `nextRequestRev()` per-node revisions, `fetchArtifact()` `no-store`, zero-mutation unchanged polls). The tripwire "Artifact content is escaped through `escHtml()` and rendered in `<pre>`". `renderContentFor()` / `gatorHighlight()` ("presentation only"). The `repo.js` untrusted-text rule. "Keep the UI dependency-free".
- `.gator/charters/scripts-dashboard.md`: artifact route is allowlisted, served as `text/plain`, no server caching; `build_snapshot()` tripwire that every `views/*.js` script tag must be in the inliner regex and block; HTML CSP applies only to `/raw` HTML responses (the shell itself has none).
- `.gator/charters/INDEX.md`: dashboard JS/CSS/HTML map to the UI and Server charters; `dashboard/*.py` maps to Server and Cross-Cutting.
- Code: `src/gator_command/scripts/dashboard/views/loop.js` (`fetchArtifact()`, `extractSummary()`, `MUTABLE_ARTIFACTS`, `nextRequestRev()`, `loadArtifactSummary()`, `loadArtifactContent()`, `createArtifactSection()`, `renderArtifacts()`). `views/repo.js` (`renderMarkdown()`, `inlineFormat()`, `renderTable()`, `.md` link interception). `dashboard.html` script order. `dashboard/snapshot.py` (`build_snapshot()`). `dashboard.css` (`.loop-artifact-*`, `.md-code-block`, `.md-table`). `gator-dashboard.py` CSP constants (only `_B2_CSP_*` on `/raw` HTML). `pyproject.toml` package-data (`scripts/dashboard/**/*` already ships new view files).
- Tests: `tests/test_dashboard_ui/test_loop_workspace.py` (`test_artifact_toggle_loads_content`, `test_artifact_html_is_escaped`, `extractSummary` tests), `test_loop_refresh_ui.py` (MutationObserver pattern), `test_loop_seed.py` (`seed_loop_fixtures`, the `xss-test` loop), `tests/test_snapshot.py` (`test_scripts_inlined`, `test_no_external_references_remain`).

## Approach

### Decision 1 — Renderer choice: a limited in-repo DOM builder

**Choice:** a new module `views/loop-markdown.js` exposes `window.GatorLoopMarkdown`. It parses a deliberately small Markdown subset in one pass and emits nodes only through `document.createElement`, `document.createTextNode` and property assignment. No code path assigns artifact text to `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `setAttribute("style")` or `on*`. The renderer never gives artifact text to an HTML parser, so the code has no sanitizer step to get wrong.

**Rejected: reuse `repo.js` `renderMarkdown()`.**
- It concatenates HTML strings after `escHtml()`.
- It accepts any link target: `[x](javascript:alert(1))` yields a live `javascript:` href.
- It emits `<img>` with an arbitrary `src` (an external fetch beacon) and an inline `style`.
- It sets `target="_blank"` without `rel`.
- `escHtml()` does not escape `'`.

Making it safe would change the Repository browser, which the scope guard excludes. That gap is noted under Risks as an observation for the Architect.

**Rejected: a pinned third-party renderer plus sanitizer (e.g. marked + DOMPurify).**
- The UI charter requires a dependency-free UI.
- The Dashboard shell serves no CSP, so sanitizer correctness would be the only barrier.
- It would add vendoring, update and CVE-tracking burden, plus snapshot-inlining size for features this surface does not need.

A constrained renderer whose output is only safe node types is simpler and easier to audit. This matches the Architect brief.

### Decision 2 — Raw view interaction and accessibility

- When an artifact section is expanded, its `.loop-artifact-content` holds three parts:
  - a toolbar `<div class="loop-artifact-viewbar" role="group" aria-label="Artifact view">` with two native `<button type="button">` elements, **Rendered** and **Raw**, each with `aria-pressed="true|false"`;
  - a caption `<span class="loop-artifact-viewstate" aria-live="polite">`. It reads "Showing: rendered Markdown (formatting only — Raw is the exact text)" or "Showing: raw text (exact artifact bytes)";
  - two panes: `<div class="loop-md">` (rendered) and `<pre class="loop-artifact-pre">` (raw). Exactly one pane is visible, through the `hidden` property.
- **Keyboard:** native buttons give Tab focus and Enter/Space activation. No custom key handling and no roving tabindex.
- **No colour-only state:** the pressed button is bold and underlined with a visible border, and the caption names the state in text. This follows the Architect's colorblind requirement.
- **Default view:** Rendered. The choice is stored per section in `section.dataset.view` (`rendered|raw`). It survives content refreshes and collapse/expand, and resets only when the skeleton is rebuilt (new selection). Nothing goes to localStorage.
- **One source string:** both panes come from the same fetched string in the same completion callback. The raw pane is `pre.textContent = text`, so it is never rebuilt from rendered DOM. The string is kept on the node as `content._gatorText` for change detection only.
- Switching views only toggles `hidden` and `aria-pressed`. It never refetches and never reparses.

### Decision 3 — Allowed subset and hostile-input handling

**Block elements (line-based):**
- ATX headings `#`–`######`, demoted into the excerpt outline: `#`→`h3`, `##`→`h4`, `###`→`h5`, `####`+→`h6`. This keeps the Dashboard page outline intact.
- Paragraphs: consecutive prose lines join with a space; two trailing spaces give a `br`.
- Unordered (`-`, `*`, `+`) and ordered (`N.` / `N)`) lists, with nesting by indentation. Each step of 2 or more leading spaces deepens the list, up to depth 4; deeper input stays at depth 4. An indented non-marker line continues the current item. The `ol` start number is not carried; it renders 1-based (simplicity).
- Fenced code blocks (```` ``` ```` or `~~~`, 3+ markers, info string ignored). The body is a single text node in `pre > code`. An unterminated fence runs to end of input.
- GFM tables: a header row with `|`, then a delimiter row matching `^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$`, then body rows. Cells split on unescaped `|`. Cells are capped at 32 per row; extra cells merge into the last one. Alignment colons are ignored. The table is wrapped in `div.loop-md-tablewrap` for horizontal scroll.
- Blockquotes (`>`): one level; content parsed as inline text per line.
- Horizontal rules (`---`, `***`, `___`): `hr`.

**Inline:**
- Code spans: backtick runs of equal length; content is a literal text node and is matched first, so no other markup applies inside.
- Links `[text](url)`, with the safety rules below.
- `**strong**` / `__strong__` and `*em*` / `_em_`. `_` emphasis applies only at word boundaries, so `snake_case_name` stays literal.
- Inline nesting stops at depth 3. Unmatched markers render as literal text.

**Not supported (rendered as literal text, never as markup):**
- raw or inline HTML (`<script>`, `<img onerror>`, `<style>`, `<iframe>`, comments);
- images `![alt](src)`: the literal source text shows and nothing is fetched;
- reference-style links, footnotes, autolinked bare URLs, HTML entities (`&lt;` stays as the visible text `&lt;`), and setext headings.

**Link policy (`safeHref(url)`):**
1. Trim the URL. Reject it if it contains whitespace, ASCII control characters, `\`, or is empty.
2. Accept only an absolute URL whose parsed protocol (via `new URL(url)`, no base) is exactly `http:` or `https:`.
3. On accept, emit `a.href = parsed.href`, `a.target = "_blank"`, `a.rel = "noopener noreferrer nofollow"`. Link text uses the inline rules, with no nested links.
4. On reject, render the link text as plain text followed by ` (<url>)` as a text node in `span.loop-md-link-blocked`. This covers relative paths, `#fragment`, protocol-relative `//host`, `javascript:` (any case or entity spelling, because no entities are decoded), `data:`, `vbscript:`, `file:`, `mailto:` and parse failures. The reader sees the target but nothing is clickable.
5. Relative links are not resolved into the Repository browser. That would be new navigation behaviour and is excluded by the scope guard.

**Structural allowlist (enforced by construction, verified by tests):**
- **Elements:** `h3 h4 h5 h6 p br ul ol li strong em code pre a table thead tbody tr th td blockquote hr div span`.
- **Attributes:** `class` (renderer constants only) on any element, and `href`/`target`/`rel` on `a` only. No `style`, no `id`, no `on*`, no `src`.
- **CSS:** scoped under `.loop-md` (`min-width: 0`, `overflow-wrap: anywhere`, `pre` and table wrapper `overflow-x: auto`, `max-width: 100%`). Content cannot inject styles or break the layout.

### Decision 4 — Fit with stable nodes and request revisions

- `renderArtifacts()` reconciliation, `createArtifactSection()` node identity, `MUTABLE_ARTIFACTS` refresh policy, `nextRequestRev()` and the generation/`isConnected` guards stay as they are.
- Rendering happens only inside the `loadArtifactContent()` completion, **after** all three existing guards pass (generation, `isConnected`, `_gatorContentRev === rev`). An older in-flight fetch is dropped before any parse, so it cannot overwrite newer rendered or raw output.
- **Zero-mutation unchanged polls are kept.** Unchanged polls never reach `loadArtifactContent()`, because `refreshMutable` is false when the event log has not advanced. When the event log advances and an expanded mutable artifact is refetched, the new completion compares `text === content._gatorText` and skips all DOM writes on a match. That also avoids a reparse when another artifact changed. The skip is stated in code and pinned by a test.
- A changed text rebuilds only the inside of that one `.loop-artifact-content`: the toolbar is reused if present, and both panes are rebuilt from the new string. The section node, its toggle and its expanded state are untouched, and `section.dataset.view` is re-applied.
- The collapsed-refresh path (bump revision, `delete content.dataset.loaded`) is unchanged.

### Decision 5 — Where rendering happens, and bounds

- **Expanded bodies only.** Rendering runs when a section is expanded (or refreshed while expanded), for every artifact the inspector lists. All of them are allowlisted `.md`: sketch, briefs, plan, findings, implementation, approved plan and decision documents. One code path is simpler than a per-name rule.
- **Summary excerpts stay as they are.** The `.loop-summary-text` and `.loop-timeline-summary-text` excerpts stay escaped plain text. They are truncated at 500 characters, which can cut Markdown mid-construct, and the timeline cards append incrementally. This keeps the change small.
- **Large artifacts.** `GatorLoopMarkdown.MAX_RENDER_CHARS = 200000`. Above that, the section opens in Raw with the Rendered button disabled. The caption reads "Too large to render (N characters); showing raw text". The parser is a single linear pass with bounded nesting and table width. Briefs are capped at 32,768 bytes server-side, and plans are typically under 50 KB. The existing `max-height: 400px; overflow: auto` panel and the collapse/expand toggle stay as the truncation and expand mechanism.
- **Failure fallback.** `GatorLoopMarkdown.render()` runs in `try/catch`. If it throws, or the module is absent (an older snapshot), the section shows Raw with Rendered disabled. The caption reads "Could not render Markdown; showing raw text". The escaped text is always visible, never an empty panel. Errors are not logged with artifact content.

## Changes

### 1. New renderer module
- File: `src/gator_command/scripts/dashboard/views/loop-markdown.js` (new, IIFE, `"use strict"`, no dependencies).
- What:
  - **Exports:** `window.GatorLoopMarkdown = { render(text) → DocumentFragment, safeHref(url) → string|null, MAX_RENDER_CHARS }`.
  - **Internals:** `parseBlocks(lines)` (line classifier and block builder), `renderInline(parent, text, depth)` (code spans, then links, then strong/em, else text nodes), `buildList()`, `buildTable()`, `buildFence()`. All output goes through a local `el(tag, className)` helper and `document.createTextNode`.
  - **Header comment:** states the allowlist and the never-HTML rule as a TRIPWIRE.
- Why: a modular, testable seam (Architect brief) that is separate from the 2,871-line `loop.js` and the Repository browser.

### 2. Load the module
- File: `src/gator_command/scripts/dashboard/dashboard.html`
- What: add `<script src="views/loop-markdown.js"></script>` immediately before `<script src="views/loop.js"></script>`.
- Why: `loop.js` reads `window.GatorLoopMarkdown` lazily at render time, but defining it first keeps the order obvious.

### 3. Snapshot inlining
- File: `src/gator_command/scripts/dashboard/snapshot.py` (`build_snapshot()`)
- What:
  - read `views/loop-markdown.js`;
  - add `\s*<script src="views/loop-markdown\.js"></script>` before the `loop.js` tag in the replacement regex;
  - inline it in `scripts_block` before `loop_js`.
- Why: the Server charter tripwire. Every `views/*.js` tag must be in both the regex and the block, or the regex stops matching and the snapshot keeps external references.

### 4. Loop artifact inspector uses the seam
- File: `src/gator_command/scripts/dashboard/views/loop.js`
- What:
  - `loadArtifactContent()`: after the existing three guards, a `null` text keeps today's "Not available." Otherwise it calls a new `renderArtifactBody(section, content, text)` instead of writing `<pre>` via `innerHTML`.
  - New `renderArtifactBody(section, content, text)`:
    - if `content._gatorText === text && content.dataset.loaded`, return (no writes);
    - otherwise set `_gatorText`, build or reuse the view bar, build the raw `pre.loop-artifact-pre` via `textContent`, and build `div.loop-md` from `GatorLoopMarkdown.render(text)` inside `try/catch`;
    - apply the oversize and failure rules (Decision 5), then call `applyArtifactView(section, content)`;
    - set `content.dataset.loaded = "1"`.
  - New `buildArtifactViewBar(section, content)`: two buttons wired once per content node, writing `section.dataset.view` and calling `applyArtifactView`.
  - New `applyArtifactView(section, content)`: sets `hidden`, `aria-pressed`, the `disabled` state and the caption text, writing each only when the value differs.
  - `createArtifactSection()`, `renderArtifacts()`, `MUTABLE_ARTIFACTS`, `nextRequestRev()`, `extractSummary()` and the summary loaders are unchanged.
- Why: the smallest insertion point that inherits the existing ordering and generation guarantees.

### 5. Styles
- File: `src/gator_command/scripts/dashboard/dashboard.css`
- What:
  - new rules for `.loop-artifact-viewbar`, `.loop-artifact-viewbar button[aria-pressed="true"]` (bold, underline, 2px border) and `.loop-artifact-viewstate`;
  - `.loop-md` typography (compact: 13px body, h3–h6 sizes, list padding, `pre`/`code` reuse of the `.md-code-block`/`.md-inline-code` look by declaring equivalent `.loop-md pre` / `.loop-md code` rules), `.loop-md-tablewrap { overflow-x: auto; max-width: 100%; }`, `.loop-md table` borders matching `.md-table`, `.loop-md-link-blocked` (muted, no pointer), and `.loop-md { min-width: 0; overflow-wrap: anywhere; }`;
  - `.loop-artifact-pre` unchanged.
- Why: readable compact excerpt. Containment rules stop hostile content from widening the workspace.

### 6. Tests
- File: `tests/test_dashboard_ui/test_loop_markdown_ui.py` (new, Playwright, using the existing `page` / `dashboard_fleet` fixtures and `test_loop_workspace.py` navigation helpers).
- **Unit-in-page tests** via `page.evaluate` on `GatorLoopMarkdown.render()`:
  - headings demoted; paragraphs joined; nested ul/ol (3 levels); a table with an escaped pipe and >32 cells; fenced code containing `<script>alert(1)</script>` and `<b>` (text-only, no elements); inline code containing `**`; `snake_case` stays literal;
  - **allowlist walk:** every element in the fragment is in the allowlist; every attribute is `class` or (`a` only) `href`/`target`/`rel`; no `style` or `on*` anywhere;
  - **adversarial inputs:** `<img src=x onerror=…>`, `<svg onload>`, `<style>body{display:none}</style>`, `<iframe>`, an HTML comment, `[a](javascript:alert(1))`, `[a](JaVaScRiPt:…)`, `[a](java&#x73;cript:…)`, `[a](data:text/html,…)`, `[a](vbscript:…)`, `[a](//evil.example)`, `[a](relative.md)`, `[a](#frag)`, a URL with embedded tab/newline/NUL, `![x](http://evil/beacon)` (no `img`, no fetch), `[a](https://ok.example)` → `href` https with `target=_blank` and `rel` containing `noopener` and `noreferrer`;
  - **malformed input:** unclosed fence, unmatched `**`, a lone `|` line, 10-deep indentation, empty string — no throw, text preserved.
- **Workspace tests** on seeded loops:
  - expanding a plan shows Rendered by default with `aria-pressed` correct and the caption text;
  - Raw shows `textContent` byte-identical to `fetch(artifact).text()` from the same endpoint (parity);
  - the existing `xss-test` sketch renders with zero `script`/`img`/`iframe`/`style` elements under `.loop-artifact-content`, and its literal `<script>` text is visible in both panes;
  - keyboard: Tab to Raw, press Space, and the state flips.
- **Incremental tests:**
  - (a) with a plan expanded, in Raw view, a MutationObserver on `#loop-artifacts` across several unchanged polls records 0 mutations;
  - (b) rewriting `plan.current.md` plus appending an event refreshes both panes, and the Raw choice persists;
  - (c) appending an event without changing `plan.current.md` causes 0 mutations inside the expanded content (text-equality skip);
  - (d) stale fetch: delay the first artifact response with route interception and return a newer second response, then assert that the newer text wins in both panes.
- **Fallback tests:** seed a >200,000-char artifact, then check it opens Raw, Rendered is disabled and the caption is present. Stub `GatorLoopMarkdown.render` to throw, then check the Raw text is visible with the failure caption and the workspace still polls.
- File: `tests/test_dashboard_ui/test_loop_seed.py`: add one small loop fixture (or extend an existing non-terminal one) whose `plan.current.md` holds the representative Markdown sample. The large artifact is generated inside its test, so the seed stays small.
- File: `tests/test_snapshot.py`: add `src="views/loop-markdown.js"` to `test_scripts_inlined` and `test_no_external_references_remain`, and assert `GatorLoopMarkdown` appears in the snapshot HTML.
- **Existing tests:** `test_artifact_toggle_loads_content` and `test_artifact_html_is_escaped` keep working. `.loop-artifact-pre` still exists (hidden in Rendered view) with the exact `textContent`. Neither test depends on visibility, but I will confirm this when I run the tests.

## Dependencies and Ordering

1. Change 1 (module) together with its Playwright unit-in-page tests. This is independent of the rest.
2. Change 2 (HTML tag) and Change 3 (snapshot) together, plus the `test_snapshot.py` update. Snapshot output breaks if only one is done.
3. Change 4 (loop.js integration), which needs 1 and 2.
4. Change 5 (CSS), alongside 4.
5. Workspace, incremental and fallback tests, then the full `tests/test_dashboard_ui` and `tests/test_snapshot.py` runs.
6. Charter updates immediately after each file edit (constitution step 5), and `commit_draft.md` entries.

## Assumptions, Risks, and Required Architect Decisions

**Non-blocking assumptions (reversible):**
- Default view is **Rendered**. One line flips it to Raw if the Architect prefers audit-first.
- Summary excerpts (inspector and timeline) **stay plain text**. Rendering them later reuses the same seam.
- Relative links render as **inert text plus the visible target** and do not navigate into the Repository browser.
- `MAX_RENDER_CHARS = 200000` characters (not bytes). This is a UI responsiveness bound, not a security bound.
- All inspector artifacts (including sketch and decision documents) use the seam, not only plan, findings, implementation and brief. All are allowlisted `.md` from the same route.

**Risks:**
- **Renderer correctness is the only barrier**, because the Dashboard shell has no CSP. This is mitigated by construction: no HTML parser receives artifact text, and the attribute set is fixed. The allowlist-walk test runs over every adversarial input.
- **Parser fidelity:** the subset will not match CommonMark exactly (for example, lazy continuation and setext headings). The Raw view gives an exact representation, and the failure mode is "literal text", never markup.
- **Existing-test coupling:** tests that read `.loop-artifact-pre` still pass because the Raw pane always exists. Any test that checks its visibility would need an update; none was found.

**Observation for the Architect (out of scope, no action in this plan):** `repo.js` `renderMarkdown()`/`inlineFormat()` lets `javascript:` link targets through. It emits `<img>` with an arbitrary external `src` and an inline style, and opens `target="_blank"` without `rel`. Repository content is less hostile than model-authored loop residue, but the gap is real. It could be a follow-up issue that adopts this seam.

**Blocking decisions:** none.

## Testing

- `pytest tests/test_dashboard_ui/test_loop_markdown_ui.py tests/test_dashboard_ui/test_loop_workspace.py tests/test_dashboard_ui/test_loop_refresh_ui.py tests/test_dashboard_ui/test_loop_brief_ui.py tests/test_dashboard_ui/test_loop_coding_ui.py tests/test_snapshot.py`, then the full `tests/test_dashboard_ui` suite (the CI `dashboard-ui` job).
- **Manual check:** open a live loop in `gator dashboard`, expand plan and findings, and toggle Raw/Rendered with the keyboard. Check a wide table and a long code line at narrow width with no horizontal page scroll. Check `gator dashboard --snapshot` output renders an artifact.
- **No server tests change:** no route, header, allowlist or storage code is modified. `git diff --stat` must show no `gator-dashboard.py` or `loop/` changes.

## Charter Impact

- `.gator/charters/scripts-dashboard-ui.md`:
  - add `views/loop-markdown.js` to **Covers**;
  - add a function entry `GatorLoopMarkdown.render() / safeHref()` with the element/attribute allowlist, link policy, never-HTML TRIPWIRE, size bound and failure contract;
  - add `renderArtifactBody() / buildArtifactViewBar() / applyArtifactView()` to the Loop workspace function list;
  - **replace** the tripwire "Artifact content is escaped through `escHtml()` and rendered in `<pre>`" with the new rule: rendered only through `GatorLoopMarkdown` DOM construction, Raw via `textContent` from the same fetched string, never `innerHTML`;
  - extend the incremental-artifacts tripwire with the text-equality skip and per-section view persistence.
- `.gator/charters/scripts-dashboard.md`: update the `build_snapshot()` tripwire's script list to include `loop-markdown.js`.
- `.gator/charters/INDEX.md`: no change. The `views/**` glob already maps the new file to the UI charter.
