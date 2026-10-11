# Implementation: Welcome HTML Documents — Checkpoint 1 (Sandboxed Welcome documents)

## Executive Summary

- Four placeholder Welcome documents now ship in `templates/gator-starter/docs/`. Each is a filled, cut-down copy of the Cumberland master: shared style region byte-identical, master meta CSP kept, no `==TODO==`.
- The Dashboard serves only those four names through `GET /api/welcome/docs/<name>`, with `_B2_CSP_EXTERNAL` and `nosniff`. It shows each in a lazily created, persistent iframe sandboxed exactly `allow-scripts`. The snapshot embeds them as script-safe JSON with an injected CSP meta, assigned through `srcdoc`.
- The HTML CSP directives moved verbatim to `content_policy.HTML_CSP_DIRECTIVES`. B2 header bytes are unchanged, and `test_html_preview.py` passes.
- Verified: the checkpoint's focused suite (58 passed), plus a sandbox mutation check. One deviation from the plan: encoded-slash probes get 400 from the existing request parser, not 404.

## Implementation Summary

**Documents** (`src/gator_command/templates/gator-starter/docs/*.html`, new).
- I generated each document from `reference-notes/cumberland-html-document-template.html`.
- Kept verbatim: `<!DOCTYPE html>`, `<html lang="en">`, `<meta charset>`, the master's meta CSP (`script-src 'none'`), viewport, and the whole `<style>`. The `CUMBERLAND-NARRATIVE-STYLE` region is byte-identical.
- Replaced: the authoring comment, now a short provenance comment naming the master.
- Filled: `<title>` / `<h1>` (the tab label), `header.doc-head` (subtitle and `.meta-grid`: Doc class, Audience, `status-badge` Placeholder, Updated, Reading time, Author), `section#summary .callout`, one or two body sections, and `footer.doc-foot`.
- Deleted: `.metaline`, `nav.toc`, and the unused component samples.
- Components kept per document:
  - `how`: the master's `.figure`, holding an inline SVG with `role="img"`, `<title>`, `<desc>`, a caption, and a text paragraph that says the same thing.
  - `can`: a list of the four capabilities.
  - `gatorize`: the command as a code sample, plus a `.callout.note` saying native agent files belong to the repository.
  - `session`: the master's `.steps` (the agent runs `gator init`, and its output names `GATOR_INIT.md` and the required reads), `<pre id="session-prompt">` with the exact one-line prompt, and a static `#copy-manual` line. Checkpoint 2 adds the button and script.
- No external URL other than the SVG `xmlns`, and no `<link>`, `<script src>`, `<img>`, `<iframe>`, `@import` or `url(`.

**CSP source of truth.**
- `dashboard/content_policy.py`: new `HTML_CSP_DIRECTIVES` (text moved verbatim) and `html_csp_meta_policy()` (the same directives minus `frame-ancestors`).
- `gator-dashboard.py`: imports it, and `_B2_CSP_DIRECTIVES = HTML_CSP_DIRECTIVES`. `_B2_CSP_EMBEDDED` / `_B2_CSP_EXTERNAL` and `apply_html_csp_headers()` are untouched.

**Route.**
- `dashboard/helpers.py`: `WELCOME_DOCS_DIR`, `WELCOME_DOC_NAMES` (a frozenset of four), and `read_welcome_html(name)`. It returns `None` unless `name` is a member; otherwise it reads the matched file, and returns `None` on `OSError` / `UnicodeDecodeError`.
- `gator-dashboard.py`: `do_GET` has `if path.startswith(_WELCOME_DOCS_PREFIX): self._send_welcome_doc(path[len(prefix):]); return`, which never falls through.
  - `_send_welcome_doc()` sends 200 with `apply_response_headers(text/html; charset=utf-8, no-cache)` (`nosniff`) plus `Content-Security-Policy: _B2_CSP_EXTERNAL`.
  - Otherwise it sends a plain-text 404, "This Welcome document is not available.", with `nosniff`.
  - The old `/api/welcome/how-gator-works` branch and `read_welcome_doc` / `WELCOME_DOC_PATH` are removed.

