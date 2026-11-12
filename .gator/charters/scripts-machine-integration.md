# Charter: Machine Integration

**Covers**: `src/gator_command/scripts/machine_integration.py`, `src/gator_command/scripts/gator-integration.py`, `src/gator_command/templates/machine/claude-settings.json`, `src/gator_command/templates/machine/codex-hooks.json`, `src/gator_command/templates/machine/gemini-settings.json`

## Owns

- Gator's SessionStart hook entries in each vendor's user-level settings (`~/.claude/settings.json`, `$CODEX_HOME` or `~/.codex/hooks.json`, `~/.gemini/settings.json`).
- The single, closed definition of which hook commands are Gator's (`is_gator_hook_command()`).
- The machine state file `~/.gator/vendor-integration.json` (schema `gator-vendor-integration-v1`) and the Codex `/hooks` review reminder.

## Does Not Own

- Running the hooks; see [`scripts-repo-lifecycle.md`](scripts-repo-lifecycle.md) (`gator-hook.py`).
- What the hooks record; see [`scripts-session-capture.md`](scripts-session-capture.md).
- Repository vendor files, which Gator no longer writes; see [`scripts-installer.md`](scripts-installer.md).
- Codex hook trust. Codex records trust against a hook's hash after the user reviews it in `/hooks`; Gator never reads or writes that state.

---

## TRIPWIRE: Gator Edits Only Its Own Entries

Gator writes only its own entries in vendor user settings. It never creates a vendor home (`~/.claude/`, the Codex home, `~/.gemini/`), never writes Codex trust state, and never overwrites a vendor or state file it cannot parse. User hooks, other groups, other events and other settings keep their order and values.

## TRIPWIRE: The Managed-Hook Grammar Is Closed

`is_gator_hook_command()` recognizes only the session-hook commands Gator has shipped: `gator hook session-X`, a quoted absolute launcher `"<path>/gator[.exe]" hook session-X`, `python|python3|py -3 .gator/[.includes/]scripts/gator-session-X.py`, and `||` chains of these that all name the same `X` (`open` or `start`). Any other `gator hook` verb, any other `.gator/` command, extra arguments, or a chain mixing a Gator clause with anything else is user content. These settings are machine-wide, so widening the grammar can delete user hooks in every repository. Add a new shipped shape to the grammar and to its preservation tests in the same change.

## TRIPWIRE: Compare Complete Entries

