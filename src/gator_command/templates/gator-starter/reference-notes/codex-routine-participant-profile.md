# Codex Routine Participant Profile — Opt-In Rule for Loop Commands

**Audience:** an Architect who runs a Codex loop participant and wants to stop
approving routine `gator loop` commands one by one.

## Purpose

In Codex's `workspace-write` sandbox, `.git` is read-only. Gator's candidate
check (`git write-tree`) therefore fails, so a Codex Reviewer cannot approve
and a Codex Draftor cannot submit an implementation without a host approval
prompt. The failure looks like this:

```
Error: Cannot verify the live candidate before approval: git_busy (fatal: Unable to create '…/.git/index.lock': Permission denied)
```

This profile is one Codex rule that allows exactly five `gator loop`
subcommands. It is **opt-in** and lives in a **dedicated** Codex home, so
your normal Codex sessions never see it.

## Trust Cost — Read Before Opting In

Codex documents an `allow` rule as: *"Run the command outside the sandbox
without prompting."* When this profile is active:

- each matched `gator loop …` command runs **outside the Codex sandbox**;
- every process it starts runs there too, including Gator's Git calls;
- they run with **your full user rights**.

Whatever `gator` resolves to on `PATH` gets those rights. Use the profile only
when you trust the installed Gator CLI and your `PATH`.

The profile does **not** weaken Gator. Gator still enforces the token, role,
turn, and staged-tree freshness, and it still refuses stale approvals. All
other commands in the session stay sandboxed: `git add`, `git commit`, a
direct `git write-tree`, writes outside the workspace, and any other `gator`
command.

## Verified Surface

- Codex CLI `0.144.1` on Windows 10 (19045), with
  `[windows] sandbox = "elevated"` and `workspace-write`.
- Gator `2.23.0`.
- The interactive TUI was not observed. The evidence comes from
  `codex exec` runs. "No prompt" in an interactive session rests on the Codex
  documentation for `allow`.
- Other Codex surfaces, versions, or operating systems are **untested**.
  Verify them with the checklist below before you rely on the profile.

Evidence: Gator issue #37, spike artifact
`2026-10-08-codex-routine-profile-spike.md` in the Gator source repository.

## Quick Setup: `gator loop codex`

From a governed repository, one command prepares the dedicated home and
starts Codex in it:

```
gator loop codex
```

It does this on every run:

1. Uses the dedicated home `~/.gator/adapters/codex/loop-home` (or
   `--home <path>`). It refuses your normal Codex home, a home inside the
   repository, and a home under the temp directory.
2. Writes `rules\default.rules` with exactly the rule in Setup step 3, and a
   Gator-owned block at the end of `config.toml` with
   `[windows] sandbox = "elevated"` and a trust entry for this repository.
   Your other settings in that `config.toml` are kept.
3. Checks the rule with `codex execpolicy check`: `gator loop status` must be
   allowed, and `git write-tree` and `gator loop end` must match nothing.
4. Prints the trust cost, then starts `codex` with `CODEX_HOME` set for that
   Codex process only. Your terminal's environment does not change.

On the first run Codex asks you to sign in for this home. Gator does not copy
or read your normal Codex login. Then continue as usual:
`gator loop join` with your role prompt, and optionally `/goal` (see
`codex-loop-participant.md`).

`gator loop codex --dry-run` shows the home, the rule, the trust entry, and the
launch without writing or starting anything.