**Snapshot** (`dashboard/snapshot.py`).
- `_json_script()` now escapes every `<`, `>`, `&` as `<` / `>` / `&`.
- `_with_csp_meta()` inserts `<meta http-equiv="Content-Security-Policy" content="<html_csp_meta_policy()>">` right after the first `<head…>` tag (case-insensitive). It returns `None` for `None` or for a document without `<head>`.
- `_welcome_docs_for_snapshot()` feeds `window.GATOR_WELCOME_DOCS`, which replaces `GATOR_WELCOME_DOC`. The script-tag regex and inline order are unchanged.

**Frame host** (`dashboard/views/welcome.js`, rewritten body).
- `TOPICS[i].doc` names each document. Tabpanels keep their #72 ids, roles, `aria-labelledby` and `tabindex=0`, and start empty. `applyTopic()` keeps writing only differing attributes, then calls `ensureFrame(selectedTopic)`.
- `ensureFrame()` creates one `iframe.welcome-frame` per topic per mount: `setAttribute("sandbox", "allow-scripts")`, `title` = label, and either `src = /api/welcome/docs/<doc>` or, when `window.GATOR_SNAPSHOT` is set, the `srcdoc` property from `GATOR_WELCOME_DOCS`. A missing or `null` snapshot entry gives a `p.welcome-doc-status` text notice.
- `frames` resets per mount, and a frame is never re-created or re-pointed.
- Removed: `PANELS`, `DOCS`, `docLink`, `nextButton`, the Markdown loader/renderer, the parent copy button, and `showCopyFallback`.
- `SESSION_PROMPT` stays and is unused until checkpoint 2, as the plan says.

**CSS** (`dashboard.css`): `.welcome-frame` (block, full width, no border, `height: max(480px, calc(100vh - 220px))`, narrower at ≤600px) and `.welcome-doc-status`. The dead Welcome rules are removed. `.welcome-body` and `.gator-tabbar` are unchanged.

**Knowledge layer.**
- `inbox.md`: the release-hold line.
- `commit_draft.md`: change log and frontmatter.
- The source sketch `.gator/artifacts/2026-10-10-welcome-html-documents-sketch.md` is staged as the design record for this feature.

**Deviation from the plan:** encoded-slash probes (`..%2fREADME.md`) are refused with **400** by the pre-existing shared `_parse_request()` ("encoded slash or backslash in path") before the Welcome branch runs. The plan expected 404. This is stricter and not Welcome code. The rejection test asserts 400 for `%2f` probes and 404 for every other case, and the charter TRIPWIRE records it.

## Charter Updates

- `scripts-dashboard.md`:
  - The Welcome entry is rewritten as `read_welcome_html(name) / WELCOME_DOC_NAMES / WELCOME_DOCS_DIR / _send_welcome_doc(name) / GET /api/welcome/docs/<name>`. The TRIPWIRE covers the closed set, membership-only lookup, no fall-through, plain-text 404, parser 400 for encoded separators, the removed old route, why `_B2_CSP_EXTERNAL` is used, and the intersection with the documents' own meta CSP.
  - The `is_browsable()` / `content_policy.py` entry gains the `HTML_CSP_DIRECTIVES` / `html_csp_meta_policy()` bullet.
  - `apply_response_headers()` / `apply_html_csp_headers()` gains a TRIPWIRE: the alias, byte-identical headers pinned by `test_html_preview.py`, and the `'unsafe-inline'` dependency of in-document scripts.
  - `build_snapshot()`: the `GATOR_WELCOME_DOCS` / `_with_csp_meta()` / hardened `_json_script()` note replaces the old `GATOR_WELCOME_DOC` note.
- `scripts-dashboard-ui.md`:
  - The Welcome entry is rewritten (`ensureFrame()` frames; an exact-sandbox / no-document-HTML / not-a-navigation-controller TRIPWIRE). The `SESSION_PROMPT` TRIPWIRE is kept.
  - The CSS note covers `.welcome-frame` sizing and the removed rules.
- `scripts-cross-cutting.md`: the Package-surface note now names the four runtime-read starter documents and their delivery through the generic `docs/` overlay, with the pinning tests.
- Checked against code: a grep for removed names (`read_welcome_doc`, `WELCOME_DOC_PATH`, `GATOR_WELCOME_DOC`, `loadHowDoc`, `showCopyFallback`, `copySessionPrompt`, old route) across charters, `src` and `tests` finds only the intentional "old route is gone" sentence.

## Verification

