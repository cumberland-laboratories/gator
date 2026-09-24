---
message: "Fix start.lock race on Linux CI"
change-type: fix
significance: routine
decision-tags: [dashboard, loop]
agent: claude-opus-4-6
architect: ag
---

# Session Change Log

- Fix `test_start_lock_released_after_success` and `test_start_lock_released_on_active_conflict` race condition on Linux: add retry loop for lock acquisition after HTTP response, since server's `finally` block may not have executed by the time the client processes the response
