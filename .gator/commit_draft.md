---
message: "Tests: make liveness corrupt-session test POSIX-safe (read-only session.json)"
change-type: test
significance: low
decision-tags: [tests, ci, loop]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- `tests/test_loop_liveness_projection.py::test_corrupt_session_json_retries`: the test wrote over `session.json`, which the loop makes read-only on POSIX (`_make_readonly`), so it failed with `PermissionError` on the Ubuntu CI legs for 2.19.0 (run 37051055033). It passed on Windows, where read-only is a no-op. It now calls `_make_writable` first. Test-only, no product change.
- `scripts-loop.md` (`load_session` / `save_session`): a test-hygiene note. Loop files are read-only on POSIX only, so tests that tamper with them must make them writable first; Windows CI legs cannot catch a miss.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
