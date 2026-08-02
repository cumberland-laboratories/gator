---
contract-id: machine-identity
kind: reference
owner: base Gator
tested-by: contracts/compatibility/test_gator_layout.py
---

# Machine Identity

## File location

```
~/.gator/machine-id
```

- Per-user, per-machine.
- Written on first read (`_create_machine_id` in
  `src/gator_command/scripts/gator-machine-id.py:80`).
- Never committed to git; never lives inside a repo's `.gator/`.

## File format

**NOT** JSON. A line-oriented `key: value` file, UTF-8 encoded, LF line
terminators, trailing newline.

```
id: 550e8400-e29b-41d4-a716-446655440000
hostname: my-desktop
label: alan-home-desktop
created: 2026-01-15
```

## Required keys

| Key | Format | Notes |
|---|---|---|
| `id` | RFC 4122 UUID (lowercase, hyphenated, 36 chars) | Generated once via `uuid.uuid4()`. Never rewritten. |
| `hostname` | free text | `platform.node()` at creation time. |
| `label` | free text | Defaults to hostname; operator-editable via `gator machine-id --label`. |
| `created` | `YYYY-MM-DD` | ISO date of file creation. |

Missing `id` triggers a full regeneration on next read
(`get_machine_id` in `gator-machine-id.py:74`) — treat this as a
recovery path, not a normal case.

## Contract obligations

Any component that reads machine identity MUST:

1. Parse using key: value line format, not `json.loads`.
2. Validate `id` matches the UUID pattern before use.
3. Fall back to the label = hostname convention when `label` is absent.

Any component that writes machine identity MUST:

1. Use `str(uuid.uuid4())` for a new `id` (never a hash of user data).
2. Preserve unrecognized keys on rewrite.
3. Write UTF-8 with trailing newline.

## Snippet emission dependency

`gator-session-snippet-v2` requires both `machine_id` and
`machine_label` fields. The snippet emitter reads them via
`_read_machine_id()` / `_read_machine_label()` in `precommit_session.py`.
If the machine-id file is missing or malformed, snippet emission MUST
regenerate the file, not skip the snippet.
