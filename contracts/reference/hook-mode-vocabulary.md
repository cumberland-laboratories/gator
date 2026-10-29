---
contract-id: hook-mode-vocabulary-v2
kind: reference
owner: base Gator
tested-by: contracts/compatibility/test_hook_modes.py
---

# Hook Mode Vocabulary

**v2 (2026-10-28): the commit policy is machine-local.** The enum is
unchanged. What changed is where a level is stored and who may set it: a
level relaxed by one engineer must never reach another engineer through
Git. v1 stored the level in the tracked `.gator/config.json`; that key is
no longer read.

## Canonical enum

```
strict | warn | off
```

`off` remains part of the vocabulary (Enterprise's `GATOR_HOOK_MODE` may
use it). The **machine-local** subset is `strict | warn`, declared at
`src/gator_command/templates/gator-starter/scripts/gator-enforce.py`:

```python
VALID_LEVELS = {"strict", "warn"}
```

and in `precommit_local_policy.LOCAL_LEVELS`.

## Where it lives

- **Storage**: per clone, in Git's private area:
  `$(git rev-parse --git-path gator-commit-policy.json)`, as
  `{"schema": "gator-commit-policy-v1", "level": "warn"}`. It is never
  staged and never pushed. `strict` is stored as the absence of the file.
- **Default**: `"strict"`: the file is absent, unreadable, or invalid.
- **Reader (base Gator)**: `_read_enforcement_level(repo_root)` in
  `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`,
  through `precommit_local_policy.read_level()`.
- **Writers**: the Dashboard Fleet **Warn** control
  (`POST /api/repo/<name>/commit-policy`) and
  `python gator-enforce.py --level {strict|warn}`, both through
  `precommit_local_policy.write_level()`.
- **Tracked `.gator/config.json` `enforcement_level`**: not read for the
  policy. A committed `warn`/`off` only produces the advisory warning
  `tracked-commit-policy-ignored`. `gatorize` still writes a `"strict"`
  stub there, which is harmless.
- **Git record**: a commit made under a relaxed policy carries the
  trailer `Gator-Commit-Policy: <level>`. Strict commits carry none.

## Semantics

| Value | Effect on the pre-commit hook |
|---|---|
| `strict` | Missing charter updates block; dangerous patterns pause for an Architect decision. |
| `warn` | All findings are reported; nothing blocks. The commit records `Gator-Commit-Policy: warn`. |
| `off` | Enterprise only (`GATOR_HOOK_MODE`): governance checks are skipped; trailers are still written. Not a local level. |

## Contract obligations

Any component in this repo (base Gator or Enterprise) that reads or
writes an enforcement level MUST:

1. Accept only values from the canonical enum, and locally only
   `strict | warn`.
2. Treat any other value as invalid (raise or fall back to `strict`).
3. Default to `strict` when no value is present.
4. Never store a level in a file that Git tracks.

Adding a fourth mode is a versioned change: bump this contract and
update the canonical enum + all readers in the same commit.

## Enterprise interaction

When Enterprise manages a repository (`.gator/enterprise.json` with
`enabled: true`), its hook mode decides: the bundled hook reads
`GATOR_HOOK_MODE` and falls back to `strict`, never to a repository
file. The machine-local file is ignored there, and the Dashboard refuses
to write it (409).
