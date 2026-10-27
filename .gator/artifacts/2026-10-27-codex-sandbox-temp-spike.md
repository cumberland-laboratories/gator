---
date: 2026-10-27
type: spike
issue: 87
related: [37]
loop: loop-codex-saved-approval-recovery-2026-10-27T01-35-56Z
---

# Spike: Sandboxed Test Temp Root and Codex-Written Config (`gator loop codex`)

Answers Q1–Q5 of the #37 follow-up sketch
(`vault/artifacts/2026-10-09-codex-sandbox-temp-and-profile-block-sketch.md`),
as the gate for #87 checkpoints 3 and 4.

## Surface

- Codex CLI `0.162.1` (the launcher still pins `0.144.1` as verified).
- Windows 10 Home 19045, `[windows] sandbox = "elevated"`, `workspace-write`.
- Fixture home `~/.gator/adapters/codex/spike-87`, prepared by the launcher's
  own `plan_preparation` / `apply_preparation` and signed in by the Architect
  with `codex login`. The real `loop-home` was not touched.
- Sandboxed runs used `codex exec --sandbox workspace-write -c
  approval_policy="never"` with `-c` overrides; the model was told to run one
  command unchanged. `codex sandbox <cmd>` was rejected as evidence: it uses
  the older restricted-token sandbox (it ran as `curator`, with nothing
  writable), not the elevated sandbox that a session uses.

## Results

| Run | Setting | Result |
|---|---|---|
| E0 | none | Command runs as `codexsandboxoffline`. `%TEMP%` is writable; `%TEMP%\pytest-of-curator` (created by the Architect) is **denied** (`WinError 5`). |
| E1a | `shell_environment_policy.set = {TEMP, TMP}` → `<home>\sandbox-tmp` | `TEMP` and `tempfile.gettempdir()` show the redirect; `mkdtemp` succeeds. |
| E1b | E1a + `sandbox_workspace_write.writable_roots = [<root>]` | Same; Codex's header lists the root, and an explicit sandbox ACE is added. |
| E2a | none | `pytest tests/test_loop_codex_launcher.py`: 26 passed, **59 setup errors** (the denial). |
| E2b | E1b, root **inside** the home | 84 passed, **1 failed**: `tmp_path` lies inside `CODEX_HOME`, so `validate_home` refuses it (test `test_launch_dry_run_via_cli_routing_writes_nothing`). |
| E2c | E1b, root as a **sibling** of the home (`<home>.sandbox-tmp`) | **85 passed**, no prompt. |
| E3 | E2c | `pytest tests/test_dashboard_ui/test_loop_workspace.py` (Playwright): **173 passed** in 7 min 12 s, no prompt. |
| E4 | E2c + a temporary saved `allow` for the probe | The approved command runs **unsandboxed as `curator`**, and **inherits** the redirected `TEMP`. It is denied the `pytest-of-curator` directory the sandbox user created there. The rule file was restored byte-for-byte afterwards. |
| E5 | Interactive `codex` (Architect), hooks trusted | Codex appended `[tui]`, `[tui.model_availability_nux]`, `[hooks.state]` and two `[hooks.state.'…session_start:0:N']` tables **inside** the Gator markers, before `# END`. |
| E6 | E5 file with those tables moved above `# BEGIN`, bytes unchanged (`tomllib` parse-equal) | Relaunch: the Architect saw no second hook-trust prompt. Codex updated the relocated `"gpt-6.1-sol"` counter **in place above the block** (1 → 2), added nothing inside the block, and left both `trusted_hash` entries unchanged. |

## Answers

- **Q1 (redirect reaches sandboxed commands): yes.** `shell_environment_policy.set`
  sets `TEMP` / `TMP` for sandboxed commands, and Python's `tempfile` uses it.
- **Q2 (where the root can live): a sibling of the dedicated home**, for
  example `~/.gator/adapters/codex/loop-home.sandbox-tmp`. Inside the home it
  works for the sandbox, but then every test temp path is inside
  `CODEX_HOME`, and the launcher's own home check refuses it (E2b). The
  sibling is outside every repository and outside `%TEMP%`. Add it as an
  explicit `writable_roots` entry (E1b). Do not rely on the inherited ACL
  (see Security observation).
- **Q3 (full pytest sandboxed): yes** for the launcher suite and the Playwright
  Dashboard `test_loop_workspace.py` (E2c, E3).
- **Q4 (unsandboxed commands inherit the redirect): yes, and that is a
  trade-off.** `shell_environment_policy` applies to every command. An
  approved unsandboxed command runs as the Architect and meets the reverse
  lock-out on directories the sandbox user created (E4). No Codex mechanism
  was found that applies the variable only to sandboxed commands. In
  practice, while the redirect is active, an unsandboxed `pytest` (a saved
  approval) cannot share `pytest-of-curator` with sandboxed runs. Gator's
  own allowed `gator loop …` commands are not affected the same way:
  `mkdtemp` in the root succeeds for the Architect too (E4).
- **Q5 (Codex-written tables, relocation): yes.** Codex appends its own
  tables at the end of the file, which is inside the Gator block. When those
  tables sit above the block, Codex keeps reading and updating them in place,
  and does not ask for hook trust again (E5, E6).

## Gate decisions

- **Checkpoint 3 (config preservation): positive Q5 evidence.** Implement the
  relocation.
- **Checkpoint 4 (temp root): Q1–Q3 positive; Q4 is a trade-off.** Per the
  approved plan, this is partial evidence. Escalate to the Architect before
  writing checkpoint-4 code. The question: accept that an unsandboxed pytest
  inside a `gator loop codex` session cannot share the redirected temp root,
  or stop.

## Architect decision and implementation check

- The coding loop escalated the Q4 trade-off (decision-1). Architect
  response: **"Accept and implement."**
- Checkpoint 4 implemented the sibling root (`sandbox_temp_root`) and the two
  keys in the Gator block. Live check: `spike-87` was prepared by the
  checkpoint-4 launcher code, so the settings came from `config.toml` with no
  `-c` overrides. Then `codex exec --sandbox workspace-write -c
  approval_policy="never"` ran `python -m pytest
  tests/test_loop_codex_launcher.py -q`: **93 passed**, no prompt. The Codex
  header listed the root as writable. The relocated `[tui]` / `[hooks.state]`
  tables stayed above the block.
- Side observation (out of scope, as in the companion sketch): with the hooks
  trusted, `codex exec` ran the repository's SessionStart hooks, and both
  reported `Failed` in the sandbox.

## Security observation (outside #87 scope)

`C:\Users\curator\.gator` carries an explicit, inheritable
`CodexSandboxUsers:(OI)(CI)(M)` grant (and one other sandbox SID). Every
folder below it inherits Modify for Codex sandbox users. That includes
`~/.gator/hooks` and `~/.gator/enterprise/keys`, so any sandboxed Codex
command on this machine can write there. The grant was not made by Gator. It
is most likely an earlier Codex writable-root grant. This is reported for the
Architect's decision, and nothing was changed.

## Clean-up

The fixture home and the two temp roots (`spike-87\sandbox-tmp`,
`spike-87.sandbox-tmp`) remain for the later live checks. Remove them by
deleting `~/.gator/adapters/codex/spike-87*`. Some subfolders are owned by
the sandbox user and may need an elevated delete.