The fingerprint, the "already exact" short-circuit and the merge all compare `managed_form()`: the complete hook dictionaries (`type`, `command`, `timeout`, any other key), in order. Comparing commands alone would leave a stale field in place forever (for example Gemini's `timeout`, which Gemini reads in milliseconds).

---

### VENDORS / Vendor.home() / Vendor.config_path()
File: src/gator_command/scripts/machine_integration.py
The closed table of the three vendors: key, display name, home resolver, settings filename, machine template. Codex's home is `$CODEX_HOME` when set, else `~/.codex/`.
! A vendor is present when its home directory exists. A new vendor is a code change, not configuration.

### is_gator_hook_command(cmd)
File: src/gator_command/scripts/machine_integration.py
True only for a command in the closed grammar (see the TRIPWIRE). `_clause_verb()` parses one `||` clause; every clause must parse and name the same verb.
<- `merge_document()`, `strip_managed_entries()`, `status()`, and the repository vendor cleanup (`gatorize/vendor_cleanup.py`)
! The single predicate. Do not copy it into another module.

### load_template() / template_hooks() / managed_form() / fingerprint()
File: src/gator_command/scripts/machine_integration.py
Read a `templates/machine/` file, take its SessionStart hook list, and canonicalize it (`sort_keys`, compact JSON). `fingerprint()` is SHA-256 of that form.
Filesystem: `templates/machine/*.json` (R)
! Hook commands are exactly `gator hook session-open` / `gator hook session-start`, which never change between versions, so Codex trust survives upgrades. Timeouts: Claude 10 s, Codex 10 s, Gemini 10000 ms.

### merge_document(doc, hooks) / merge_hooks_into_settings(settings_path, template)
File: src/gator_command/scripts/machine_integration.py
Converge the managed SessionStart entries to the template's complete dictionaries. Already exact and in one group → no change. Otherwise all managed entries are removed from every group, a group they alone filled is dropped, and the template goes first in the first group that held one (its other keys and user hooks kept), or into a new group. `merge_hooks_into_settings()` returns `add` | `update` | `unchanged` | `malformed`.
Filesystem: one vendor settings file (RW, atomic)
<- `ensure()`
! Invalid JSON, a non-dict document or `hooks`, or a non-list `SessionStart` is `malformed` and is never written. Creates no directory.

### strip_managed_entries(doc)
File: src/gator_command/scripts/machine_integration.py
Remove managed entries; drop a group left empty, then `SessionStart`, then `hooks`. Returns `(doc, removed_count)`.
<- `remove()`, and the repository vendor cleanup (`gatorize/vendor_cleanup.py` `plan_vendor_cleanup()` / `apply_vendor_cleanup()`)
! Shared so machine removal and repository cleanup cannot diverge.

### ensure(home=None, env=None, templates_dir=None)
File: src/gator_command/scripts/machine_integration.py
Connect every present vendor, then record each connected vendor (`config_path`, `fingerprint`, `connected_at`) in the state file. Returns `changed`, `recorded`, `codex_newly_connected`, `problems`, `messages`; the caller prints `messages` and `problems` to stderr.
Filesystem: vendor settings (RW), `~/.gator/vendor-integration.json` (RW, atomic)
! An unreadable or unknown-schema state file changes nothing, not even vendor files; `gator integration remove` is the reset.
! State recording is independent of vendor writes: a missing or different record is written even when every vendor file was already exact. Nothing is written when the desired records equal the stored ones; a version change alone never forces a write.
! A malformed vendor file is a problem for that vendor only: not written, its record removed, other vendors proceed. A vendor whose home is gone loses its record.
! `connected_at` is kept while the fingerprint is unchanged. A new or changed Codex record is "newly connected" and adds the `/hooks` reminder line.

### remove(home=None, env=None)
File: src/gator_command/scripts/machine_integration.py
Strip Gator's entries from every vendor settings file that exists, whether or not the vendor is present. Delete a file only when nothing else remains. Then delete the state file.
! Works without the state file: Gator's entries are found in the vendor files themselves. A malformed file is reported, never written.

### status(home=None, env=None, templates_dir=None)
File: src/gator_command/scripts/machine_integration.py
Read-only. Per vendor: `present`, `connected` (read from the vendor file: managed entries exact), `problem`, `config_path`, `connected_at`. Also `state` (`ok` | `missing` | `unreadable`) and `codex_reminder_due`.
! The Codex reminder is a reminder, not a trust check: it is due while Codex is connected and the dismissed fingerprint differs from the current one. A bootstrapped state file starts undismissed.

### dismiss_codex_reminder(home=None, env=None, templates_dir=None)
File: src/gator_command/scripts/machine_integration.py
Store the current Codex fingerprint as dismissed. Returns False and writes nothing without a readable state file.

### main() / cmd_status() / cmd_remove() / cmd_dismiss() — `gator integration`
File: src/gator_command/scripts/gator-integration.py
`status [--json]` prints `status()` (one line per tool: Connected, Not connected, Not installed, or Problem, as words, never colour alone); `remove` runs `remove()` and says the next ordinary `gator` command reconnects unless `GATOR_NO_VENDOR_INTEGRATION=1`; `dismiss-codex-reminder` runs `dismiss_codex_reminder()`.
<- `cli.py` verb `integration`
! `integration` is in `cli.py` `NO_ENSURE_VERBS`: running it never calls `ensure()`, so `remove` is not undone by its own command.
! Exit 1 on an unreadable state file (status, dismiss) or an unreadable vendor file (remove); 2 on usage errors.

### Trigger and Dashboard surfaces (callers)
`cli.py` `_ensure_machine_integration()` calls `ensure()` before every ordinary verb and `--explain` (see [`scripts-cross-cutting.md`](scripts-cross-cutting.md)). The Dashboard reads `status()` through `GET /api/integration` and dismisses through `POST /api/integration/dismiss-codex-reminder` (see [`scripts-dashboard.md`](scripts-dashboard.md)); it never calls `ensure()` itself (`gator dashboard` already ran it).

## Before Changing This Module

- Use temporary `home` and explicit `env` in every test; never touch the real home.
- Keep the preservation tests for user `gator hook` verbs and `.gator/` commands passing.
- Changing a template changes its fingerprint, so Codex asks for a new `/hooks` review on every machine. Change templates only deliberately.

## Connections

-> [Session Boot and Hook Dispatch](scripts-repo-lifecycle.md) - the `gator hook` commands these entries run
-> [Vendor Session Capture](scripts-session-capture.md) - what the session hooks record
-> [Gatorize Installer](scripts-installer.md) - repositories no longer carry vendor files
-> [Cross-Cutting](scripts-cross-cutting.md) - CLI and runtime contracts
