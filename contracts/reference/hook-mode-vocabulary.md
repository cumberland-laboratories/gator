---
contract-id: hook-mode-vocabulary
kind: reference
owner: base Gator
tested-by: contracts/compatibility/test_hook_modes.py
---

# Hook Mode Vocabulary

## Canonical enum

```
strict | warn | off
```

Defined at `src/gator_command/templates/gator-starter/scripts/gator-enforce.py:21`:

```python
VALID_LEVELS = {"strict", "warn", "off"}
```

## Where it lives

- **Storage**: `.gator/config.json` in each governed repo, under key
  `enforcement_level`.
- **Default**: `"strict"` (written by `gatorize.py:331` when the config
  stub is created; falls back to `"strict"` on read when the file is
  missing).
- **Reader (base Gator)**: `_read_enforcement_level()` in
  `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py:1088`.
- **Writer**: `gator enforce --level {strict|warn|off}`.

## Semantics

| Value | Effect on the pre-commit hook |
|---|---|
| `strict` | CRITICAL / HIGH findings block the commit. |
| `warn` | All findings are reported to stderr; nothing blocks. |
| `off` | Governance checks are skipped entirely; trailers are still written. |

## Contract obligations

Any component in this repo (base Gator or Enterprise) that reads or
writes an enforcement level MUST:

1. Accept exactly and only the three values above.
2. Treat any other value as invalid (raise or fall back to `strict`).
3. Default to `strict` when no value is present.

Adding a fourth mode is a versioned change: bump this contract to
`hook-mode-vocabulary-v2` and update the canonical enum + all readers
in the same commit.

## Enterprise interaction

Enterprise-side code (post-monorepo) may propose an enforcement level
via server policy. When it does, it MUST write the value into the same
`.gator/config.json` key using the same enum. No parallel key, no
alternative vocabulary.