- `python -m pytest tests/test_welcome_docs.py tests/test_snapshot.py tests/test_dashboard_ui/test_welcome_ui.py tests/test_dashboard_ui/test_html_preview.py -q` → **58 passed** (39 s).
  - `test_welcome_docs.py` (10): Cumberland structure ×4, standalone and accessible ×4, session prompt equals `welcome.js` `SESSION_PROMPT`, gatorize installs all four and `plan_updates()` plans each as `add` when missing.
  - `test_snapshot.py`: four documents, each the shipped text plus exactly one injected meta after `<head>`. A hostile document (`</script><!--<script>`, U+2028, `&`) leaves no raw `<`, `>` or U+2028 in the inline JSON and round-trips. A headless document and an absent one become `null`.
  - `test_welcome_ui.py` (21):
    - the repo-context test (only the four document GETs, once each);
    - the ARIA/keyboard, narrow-width and Back/Forward pins, unchanged;
    - frames: only `how` on open; one exact-sandbox, titled frame per topic; an in-frame marker survives switching away and back; no re-request; no document markup in the Dashboard DOM;
    - route ×4: status, content type, `nosniff`, exact CSP, byte-equal body, and a query string ignored;
    - rejections ×9;
    - snapshot `srcdoc` frame with sandbox, CSP meta and the exact prompt.
  - `test_html_preview.py`: B2 headers unchanged after the constant move.
- `python -m pytest tests/test_packaging.py -k test_wheel_has_templates` → 1 passed. `test_wheel_has_templates` now asserts the four `gator_command/templates/gator-starter/docs/*.html` wheel members. It was pulled forward from final approval because the cross-cutting charter cites it.
- Mutation check: setting the frame sandbox to `allow-scripts allow-same-origin` makes `test_welcome_frames_lazy_persistent_sandboxed` fail. Restored afterwards.
- Deferred to final approval, per the plan's ladder: the rest of `test_packaging.py`, `test_layout.py`, `test_gatorize.py`, and the broad `tests/test_dashboard_ui` suite.
- Not part of the candidate: `.gator/.gator-version` and `.gator/runtime-pin.json` (version-bump residue, unstaged) and the loop directories.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 2) — Sandboxed Welcome documents |
| Checkpoint base tree | `6c0874c6810c7ebe2b03e81d173f86db16dc7862` |
| Generation | 0 |
| Staged tree (candidate) | `644db5e88cf059b1466b4a6080d8dc2f975e91ca` |
| Changed paths in this checkpoint | 21 (A 7, M 14) |
| Loop base HEAD | `a2593995f53bdce353c9539188217324218938dd` |
| Loop base tree | `6c0874c6810c7ebe2b03e81d173f86db16dc7862` |
| Current HEAD | `a2593995f53bdce353c9539188217324218938dd` (dev) |
| Changed paths vs loop base (cumulative) | 21 |
| Unstaged / untracked residue | 2 other + 34 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 6c0874c6810c7ebe2b03e81d173f86db16dc7862 644db5e88cf059b1466b4a6080d8dc2f975e91ca
```

Cumulative context (approved checkpoints plus this one): `git diff 6c0874c6810c7ebe2b03e81d173f86db16dc7862 644db5e88cf059b1466b4a6080d8dc2f975e91ca`.

Changed paths in this checkpoint (status, path):

```text
A .gator/artifacts/2026-10-10-welcome-html-documents-sketch.md
M .gator/charters/scripts-cross-cutting.md
M .gator/charters/scripts-dashboard-ui.md
M .gator/charters/scripts-dashboard.md
M .gator/commit_draft.md
M .gator/inbox.md
A .gator/session-snippets/2026-10-10-gator-bd2be0d7a7abf.json
M src/gator_command/scripts/dashboard/content_policy.py
M src/gator_command/scripts/dashboard/dashboard.css
M src/gator_command/scripts/dashboard/helpers.py
M src/gator_command/scripts/dashboard/snapshot.py
M src/gator_command/scripts/dashboard/views/welcome.js
M src/gator_command/scripts/gator-dashboard.py
A src/gator_command/templates/gator-starter/docs/gatorize-a-repo.html
A src/gator_command/templates/gator-starter/docs/how-gator-works.html
A src/gator_command/templates/gator-starter/docs/start-a-session.html
A src/gator_command/templates/gator-starter/docs/what-gator-can-do.html
M tests/test_dashboard_ui/test_welcome_ui.py
M tests/test_packaging.py
M tests/test_snapshot.py
A tests/test_welcome_docs.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
```

Loop residue: 34 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
