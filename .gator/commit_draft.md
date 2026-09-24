---
message: "Bump to 2.15.0 — dashboard loop workspace"
change-type: release
significance: notable
decision-tags: [release]
agent: claude-opus-4-6
architect: ag
---

# Session Change Log

- Bump version to 2.15.0 in `pyproject.toml`, `VERSION`, and `CHANGELOG.md`
- Fix snapshot builder: add `loop.js` to inlining regex and script block (CI was failing because the new script tag wasn't matched)
- Update `test_snapshot.py` to include `loop.js` in external reference assertions
