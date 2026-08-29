# Configure Machine Preferences (`~/.gator/preferences.json`)

The unified machine-local preferences file lets an operator override Gator's default execution reality on a specific machine — the launcher Gator picks for git-hook shebang generation today, and (in a follow-on release) local hook-mode overrides.

This file is **machine-scoped**, not repo-scoped. It lives at `~/.gator/preferences.json` (Windows: `%USERPROFILE%\.gator\preferences.json`), travels with the machine, and is never committed to any repo.

## When to use

Reach for this procedure when auto-detection fails on this specific machine. The classic case is Windows Python-launcher discovery:

- `gator update` on Windows prints "**No spaceless Python Launcher (py.exe) found on this machine**" and refuses to install hooks
- `gator init` at session start reports `git hooks: degraded — hook shebang unresolvable: …`
- Field debugging shows `py.exe` sits at `%LOCALAPPDATA%\Programs\Python\Launcher\py.exe` under a username with a space (e.g. `C:\Users\John Doe\...`), so the auto-detected path is un-shebang-able (POSIX shebang can't quote spaces)

Any of those signal that this machine needs a durable local override rather than another round of hoping auto-detect resolves next time.

## Steps

1. **Confirm the failure mode.** Run whatever surface tripped the refusal (`gator update`, `git commit`, `gator init`). Read the full message — it names every location Gator checked and why each failed. If the message doesn't mention `preferences.json` at all, you have a different problem.

2. **Locate a working spaceless `py.exe` on the machine.** Options in order of ease:
   - System-wide install: the python.org installer's "Install for all users" option puts `py.exe` at `C:\Windows\py.exe` (guaranteed spaceless). Installing that gets you out of this procedure entirely.
   - `winget install Python.Launcher` if system-wide is off the table.
   - Any existing spaceless `py.exe` you can find via `where py.exe` or a filesystem search.

   If nothing spaceless exists on the machine and you can't install a system-wide launcher, this procedure can't help — Gator's hook contract requires a spaceless absolute path.

3. **Create the preferences file.** Open (or create) `%USERPROFILE%\.gator\preferences.json`. Minimal contents:

   ```json
   {
     "schema": "gator-preferences-v1",
     "python": {
       "windows_py_launcher": "C:/Windows/py.exe"
     }
   }
   ```

   Replace the launcher path with your resolved one. **Use forward slashes** (Gator normalizes on write, but hand-authored files with backslashes work too — the validator accepts both).

   Optional fields, if you want them:

   ```json
   {
     "schema": "gator-preferences-v1",
     "updated_at": "2026-08-29T14:00:00Z",
     "python": {
       "source": "user",
       "windows_py_launcher": "C:/Windows/py.exe",
       "allow_for_hook_shebang": true
     },
     "notes": "Set after per-user launcher path had a spaced username."
   }
   ```

4. **Checkpoint — validation.** The path in `windows_py_launcher` must satisfy all four rules:
   - **Basename is `py.exe`** (case-insensitive).
   - **Absolute path** (starts with a drive letter or `/`, not relative).
   - **No spaces anywhere in the path** (POSIX shebang can't quote).
   - **File actually exists** at that path.

   A file that violates any rule is caught by Gator and reported explicitly ("`invalid: spaced-path`", "`invalid: file-not-found`", etc.) — Gator will **not** silently fall back to auto-detection when a user-configured preference is broken. That's intentional: falling back would defeat the override you just wrote.

5. **Trigger a resolver run to verify.** Any of:
   - `gator update --dry-run` — the plan output should no longer name a hook-refusal.
   - `gator init` (from any governed repo) — `git hooks:` line should show a healthy status.
   - A real `git commit` — pre-commit should invoke.

## Notes

- **Malformed JSON is a loud failure, not a silent one.** If the file exists but is not parseable, Gator refuses the hook install with a message that names the parse error. Fix the JSON or delete the file — Gator will not "ignore and auto-detect" from a broken user configuration.
- **Removing the file returns to auto-detect.** Delete or rename `~/.gator/preferences.json` (or its `python:` section) to revert to Gator's default behavior. There is no undo required.
- **Backslashes in JSON strings must be escaped.** If you paste a Windows path like `C:\Windows\py.exe` into JSON, write it as `"C:\\Windows\\py.exe"` or use forward slashes `"C:/Windows/py.exe"`. Forward slashes are strongly recommended — Gator normalizes to them on write anyway.
- **This file may hold other sections later.** The `hooks:` section is reserved for a follow-on release; the schema (`gator-preferences-v1`) is additive within v1, so a follow-on release adding hook-mode preferences will extend this same file — no rename, no schema bump, no migration.
- **Interpreter vs launcher.** `windows_py_launcher` is only used where Gator needs a shebang-safe absolute `py.exe` (Windows git-hooks). It is **not** the interpreter Gator uses to run its own Python — that continues to be whatever `pipx` installed. A follow-on release may add a separate `python_executable` field for other machine-side subprocess seams; today there is no such field and no such consumer.
- **A future `gator prefs` CLI will manage this file.** Until then, manual editing is the supported path. Once the CLI ships, the recommended workflow becomes `gator prefs set-python-launcher --windows-py <path>` (equivalent to the manual edit); manual editing remains as the recovery-when-CLI-broken fallback.

## Connections

→ `.gator/vault/artifacts/2026-08-29-machine-python-preference-implementation-plan.md` — implementation plan (r3) for this feature and the resolver seam
→ `contracts/schemas/gator-preferences-v1.json` — the authoritative schema
→ `.gator/charters/scripts-core-library.md` — `read_preferences` / `_validate_launcher_candidate` / `resolve_python_launcher_for_hooks` charter entries
