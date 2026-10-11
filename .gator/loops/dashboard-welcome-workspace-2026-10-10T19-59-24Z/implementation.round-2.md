# Implementation: Dashboard Welcome Workspace (#72) — Checkpoint 2

## Executive Summary

- **What changed:** The sidebar logo is now a real `#brand-home` button ("Open Welcome"). It opens a new, repository-independent `welcome` shell view. `views/welcome.js` renders four ARIA topics in the shared main-pane tab bar from checkpoint 1, with fixed content, and one **Copy session-opening prompt** control. If the clipboard is unavailable, Loop's manual-copy fallback is used.
- **Key decision:** Implemented exactly as the approved plan says:
  - topic state is module-local;
  - Welcome history entries are ordinary shell entries with `sub: null`;
  - there is no fetch, storage, console or history call in Welcome;
  - the snapshot inlines the new script.
- **Main risk:** A shell-history TRIPWIRE is touched, because `VIEW_META` gates `isShellEntry`. The significance check was run and recorded. It surfaces one open question for the Architect: the copied prompt keeps the sketch's two line breaks.
- **Verified:** The focused command passes 16/16. The final broad suite (Dashboard UI + snapshot + packaging) passes: 474 passed, 11 skipped.

## Implementation Summary

- **`views/welcome.js` (new).** It registers `GatorViews.welcome(data, container)`.
  - **Constants:** `TOPICS`; `SESSION_PROMPT` (the exact sketch text, line breaks as written); fixed `DOCS` links to the public README, `docs/how-to-use-gator.md` and `docs/architecture.md`; and module-local `selectedTopic = "what"`.
  - **Rendering:** it writes `.welcome-workspace`, which holds a `div.gator-tabbar.welcome-tabbar` with a `[role=tablist][aria-label="Welcome topics"]` of four `button.gator-tab.welcome-tab[role=tab]`, and a `.welcome-body` with four `section[role=tabpanel][tabindex=0]` panels.
  - **Tab state:** `applyTopic()` writes `aria-selected`, roving `tabindex` and `hidden` only when they differ. Click selects; Left/Right (wrapping), Home and End select and focus. The "next" buttons select their target topic and focus its tab.
  - **Copy:** the prompt is written into the visible `pre.welcome-prompt` and the fallback textarea only via `textContent` / `.value`. `copySessionPrompt()` writes the prompt to the clipboard, then shows "Copied" and the polite status "Session-opening prompt copied.", restored after 2 s if still connected.
  - **Fallback:** `showCopyFallback()` mirrors `showPromptFallback()`: a selected read-only textarea, "Select all and copy manually.", and Dismiss. It also announces "Clipboard unavailable — copy the prompt manually." It runs when `navigator.clipboard` is missing or `writeText` rejects.
- **`dashboard.html`.** The logo `<img>` (now `alt=""`) is wrapped in `<button type="button" id="brand-home" class="brand-home" aria-label="Open Welcome" title="Open Welcome">`. `<script src="views/welcome.js">` is added after `settings.js`.
- **`dashboard.js`.**
  - `VIEW_META.welcome = {title: "Welcome to Gator!"}`.
  - A `showView` branch for `welcome` calls `updateTopbar` and the view. It never calls `setActiveRepo` / `clearActiveRepo`.
  - `aria-current="page"` is set on `#brand-home` only while Welcome is shown.
  - The logo click calls `navigate("welcome")`.
  - Unchanged: `cleanSub`, `GatorShell`, the `#sidebar-nav` handler, `doRefresh` and `init`.
- **`dashboard.css`.** `.brand-home` resets the button styling and adds a `:focus-visible` outline; `#brand-logo` sizing is unchanged. New Welcome block: `.welcome-body` (max-width 760px), headings, lists, the next and copy buttons (bordered, with focus outlines), the `.welcome-code` / `.welcome-prompt` blocks (`pre-wrap`), the status, and the `.welcome-copy-fallback*` styles matching the Loop fallback. The tabs reuse `.gator-tabbar` / `.gator-tab` with no Welcome-specific tab rules.
- **`snapshot.py`.** Reads `views/welcome.js`, adds it to the script-tag regex after `settings`, and inlines it before the data block.
- **Tests:**
  - `tests/test_snapshot.py`: `welcome.js` is added to both "no external reference" checks, plus `window.GatorViews.welcome` inlined.
  - New `tests/test_dashboard_ui/test_welcome_ui.py`, with six tests and nine cases:
    1. Routing from Fleet, Repo and Loop (parametrized). Repository label and dimming are unchanged. `aria-current` is set. There are zero `/api/` requests and no non-GET requests across all tab switches and a copy.
    2. ARIA relationships, roving tabindex, click and keyboard incl. wrapping, one visible panel, weight + 3px underline, and the bar spanning the pane's content width with a 1px baseline.
    3. Exact copy: the clipboard is compared with CRLF normalized, because the Windows OS clipboard stores CRLF. Also checks "Copied", the `role=status` / `aria-live=polite` text, no prompt in `history.state` / `localStorage` / `sessionStorage`, and the label restored.
    4. Fallback, parametrized over a missing and a rejecting Clipboard API: exact text, read-only and selected, hint, status, and Dismiss.
    5. At 400px: all four tabs are inside the viewport, unclipped, and at the same font size as desktop.
    6. Back/Forward: one history entry per open, none per topic, `sub: null`; Back shows Fleet and clears `aria-current`; Forward restores Welcome with the same topic; reloading and reopening shows "What is Gator?".

