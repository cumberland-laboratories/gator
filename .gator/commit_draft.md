---
message: "Dashboard: loop workspace refresh-failure visibility (#44)"
change-type: fix
significance: notable
decision-tags: [dashboard, loop, ui]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- #44 remainder, refresh-failure visibility (sketch `.gator/vault/artifacts/2026-10-01-loop-workspace-refresh-failure-sketch.md`), in `dashboard/views/loop.js`:
  - A failed background poll of `/status` or `/events` returns without rendering, so the last valid workspace survives: content, artifacts, open Architect controls and expanded sections. A text-led "Refresh failed — retrying." notice appears, with `role="status"`. The next successful full refresh clears only that notice.
  - `#loop-region-notice` now has named slots. `refresh` is owned solely by `pollLoop()` through `setRefreshFailed()`, which writes only on a state change and is guarded by generation, selection and an attached root. `action` holds the Continue, Re-notify and Reopen notices, written through `noticeSlot()`. Recovery never erases an Architect message.
  - Fixed a latent destructive case: `fetchEvents()` returned `[]` on HTTP errors, so a failed `/events` poll rendered as an empty history and pruned event-derived artifact sections. It now returns `null` on failure. Initial load still renders `[]`, keeping its existing behavior.
- `dashboard.css`: the `.loop-refresh-failed` style (dashed and solid borders, no hue dependence).
- New `tests/test_dashboard_ui/test_loop_refresh_ui.py` (6 Playwright tests):
  - status failure keeps the workspace, with an open interject input and an expanded artifact, and recovers;
  - an events failure never prunes artifacts;
  - recovery keeps the Architect action notice;
  - repeated failures cause zero mutations;
  - a stale in-flight failure can't touch a new selection;
  - initial-load failure is unchanged.

  The 4 behavior tests were verified to fail on the pre-change `loop.js`.
- `scripts-dashboard-ui.md`: notice slots, refresh-failure ownership and guards, and the `fetchEvents` null contract.
- `scripts-dashboard.md`: the server side of the failure contract. Errors must be non-2xx; a genuine no-events loop returns 200 `{"events": []}`. The UI treats anything else as a refresh failure, never as an empty history.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
