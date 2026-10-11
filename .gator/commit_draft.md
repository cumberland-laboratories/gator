---
message: "Welcome: topic frames span the full main-pane width"
change-type: fix
significance: routine
decision-tags: [dashboard, welcome]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- `dashboard.css`: `.welcome-body` drops the #72 `max-width: 760px` and its side padding (now `padding: 16px 0 0`), so each Welcome topic iframe spans the full main-pane content width, aligned with the tab bar. The documents set their own reading width inside the frame (Architect direction after reviewing `4b91390` in the source Dashboard; this resolves the approved plan's assumption 4).
- `test_welcome_ui.py`: `test_welcome_frames_lazy_persistent_sandboxed` now asserts the selected frame's left and right edges match the tab bar's (±1px).
- Charter `scripts-dashboard-ui.md`: the Welcome layout note describes the full-width body.