## Charter Updates

- **`.gator/charters/scripts-dashboard-ui.md`:**
  - **Owns:** "welcome views" added.
  - **`navigate()…` TRIPWIRE:** a new **Welcome (#72)** sub-bullet. Welcome is a `VIEW_META` view, reached only from `#brand-home` and Back/Forward. It sets `aria-current`, never calls the repository-context setters, and its entries carry `sub: null` (`cleanSub` stays Loop-only).
  - **New entry `GatorViews.welcome / applyTopic() / selectTopic() / copySessionPrompt() / showCopyFallback() (#72)`:** covers the tab structure, module-local topic state, fixed content, and copy and fallback behaviour. It adds two TRIPWIREs:
    - the prompt is vendor- and layout-neutral (never `.gator/.includes/GATOR_INIT.md`), written only through `textContent` / `.value`, and never logged, stored, put in `data-*` or put in history;
    - Welcome never touches repository context.

    It is pinned by `test_welcome_ui.py`.
  - **Responsive shell:** a **Logo button (#72)** TRIPWIRE.
- **`.gator/charters/scripts-dashboard.md` → `build_snapshot()`:** the script order now includes **welcome (#72)** after settings, and the pin note mentions `GatorViews.welcome`.
- **How I checked these against the code:** I grepped `welcome` in `dashboard.js` (VIEW_META, the `showView` branch, the click binding, `aria-current`) and `snapshot.py` (read, regex, block), and checked the function names in `welcome.js` against the new charter heading.
- **Commit draft:** five checkpoint 2 log bullets, plus the significance check below. `significance` stays `notable`.

## Significance Check

This checkpoint touches the **shell-owned history TRIPWIRE (#56)**, because `VIEW_META` gates `isShellEntry`.

**Steelman:**
1. **More restorable history entries.** Adding `welcome` widens the set of entries that can be restored. A Dashboard downgrade would ignore a `welcome` entry: Back skips it instead of restoring it.
2. **A new focus stop.** The logo was a decorative image and is now a named button. Screen readers announce it, and keyboard Tab stops on it before the nav.
3. **Outbound links in a local-first tool.** The GitHub links are dead offline and in snapshots. They are plain navigation and carry no data (`noopener noreferrer`).
4. **Multi-line prompt.** The copied prompt keeps the sketch's two line breaks. Terminal agent UIs without bracketed paste can treat a pasted newline as "submit" and send only the first line.
5. **Drift.** The Welcome text is maintained by hand in JS and can drift from the README and docs.

**Compatibility:** The history-state shape is unchanged (one new `view` value, `sub: null`). No API, CLI, HTTP or schema change; the change is additive.

**For the Architect (open question, non-blocking):** the line-break behaviour in item 4. The approved plan fixes the prompt "with the line breaks as written in the sketch", and this candidate follows that. A single-line variant is a one-constant change if the Architect prefers it.

All of this is recorded in `commit_draft.md` to be surfaced before the final commit.

## Verification

- `python -m pytest tests/test_dashboard_ui/test_welcome_ui.py tests/test_snapshot.py` → **16 passed**. The first run failed only on the clipboard comparison, because Windows' OS clipboard returns CRLF; the test now normalizes line endings and the copied value is otherwise exact.
- Final broad suite (plan ladder, run once): `python -m pytest tests/test_dashboard_ui tests/test_snapshot.py tests/test_packaging.py` → **474 passed, 11 skipped** (11m36s), run against the working tree, which matches the staged candidate except `commit_draft.md` (the significance bullet was added afterwards). Covers every Loop, liveness, coding, markdown, refresh, attention, brief, responsive-shell, fleet-layout and content-transport file, so Fleet/Commits/Docs/Loop navigation is unchanged (sketch Verification 7).
- Not run: the manual real-browser check from the plan (logo from Fleet, Repo and no-repo at desktop and ~400px; focus rings; a real clipboard paste). It is for the Architect before the final commit.
- **Residue:** as in checkpoint 1, the earlier session snippet is in the index, and `.gator/.gator-version` / `.gator/runtime-pin.json` are intentionally left unstaged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 2) — Welcome workspace and logo routing |
| Checkpoint base tree | `7778f63837b285d2bc992967fa3dda889090aed3` |
| Generation | 2 |
| Staged tree (candidate) | `3902f1b1725c76325881a23ba17c5b89eeedc931` |
| Changed paths in this checkpoint | 10 (A 2, M 8) |
| Loop base HEAD | `9db8fd0ef4693bcc124e75de8776929c28793f23` |
| Loop base tree | `597eaa5f4fbfbd348d04851ec24d07428133e403` |
| Current HEAD | `9db8fd0ef4693bcc124e75de8776929c28793f23` (dev) |
| Changed paths vs loop base (cumulative) | 13 |
| Unstaged / untracked residue | 2 other + 16 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 7778f63837b285d2bc992967fa3dda889090aed3 3902f1b1725c76325881a23ba17c5b89eeedc931
```

Cumulative context (approved checkpoints plus this one): `git diff 597eaa5f4fbfbd348d04851ec24d07428133e403 3902f1b1725c76325881a23ba17c5b89eeedc931`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-dashboard.md
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.css  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.html
M src/gator_command/scripts/dashboard/dashboard.js
M src/gator_command/scripts/dashboard/snapshot.py
A src/gator_command/scripts/dashboard/views/welcome.js
A tests/test_dashboard_ui/test_welcome_ui.py
M tests/test_snapshot.py
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
```

Loop residue: 16 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
