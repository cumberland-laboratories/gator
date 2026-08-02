---
last-touched: 2026-06-20
category: reference
tags: [windows, pytest, testing, operations]
---

# Windows pytest tempdir note

## Summary

On this machine, `pytest` can fail before or after tests run because of Windows ACL issues in temporary directories.

Two variants have shown up:

- a broken global temp subtree at `%LOCALAPPDATA%\Temp\pytest-of-curator`
- repo-local temp directories created under a different Windows identity when tests are launched from the Codex sandbox

The reliable workaround is to run pytest from the normal `curator` shell and force a repo-local base temp directory.

## Recommended command

```powershell
python -m pytest tests/test_session_aggregator.py -q --basetemp .tmp\pytest-session-aggregator
```

This avoids the stale global `pytest-of-curator` path and keeps test temp files inside the repo.

## When it fails from Codex

If Codex launches pytest inside the sandbox, Windows may create `.tmp\pytest-*` with ACLs that the normal user cannot traverse. In that case:

1. remove the stuck directory from an elevated shell if needed
2. rerun the same `python -m pytest ... --basetemp ...` command from the normal user shell

## If the global temp root is corrupted

If `%LOCALAPPDATA%\Temp\pytest-of-curator` becomes inaccessible, repair or remove it from an elevated shell:

```powershell
takeown /f C:\Users\curator\AppData\Local\Temp\pytest-of-curator /r /d y
icacls C:\Users\curator\AppData\Local\Temp\pytest-of-curator /grant "curator:(OI)(CI)F" /t
icacls C:\Users\curator\AppData\Local\Temp\pytest-of-curator /inheritance:e /t
Remove-Item -Recurse -Force C:\Users\curator\AppData\Local\Temp\pytest-of-curator
```

## Practical rule

For targeted Windows test runs in `gator-command`, prefer:

- `python -m pytest ...`
- `--basetemp .tmp\<run-name>`
- execution from the normal Windows user shell, not the Codex sandbox, when ACL behavior matters
