# governance-source.json Schema Reference

Schema for `.gator/governance-source.json` — the file that tells a governed repo where its org policy comes from.

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `policy_file` | string | yes | Relative path to the policy file within the command post repo. Default: `gator-command/org-policy.md` |
| `remote_url` | string | no | Git remote URL for the command post. Portable across machines. Primary source for `--sync` when local path is unavailable. |
| `_local_path_hint` | string | no | Absolute path to the command post on this machine. Machine-local — may not resolve on other machines. Used as fast path when available. |
| `_local_path_note` | string | no | Human-readable note explaining the local path hint is machine-specific. |

## Example

```json
{
  "policy_file": "gator-command/org-policy.md",
  "remote_url": "https://github.com/org/gator-command.git",
  "_local_path_hint": "/home/user/code/gator-command",
  "_local_path_note": "Machine-local — may not resolve on other machines"
}
```

## Resolution Order

1. `_local_path_hint` → resolved via `normalize_path()`, used if directory exists
2. `remote_url` → used for `--sync` fetch when local path is absent or inaccessible

## Related Files

- `.gator/policy-link.json` — provenance manifest written by `--sync`, records what was cached and when
- `.gator/policy-cache/org-policy.md` — the materialized policy file
- `.gator/command-post.md` — legacy thin link (still used as fallback for deriving governance source)

## Created By

- `gator policy-status --init` generates this file from the existing thin link
- Manual creation is also valid

## Consumed By

- `gator-policy-status.py` — loads via `load_governance_source()`
- `gator-fleet-report.py` — reads indirectly via `compute_sync_state()` for policy_link
- `gator-drift.py` — reads indirectly via `compute_sync_state()` for policy-* findings