The command never starts, joins, or authorizes a loop, and it never takes a
token. It **stops without changes** when it finds a rule file it did not
write, another file in `rules\`, your own `[windows]` table or trust entry for
this repository outside its block, or a failed rule check. In that case use
the manual Setup below. It runs only on Windows, the verified surface. A Codex
version other than the verified one prints a warning; the rule check still
runs.

To remove it, delete `~/.gator/adapters/codex/loop-home`.

## Setup

Codex reads rules from the `rules/` folder of its config home. A `--profile`
cannot carry a rule. The opt-in unit is therefore a **separate `CODEX_HOME`**
that you select for one terminal only. Never add this rule to your normal
`~/.codex`, because every session there would get it.

1. **Create a dedicated home outside any temporary directory.** Codex refuses
   to create its helper binaries under `%TEMP%`.
   Example: `C:\Users\<you>\.codex-gator-loop`.
2. **Create `config.toml` in that folder.** Pre-trust the governed repository.
   In the spike, a `codex exec` run in an untrusted folder added a trust entry
   to the home it ran from. Copy your sandbox setting from your normal config:

   ```toml
   [windows]
   sandbox = "elevated"

   [projects.'C:\path\to\your\repo']
   trust_level = "trusted"
   ```

3. **Create `rules\default.rules` in that folder.** Use exactly this rule:

   ```python
   prefix_rule(
       pattern = ["gator", "loop", ["status", "wait", "submit-draft", "submit-review", "submit-implementation"]],
       decision = "allow",
       justification = "Gator loop participant routine commands; Gator enforces token, role, turn and candidate freshness.",
       match = [
           ["gator", "loop", "status", "--token", "glp_x"],
           ["gator", "loop", "submit-review", "--token", "glp_x", "--file", "r.md", "--approve"],
       ],
       not_match = [
           ["gator", "loop", "end", "--token", "glp_x"],
           ["gator", "gatorize", "."],
           ["git", "write-tree"],
       ],
   )
   ```

   Save both files as UTF-8 **without** a byte-order mark. Windows PowerShell
   5.1 `Set-Content -Encoding utf8` adds one. Use an editor, or
   `[IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))`.
4. **Check the rule:**

   ```
   codex execpolicy check --rules C:\Users\<you>\.codex-gator-loop\rules\default.rules -- gator loop status --token x
   codex execpolicy check --rules C:\Users\<you>\.codex-gator-loop\rules\default.rules -- git write-tree
   ```

   The first command must print `"decision":"allow"`. The second must print
   `{"matchedRules":[]}`. A syntax error makes Codex refuse to start, so a
   broken rule fails closed.
5. **Log in once for that home** in a new PowerShell window:

   ```
   $env:CODEX_HOME = 'C:\Users\<you>\.codex-gator-loop'
   codex login
   ```

   `CODEX_HOME` also holds Codex's login, so the dedicated home needs its own.
   The spike copied an existing `auth.json` into the home instead. `codex login`
   is the documented route and avoids copying credentials. On the first run
   from a new home, Codex re-runs its Windows sandbox setup. In the spike it
   reused the existing sandbox users and showed no prompt.

6. **Start the participant session from that same window:** `cd` to the
   repository, run `codex`, join the loop, and optionally enter Goal mode (see
   `codex-loop-participant.md`). Set `CODEX_HOME` only in that window. Never
   set it as a user or machine environment variable.

## Covered and Not Covered

| Covered (runs unsandboxed, no prompt) | Not covered (normal Codex policy) |
|---|---|
| `gator loop status` | `gator loop end`, `pause`, `unblock`, `extend`, `start` and other `gator` commands |
| `gator loop wait` | `git add`, `git commit` and every other Git write |
| `gator loop submit-draft` | tests, builds and package installs |
| `gator loop submit-review` | any compound command (`…; …`, pipes, variables) |
| `gator loop submit-implementation` | anything outside the repository |

Only simple, single commands are known to match. Codex runs commands through
`powershell.exe -Command`, and the spike showed that it matches a single plain
command against the rule. The Codex rules documentation says compound or
variable-bearing scripts are not split, so they are expected to run sandboxed.
This was not tested live. A Draftor still needs one host approval for
`git add` before it submits.

## Participant Guidance

- **Read Gator's text, not the exit code.** Windows PowerShell 5.1 reports
  exit `1` for every non-zero exit, so `2` (loop ended) and `3` (still
  waiting) look the same. Use the output: `Loop ended.` means stop, and
  `Your turn: YES` means act. Otherwise reissue the bounded `wait`.
- **Under Codex, a `git_busy … index.lock … Permission denied` error is a
  host denial.** It is not Git contention, a code finding or an Architect
  decision. Gator's `git_busy` label does not say so. It usually means the
  profile is not active in this session: the wrong `CODEX_HOME`, or a
  missing or edited rule. Approve the host prompt, or tell the Architect out
  of band. Do not `gator loop escalate` for it, and do not submit findings
  about it.
- Copy the role token exactly. A mis-copied token fails safely with
  `Loop directory not found`.

## Removal

Delete the dedicated home folder, for example
`C:\Users\<you>\.codex-gator-loop`. Nothing was added to your normal Codex
home, Git config or environment. A Codex session started without that
`CODEX_HOME` behaves exactly as before.

## Fallback

Without the profile, use the ordinary workflow in `codex-loop-participant.md`:
Goal mode with bounded `wait`, approving the host prompt when a submission
needs Git access.

## Validation Checklist (repeat on a new surface or version)

1. Without the profile, a Reviewer `submit-review --approve` fails with the
   `index.lock` denial, and the loop stage does not change.
2. With the profile, the same approval succeeds. The Reviewed Candidate shows
   `Live candidate unchanged at review: yes`.
3. With the profile, a direct `git write-tree` in the same session is still
   denied.
4. With the profile, an approval after the staged tree has changed is refused
   by Gator ("The candidate changed since submission").
5. After you remove the profile, your normal Codex home and its
   `codex execpolicy check` results are unchanged.
