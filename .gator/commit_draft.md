---
message: "CI: raise dashboard-ui job timeout to 20 minutes"
change-type: maintenance
significance: low
decision-tags: [ci, release]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- `.github/workflows/source-ci.yml`: the `dashboard-ui` `timeout-minutes` goes from 10 to 20. On 2.19.0 dev CI (run 37063620912) the Windows leg was cancelled at the cap with 255 of 332 tests passed and none failed. Windows setup takes about 4 minutes and the grown suite about 8.
- `release-pipeline.md` (Workflow A): records the cap and why.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
