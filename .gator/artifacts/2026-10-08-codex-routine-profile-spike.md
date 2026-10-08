---
date: 2026-10-08
type: spike-evidence
issue: 37
feature: codex-routine-loop-command-profile-spike
planning-loop: codex-routine-loop-command-profile-spike-2026-10-07T23-26-59Z
coding-loop: codex-routine-loop-command-profile-spike-2026-10-07T23-37-15Z
status: complete-published-opt-in
---

# #37 Phase 1 — Codex Routine Loop-Command Profile Spike: Evidence

This artifact records the evidence for the #37 Phase-1 spike. Each coding
checkpoint adds one section. Checkpoint 1 records the environment, the Codex
documentation, the isolation decision, the preflight state of the normal
Codex home, the fixture, and the baseline denial without a profile.

Role tokens are never written here. Command output shows them as
`glp_<redacted>`.

## 1. Environment (pinned)

| Item | Value |
|---|---|
| Codex surface | Codex CLI (npm package `@openai/codex`, run through `codex.ps1`) |
| Codex version | `codex-cli 0.144.1` |
| OS | Microsoft Windows 10 Home, `10.0.19045` |
| Codex Windows sandbox | `[windows] sandbox = "elevated"` in the normal `config.toml` |
| Sandbox mode used for probes | `workspace-write` (`-c sandbox_mode="workspace-write"`) |
| Approval policy | not set in the normal `config.toml` (Codex default) |
| Workspace trust | the governed repo `\\?\C:\Users\curator\code2\gator` is `trust_level = "trusted"`; the fixture is not listed (untrusted) |
| Gator | `gator 2.23.0` (pipx) |
| Git | `git version 2.40.0.windows.1` |
| `CODEX_HOME` | not set at process, user or machine scope; the normal home is `~\.codex` |

The results apply to this surface only. The desktop app, IDE extensions,
macOS and Linux are untested.

## 2. Codex documentation consulted (retrieved 2026-10-07)

`developers.openai.com/codex/*` URLs now return HTTP 308 redirects to
`learn.chatgpt.com/docs/*`. The redirected pages were read.

- **Rules** — <https://learn.chatgpt.com/docs/agent-configuration/rules>
  - Load locations: the user layer `~/.codex/rules/default.rules`, Team Config
    locations, and project-local `<repo>/.codex/rules/` (only when the
    project is trusted). The `rules/` folder of every active config layer is
    scanned at startup.
  - `prefix_rule(pattern=[...], decision=..., justification=..., match=...,
    not_match=...)`; the decision is `allow`, `prompt` or `forbidden`, and the
    default is `allow`. When several rules match, the most restrictive wins:
    `forbidden` > `prompt` > `allow`.
  - **`allow`: "Run the command outside the sandbox without prompting."**
  - Shell wrappers: linear chains in `bash -lc` / `bash -c` / `zsh` / `sh` are
    split into separate commands. Scripts with redirections, substitutions,
    variables, wildcards or control flow are matched as one string. The page
    does not mention PowerShell wrapping.
  - Test with `codex execpolicy check --pretty --rules <file> -- <command>`.
- **Approvals and security, protected paths** —
  <https://learn.chatgpt.com/docs/agent-approvals-security>, verbatim:
  > In the default `workspace-write` sandbox policy, writable roots still
  > include protected paths:
  > * `<writable_root>/.git` is protected as read-only whether it appears as a
  >   directory or file.
  > * If `<writable_root>/.git` is a pointer file (`gitdir: ...`), the resolved
  >   Git directory path is also protected as read-only.
  > * `<writable_root>/.agents` is protected as read-only when it exists as a
  >   directory.
  > * `<writable_root>/.codex` is protected as read-only when it exists as a
  >   directory.
  > * Protection is recursive, so everything under those paths is read-only.
- **Config reference** — <https://learn.chatgpt.com/docs/config-file/config-reference>
  - `sandbox_mode`: `read-only` | `workspace-write` | `danger-full-access`.
  - `approval_policy`: `on-request` | `never` | granular form (`untrusted` is
    deprecated).
  - `sandbox_workspace_write.writable_roots` adds writable roots.
  - Profiles: `[profiles.x]` tables or `<name>.config.toml` files, selected
    with `--profile`.
  - `windows.sandbox`: `unelevated` | `elevated` | `mxc`.
  - Project `.codex/config.toml`, hooks and rules load only for trusted
    projects.
- **Environment variables** —
  <https://learn.chatgpt.com/codex/config-file/environment-variables>,
  verbatim: `CODEX_HOME` "Sets the root for Codex state, including config,
  auth, logs, sessions, skills, and standalone package metadata. If you set
  it, the directory must already exist." The default is `~/.codex`.
- **Windows sandbox** — <https://learn.chatgpt.com/docs/windows/windows-sandbox>
  - Elevated mode uses "dedicated lower-privilege sandbox users, filesystem
    permission boundaries, firewall rules, and local policy changes".
  - Unelevated mode uses a restricted token derived from the current user and
    ACL boundaries.
  - Windows 10 1809+ has "best effort" support.

**Gaps in the documentation:**
- No page states whether child processes of an `allow`-ed command also run
  outside the sandbox. The rules page says the command itself runs outside
  the sandbox; the probes in checkpoint 2 settle the rest.
- No page states how a `powershell.exe -Command "..."` wrapper is matched.

### Answers to sketch Q1–Q3 from the documentation

| Q | Documentation answer | Still to observe |
|---|---|---|
| Q1: supported mechanism | `prefix_rule` with `decision="allow"` in a rules file. Writable-root config cannot help, because `.git` stays protected inside every writable root. | how it matches a PowerShell-wrapped invocation (cp2) |
| Q2: child Git `index.lock` work | An `allow` rule runs the matched command **outside the sandbox**, so its child Git should be able to write `.git`. Within the sandbox, no documented setting makes `.git` writable. | P-write / P-child (cp2) |
| Q3: scope | Rules load per config layer (user home, Team Config, trusted project). They are not profile-scoped. Per-session scope is possible only through a separate `CODEX_HOME`. A trusted project's `.codex/rules/` gives repository scope, but every session in that trusted repository gets it. | confirm empirically that rules load from `$CODEX_HOME/rules` (cp2) |

## 3. Isolation discovery verdict

| Item | Finding | Source |
|---|---|---|
| (a) Separate config home for one process | **Yes.** `CODEX_HOME`, set at process scope only; the directory must exist. | environment-variables page |
| (b) Where rules and profiles load from | rules: `rules/` of each config layer (user = `CODEX_HOME`); profiles: `[profiles.x]` or `<name>.config.toml` in the config home | rules page; config reference |
| (c) Per-session selector | `--profile` selects config keys only; rules are **not** profile-scoped. `-c` overrides config keys only. | config reference |

**Verdict: isolation is feasible.** The spike rule is written only under a
spike `CODEX_HOME` (scratchpad), and that variable is set only on the one
process that runs the Codex session. The normal home is never written.
**Consequence for packaging:** a profile cannot carry a rule, so the per-session
opt-in unit for a pass is a dedicated `CODEX_HOME`, not a `--profile`.

## 4. Preflight state of the normal Codex home

SHA-256 manifest (config and rules only; the credential file is not read or
hashed):

```
eeabec50eef569901f0d9fbf9dc547460588c185bcfa3cb3a128628429ca992f  ~\.codex\config.toml
3a1f0627dfef6e17e9bbd9c74c14c037b7f5be56167d66346f842824a125707f  ~\.codex\rules\default.rules
```

- `[profiles.*]` tables in `config.toml`: 0. `*.config.toml` profile files: none.
- The governed repo has `.codex/` (tracked), containing only `hooks.json`
  and no `rules/`.

`codex execpolicy check --rules ~\.codex\rules\default.rules -- <cmd>` from the
normal home (`no-match` means `{"matchedRules":[]}`):

| Command | Decision |
|---|---|
| `gator loop status --token glp_PLACEHOLDER` | no-match |
| `gator loop wait --token glp_PLACEHOLDER --max-seconds 45` | no-match |
| `gator loop submit-draft --token glp_PLACEHOLDER --file p.md` | no-match |
| `gator loop submit-review --token glp_PLACEHOLDER --file r.md --approve` | no-match |
| `gator loop submit-implementation --token glp_PLACEHOLDER --checkpoint cp1 --file i.md` | no-match |
| `gator loop end --token glp_PLACEHOLDER` | no-match |
| `git write-tree` | no-match |
| `git commit --allow-empty -m probe` | no-match |
| `git update-ref refs/heads/x HEAD` | no-match |
| `powershell.exe -Command "gator loop submit-review --token glp_PLACEHOLDER --file r.md --approve"` | no-match |

No normal-home rule covers a loop command or the probe Git writes.

**Observation (not changed by this spike):** the normal `default.rules` (93
lines) already holds remembered "always allow" rules from earlier sessions.
Several are broad prefixes: `["git","add"]`, `["git","commit","-m"]`,
`["git","fetch"]`, `["gator","init"]`, `["gator","gatorize"]`, `["rg"]` and
`["Get-Content"]`. Under the rules page, each runs **outside the sandbox
without prompting**. This shows how a one-time "always allow" quietly
becomes a standing permission in every session. It is also why the spike's
negative controls are judged against the isolated spike home, not the normal
home. This is for the Architect's awareness only. The spike does not edit
these rules.

## 5. Fixture

All fixture files are outside every governed repository:
`%TEMP%\gator-codex-spike-20261008\` (`repo\` and `work\`).

1. `git init -b main` with an initial commit of `app.py`
   (`def add(a, b)`), then `gator gatorize --yes .`.
2. The scaffolding commit went through the strict commit gate. It first
   blocked `missing-message`, then `invalid-change-type` (`chore` is not a
   legal value), then passed with `change-type: maintenance`. HEAD
   `72f9e32 fixture: gatorize`.
3. Planning loop `add-subtract-2026-10-07T23-40-02Z`: the draft was
   submitted and the reviewer approved it with the CLI (`plan_approved`).
4. Coding loop `add-subtract-coding-2026-10-07T23-42-17Z` (one checkpoint):
   `sub(a, b)` was added and staged, and the draftor ran
   `submit-implementation --checkpoint cp1` from an ordinary shell. Result:
   generation 0, candidate staged tree
   `2049d8ba4df39db8eeeaccef380ff6bf9d38315a`, stage `implementation_review`.
5. Role tokens are kept only in `work\tokens.env`, outside the repository.

## 6. Baseline: no profile

The probes use `codex sandbox -c sandbox_mode="workspace-write"`. It applies
the same Windows elevated sandbox that an interactive Codex session uses for
unapproved commands, without a model. The interactive Goal-mode session is
exercised in checkpoint 2, from a fresh session.

### 6.1 Confound found and controlled: sandbox user and Git `safe.directory`

The elevated sandbox runs commands as a dedicated sandbox user (SID
`…-1006`). The fixture is owned by the interactive user (SID `…-1001`).
Without a `safe.directory` entry, Git refuses the repository before any
`.git` protection is reached:

```
… is owned by:
	'S-1-5-21-…-1001'
but the current user is:
	'S-1-5-21-…-1006'
To add an exception for this directory, call:
	git config --global --add safe.directory C:/Users/curator/AppData/Local/Temp/gator-codex-spike-20261008/repo
```

The Architect's real repositories avoid this through `safe.directory`
entries in `C:/Users/curator/.gitconfig`, which the sandbox user also reads.
For example, `C:/Users/curator/code2/gator` is listed. To mirror that without
changing the global Git config, the probes set it **per process** with Git's
command-line-scope environment:
`GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=safe.directory`,
`GIT_CONFIG_VALUE_0=<fixture path>`.

A bare `gator` executable cannot be launched by the sandbox runner
(`CreateProcessAsUserW failed: 2`). Gator probes therefore use the same shape
as an interactive Codex command:
`powershell.exe -Command "gator loop …"`.

### 6.2 Probe results

| Probe | Command under sandbox | Result |
|---|---|---|
| P0a, read-only inspection | `git diff --stat 72f9e32 2049d8ba…` | **succeeds** (2 files, 114 insertions, 1 deletion) |
| P0b, write-tree control (H1) | `git write-tree` | **fails**, exit 128: `fatal: Unable to create '…/repo/.git/index.lock': Permission denied` |
| P0c, opportunistic index refresh | `git diff --name-only` | succeeds; Git skips the optional lock without error |
| P1, Reviewer status | `powershell.exe -Command "gator loop status --token glp_<redacted>"` | **succeeds**; prints the stored candidate `2049d8ba…` and the review command |
| P2, governed approval | `powershell.exe -Command "gator loop submit-review --token glp_<redacted> --file …\review-approve.md --approve"` | **fails**, exit 1 (verbatim below) |

P2 verbatim:

```
  Error: Cannot verify the live candidate before approval: git_busy (fatal: Unable to create 'C:/Users/curator/AppData/Local/Temp/gator-codex-spike-20261008/repo/.git/index.lock': Permission denied)
```

H1 is **confirmed** on this surface. The only write Gator's candidate
verification needs that the sandbox refuses is `git write-tree` taking
`.git/index.lock`. This matches the protected-paths documentation.

### 6.3 Loop state before and after (from `work\loopstate.py`)

```
BEFORE:   stage=implementation_review generations=1 events=2 last_event=implementation_submitted approval=no index_sha=e96ec14b71913a03 objects=106 index_lock=False
AFTER P0: stage=implementation_review generations=1 events=2 last_event=implementation_submitted approval=no index_sha=e96ec14b71913a03 objects=106 index_lock=False
AFTER P2: stage=implementation_review generations=1 events=2 last_event=implementation_submitted approval=no index_sha=e96ec14b71913a03 objects=106 index_lock=False
```

The denied approval left the loop exactly as it was: same stage, generation
count, event count, index bytes and object count, and no stale `index.lock`.

### 6.4 Observation for sketch Q4: the denial is labelled `git_busy`

Gator reports the host denial as `git_busy` ("an index-lock failure persists
after one retry", per the loop charter's `snapshot()` error codes), because
`_is_busy` matches the `index.lock` text. To a participant this looks like
transient Git contention, not an execution-permission denial. The
`Permission denied` text survives only inside the parenthesised detail.

This spike does not change Gator, because the sketch makes Gator's snapshot
code a non-goal. Recommended Phase-1b candidate: classify an `index.lock`
failure whose detail contains `Permission denied` as a distinct error code
(for example `git_permission_denied`) with participant text naming a host
execution-permission condition. It would need its own planning loop.

## 7. Checkpoint 2: profile happy path

### 7.1 Mechanism and isolation

There is one mechanism. It is a user-layer rule file in an isolated spike
`CODEX_HOME`:
`…\scratchpad\spike-codex-home\` (outside every repository; not the normal
home).

`rules\default.rules` (SHA-256 `eaacd4d1…`, 15 lines, unchanged after every
run):

```
prefix_rule(
    pattern = ["gator", "loop", ["status", "wait", "submit-draft", "submit-review", "submit-implementation"]],
    decision = "allow",
    justification = "Gator loop participant routine commands (#37 spike); Gator enforces token, role, turn and candidate freshness.",
    match = [ ["gator","loop","status","--token","glp_x"], ["gator","loop","submit-review","--token","glp_x","--file","r.md","--approve"] ],
    not_match = [ ["gator","loop","end","--token","glp_x"], ["gator","gatorize","."], ["git","write-tree"] ],
)
```

`config.toml` in the spike home contains only `model`,
`model_reasoning_effort`, `[windows] sandbox = "elevated"` and
`trust_level = "trusted"` for the fixture path. Both files are written
without a UTF-8 BOM.

**Deviation from the plan, approved by the Architect on 2026-10-07:**
- The Architect could not run the interactive session, so the Codex runs use
  `codex exec --ephemeral -s workspace-write --json` (non-interactive) instead
  of an interactive Goal-mode TUI session.
- Authentication: the Architect approved copying `~\.codex\auth.json` into the
  spike home instead of a fresh `codex login`. The copy is deleted at
  teardown (checkpoint 3).

Each run sets only process-scoped variables:
- `CODEX_HOME=<spike home>`;
- `GIT_CONFIG_PARAMETERS='safe.directory=<fixture>'`. This replaces
  `GIT_CONFIG_COUNT`/`KEY_0`, whose names contain `KEY` and may be filtered
  by Codex's shell environment policy. Whether that filter applies was not
  tested.

Side effects of a fresh `CODEX_HOME`:
- Codex re-ran its elevated-sandbox setup. It reused the existing machine
  sandbox users `CodexSandboxOffline` and `CodexSandboxOnline`, wrote their
  credentials to `<spike>\.sandbox-secrets\sandbox_users.json`, and recorded
  a non-fatal `helper_unknown_error: read ACL run had errors`.
- Codex refused to create PATH helper aliases under a temporary directory
  (warning only).

All of these files are deleted with the spike home at teardown.

### 7.2 Command-match results (`codex execpolicy check --rules <spike>\rules\default.rules`)

| Command | Decision |
|---|---|
| `gator loop status --token glp_PLACEHOLDER` | **allow** |
| `gator loop wait --token glp_PLACEHOLDER --max-seconds 45` | **allow** |
| `gator loop submit-draft --token glp_PLACEHOLDER --file p.md` | **allow** |
| `gator loop submit-review --token glp_PLACEHOLDER --file r.md --approve` | **allow** |
| `gator loop submit-implementation --token glp_PLACEHOLDER --checkpoint cp1 --file i.md` | **allow** |
| `gator loop end --token glp_PLACEHOLDER` | no-match |
| `gator loop extend --token glp_PLACEHOLDER --rounds 2` | no-match |
| `gator gatorize .` | no-match |
| `git write-tree` | no-match |
| `git commit --allow-empty -m probe` | no-match |
| `git update-ref refs/heads/x HEAD` | no-match |
| `powershell.exe -Command "gator loop submit-review …"` (static check) | no-match |
| `powershell.exe -Command "gator loop status …; git update-ref …"` (static check) | no-match |

**PowerShell wrapper, sketch Q5.** The static checker matches tokens only.
In the live sessions, Codex ran every command as
`powershell.exe -Command '<cmd>'`, and the governed approval succeeded
(§7.3). That approval fails under the sandbox (§6.2, P2), so the live session
must have unwrapped the simple single command and matched it against the
prefix rule. The trailing dynamic `--token glp_…` argument does not affect a
prefix match. A literal command-prefix rule is sufficient, and no special
invocation pattern is needed. Compound or variable-bearing scripts are not
expected to be unwrapped (per the rules page's `bash -lc` description), so
they would run sandboxed. This was not probed live.

### 7.3 Live runs

**Session A (Reviewer, coding loop `add-subtract-coding-…`).** All
commands are shown as Codex ran them, each wrapped in `powershell.exe -Command`:

| # | Command | Codex exit | Result |
|---|---|---|---|
| 1 | `gator loop status --token glp_<r>` | 0 | Reviewer's turn, candidate `2049d8ba…` |
| 2 | `gator loop wait …` (model mis-copied the token) | 1 | `Error: Loop directory not found: …\add-subtratt-coding-…`. Gator rejected the corrupted token cleanly; no state change. |
| 2′ | `gator loop wait --token glp_<r> --max-seconds 45` | 0 | turn ready |
| 3 | `git write-tree` (P-write) | 1 | `fatal: Unable to create '…/.git/index.lock': Permission denied` |
| 4 | `gator loop submit-review --token glp_<r> --file …\review-approve.md --approve` | 0 | approved; `PENDING COMMIT` of staged tree `2049d8ba…` |
| 5 | `gator loop status --token glp_<r>` | 1 | loop ended (Gator exit 2, see §7.5) |
| 6 | `gator loop wait …` | 1 | loop ended (Gator exit 2, see §7.5) |

Fixture state:

```
PRE-A:  stage=implementation_review   generations=1 events=3 last_event=architect_attention_due approval=no  index_sha=e96ec14b71913a03 objects=106 index_lock=False
POST-A: stage=implementation_approved generations=1 events=4 last_event=implementation_approved approval=yes index_sha=e96ec14b71913a03 objects=106 index_lock=False
```

The fixture's CLI-appended Reviewed Candidate:

| Fact | Value |
|---|---|
| Verdict | APPROVE |
| Reviewed staged tree | `2049d8ba4df39db8eeeaccef380ff6bf9d38315a` |
| Reviewed HEAD | `72f9e32adeeb0013dcea9957afbaf0441ca69e84` |
| Live candidate unchanged at review | **yes** |

**Session B (Draftor, planning loop `add-multiply-…` then coding loop
`add-multiply-coding-…`).**

| # | Command | Codex exit | Result |
|---|---|---|---|
| B1.1 | `gator loop submit-draft --token glp_<r> --file …\plan2.md` | 0 | `Draft submitted. Advancing to plan_review.` |
| B1.2 | `gator loop wait --token glp_<r> --max-seconds 10` | 1 | not the draftor's turn (Gator exit 3, see §7.5) |
| (Architect shell) | reviewer approval; coding loop started | — | — |
| B2.0 | file edit of `app.py` (adds `mul`) | — | workspace write allowed |
| B2.1 | `git add app.py` (not covered by the rule) | 1 | `fatal: Unable to create '…/.git/index.lock': Permission denied` |
| B2.2 | `gator loop submit-implementation --token glp_<r> --checkpoint cp1 --file …\impl2.md` | 0 | submitted generation 0; stage `implementation_review` |

B2.2 submitted the already-staged tree. The `mul` edit stayed unstaged
because B2.1 was denied, and Gator correctly treats only the staged tree as
the candidate. This coding loop is left in `implementation_review` for the
checkpoint-3 stale-candidate probe.

`submit-draft` writes only under `.gator/loops/`, which is inside the
writable root. It would succeed sandboxed as well, so it shows the rule
matches but does not prove the rule was needed.

### 7.4 Required per-mechanism evidence row

| Mechanism | Command match result | Approval behavior | Effective sandbox / write boundary | Child Git inherits? |
|---|---|---|---|---|
| User-layer `prefix_rule(["gator","loop",[5 subcommands]], decision="allow")` in an isolated `CODEX_HOME` | 5/5 positives `allow`; 8/8 negatives `no-match` (§7.2). The live session unwraps simple `powershell.exe -Command` invocations and matches them (§7.2). | `codex exec` has no approval UI. Across 10 invocations of covered commands (status ×3: A1, A5 and one unprompted status in B2; wait ×4: A2 with the corrupted token, A2′, A6, B1.2; submit-review, submit-draft, submit-implementation), none produced an approval request or failed for a host-permission reason. There were no remembered approvals: fresh `CODEX_HOME`, `--ephemeral`, and the rule file was byte-identical before and after. **The interactive TUI prompt display was not observed.** The no-prompt claim for interactive sessions rests on the documented `allow` semantics ("without prompting"). | **The matched command runs outside the sandbox. The session sandbox is not widened.** P-write: direct `git write-tree` (A3) and `git add` (B2.1) in the same sessions were still denied at `.git/index.lock`. | **Yes.** P-child: `submit-review --approve` (A4) and `submit-implementation` (B2.2) both run `git write-tree`, which the sandbox denies (§6.2 P0b/P2), and both succeeded. A4's Reviewed Candidate records `Live candidate unchanged at review: yes`. Gator's children run with the user's full rights. |

### 7.5 Additional findings

1. **The PowerShell wrapper collapses Gator exit codes.** Codex runs commands
   as `powershell.exe -Command '<cmd>'`. Windows PowerShell 5.1 then exits
   `1` for any non-zero native exit code:

   ```
   direct  gator loop wait …           → exit 2
   powershell.exe -Command "gator loop wait …"                    → exit 1
   powershell.exe -Command "gator loop wait …; exit $LASTEXITCODE" → exit 2
   ```

   A Codex participant therefore cannot tell `2` (loop ended) from `3`
   (still waiting) by exit code, and the Loop protocol's bounded-wait
   contract is keyed on exit codes. In Session A, the model had to infer
   "loop ended" from the text. The `; exit $LASTEXITCODE` form preserves the
   code, but it contains a variable, so it is probably **not** unwrapped and
   would no longer match the allow rule (not probed live). Packaging must tell
   Codex participants to read Gator's text (`Loop ended.`, `Your turn: YES`),
   not the exit code. A Gator-side remedy, such as a fixed machine-readable
   final line on `wait`, is a separate candidate and is not implemented.
2. **The model corrupted a token once.** The participant mis-copied the role
   token. It decodes to a different loop id (`add-subtratt-…`). Gator failed
   closed with `Loop directory not found` and no state change. This is
   harmless but shows that dynamic token handling is a model-reliability
   issue, not a permission issue.
3. **No token persisted.** `rg -uu -a` over the whole spike home (text and
   binary) found no fixture token, because `--ephemeral` saves no
   transcript. The same scan found none in this repository outside
   `.gator/loops/`. Tokens exist only in the fixture's `work\` notes and the
   `codex exec` JSON logs there, outside every repository, and are deleted at
   teardown. An interactive (non-ephemeral) Codex session would save the typed
   token in `CODEX_HOME` history and transcripts, which is today's normal
   behavior.
4. **Normal home untouched.** After both sessions, the normal-home manifest
   still equals the preflight values (`eeabec50…`, `3a1f0627…`).

### 7.6 Checkpoint-2 verdict

The happy path **works**: all five commands run, approvals advance with
Gator's live staged-tree check intact, and the rest of the session stays
sandboxed. Because of how the mechanism works, this is a **conditional
pass**: every matched `gator loop` invocation, and every process it starts,
runs **outside the Codex sandbox** with the user's full rights. Under the
approved plan, whether that is acceptable is an Architect-owned decision. It
must be escalated before checkpoint 4 publishes any profile note.

## 8. Checkpoint 3: safety, rejection and teardown

All Codex runs use `codex exec --ephemeral -s workspace-write --json`, the
Architect-approved substitute from §7.1. Fixture coding loop
`add-multiply-coding-2026-10-07T23-56-56Z` is used unless stated otherwise.

### 8.1 Stale candidate (profile active)

The `mul` edit was staged from an ordinary shell after submission, so the
staged tree became `350611e2…`; the submitted tree was `2049d8ba…`. The
profiled Codex Reviewer then ran
`gator loop submit-review --token glp_<r> --file …\review-approve.md --approve`:

```
exit=1
Error: The candidate changed since submission (staged tree or HEAD differs); approval is blocked. Submit findings so the Draftor resubmits the current tree.
```

```
PRE-STALE:  stage=implementation_review generations=1 events=2 approval=no index_sha=7c911c2490936f90 objects=108
POST-STALE: stage=implementation_review generations=1 events=2 approval=no index_sha=7c911c2490936f90 objects=108
```

Gator's own freshness check refused the approval, not the host. The rule let
the live snapshot run, and the snapshot found the changed tree. **The profile
does not weaken the staged-tree binding.** The fixture was then reset from an
ordinary shell: Reviewer findings, then the Draftor resubmitted generation 1
(`350611e2…`).

### 8.2 Unrelated commands (profile active)

| Command (as Codex ran it) | Exit | Result |
|---|---|---|
| `git commit --allow-empty -m probe` | 1 | `fatal: Unable to create '…/.git/index.lock': Permission denied` (sandboxed) |
| `Set-Content -Path 'C:\Users\curator\gator-spike-probe.txt' -Value probe` (outside the workspace) | 1 | `UnauthorizedAccessException` (sandboxed); file not created |
| `gator loop end --token <Reviewer> --reason probe` (not covered by the rule) | 1 | `Rejected: End requires the architect token` (ran sandboxed; Gator's role check refused it) |

HEAD stayed `72f9e32`, and the loop state and index bytes were unchanged.
Commands outside the five-subcommand prefix get normal Codex treatment.

### 8.3 Profile removed mid-loop

`rules\default.rules` was moved out of the spike home's `rules\` directory
(0 rule files), and the same Reviewer approval was retried:

```
exit=1
Error: Cannot verify the live candidate before approval: git_busy (fatal: Unable to create 'C:/Users/curator/AppData/Local/Temp/gator-codex-spike-20261008/repo/.git/index.lock': Permission denied)
```

- **Loop state:** PRE and POST were identical (`implementation_review`,
  generations 2, events 4, index `7c911c24…`, objects 108). There was no
  transition and no new generation or event.
- **Token:** still valid. An ordinary shell with no `CODEX_HOME` printed
  `Your turn: YES`, `Stage: implementation_review`, exit 0.
- **Participant diagnosis:** asked what kind of problem this was, the model
  answered *"a Git repository lock/permission contention preventing Gator
  from verifying the candidate"*. It did not identify an execution-permission
  condition. Gator's `git_busy` label (§6.4) leads participants to the
  contention reading. The sketch's requirement that participant text identify
  an execution-permission problem is **not met** by current Gator output.
  This supports the Phase-1b classification change.

### 8.4 Mechanism unavailable (malformed rule file)

A syntactically broken `rules\default.rules` was written:
- `codex execpolicy check`: `Error: failed to parse policy at …\default.rules … starlark error: error: Parse error: unexpected symbol '=', expected symbol ']'` (exit −1).
- `codex exec` refused to start: `Error loading rules: …\default.rules:1: starlark error: … (problem is on or around line 1)` (exit 1). No model turn ran.

A broken profile **fails closed**: no session starts, so nothing runs with
either the elevated permission or a silent fallback.

### 8.5 Terminal

The valid rule was restored (SHA `eaacd4d1…`). The fixture loop was ended
with the Architect token (`ended_by_architect`). The profiled participant was
asked to follow bounded waiting:

```
gator loop wait --token glp_<r> --max-seconds 10   → exit 1;  "Loop ended."
AGENT: I will stop: the loop reports `Stage: ended_by_architect` and "Loop ended."
```

The participant stopped correctly, using Gator's text because the wrapper
reports exit 1 (§7.5.1). A scan of the rule file for `glp_` tokens, loop ids
(`add-`), fixture paths and `loops` found **nothing**. The profile holds only
the static command prefix and nothing that outlives a loop.

### 8.6 Teardown of the spike config home

- `rm -rf <scratchpad>\spike-codex-home`. Afterwards the path does not exist.
  This removed the copied `auth.json`, the sandbox-user credentials file, the
  rule, and all Codex state written there.
- Persistent environment variables, at User and Machine scope:
  `CODEX_HOME`, `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`,
  `GIT_CONFIG_KEY_0`, `GIT_CONFIG_VALUE_0` and `CODEX_SQLITE_HOME` are all
  empty.
- The global Git `safe.directory` list does not contain the fixture
  (0 matches).

### 8.7 Post-teardown verification

- **Manifest:** `config.toml` `eeabec50…` and `rules\default.rules`
  `3a1f0627…` match preflight. There is still one rules file and no profile
  files. See §8.8 for one restored change.
- **`execpolicy check` from the normal home:** the same 10 commands as §4 are
  all `no-match`, identical to preflight.
- **Fresh default-home session reproduces the baseline:** a new fixture
  coding loop `add-multiply-coding3-2026-10-08T00-06-13Z` (candidate
  `350611e2…`) was used. Codex ran with **no** `CODEX_HOME` (normal home),
  `--ephemeral`, and Reviewer `submit-review --approve`:

  ```
  exit=1
  Error: Cannot verify the live candidate before approval: git_busy (fatal: Unable to create '…/.git/index.lock': Permission denied)
  PRE/POST: stage=implementation_review generations=1 events=2 approval=no index_sha=7c911c2490936f90 objects=108 (identical)
  ```

  This is identical to §6.2 P2. The normal home has no residual permission.
  The fixture loop was then ended with the Architect token.

### 8.8 Finding: Codex writes project trust into the normal config

The default-home run in §8.7 was the first Codex run in the fixture **without**
the spike home, which had pre-trusted it. Codex appended this to the normal
`~\.codex\config.toml`:

```
[projects.'c:\users\curator\appdata\local\temp\gator-codex-spike-20261008\repo']
trust_level = "trusted"
```

The SHA changed `eeabec50…` → `1c40b51b…`. The rules file was untouched. I
removed exactly that 3-line block with a guarded script, which writes only
if the result hashes to the preflight value. The file is again `eeabec50…`,
byte-identical to preflight.

Two lessons follow:
- A packaged opt-in that points Codex at a dedicated `CODEX_HOME` must
  pre-trust the working repository there, or the participant's first run
  writes trust to whichever home it uses.
- Running `codex exec -s workspace-write` in a new directory is **not**
  read-only toward the config home. The spike's own isolation held, because
  every profiled run used the spike home.

### 8.9 Checkpoint-3 matrix status

| Sketch matrix row | Probe | Outcome |
|---|---|---|
| Stale candidate | §8.1 | **pass**: Gator refused; state unchanged |
| Unrelated command | §7.3 (P-write, `git add`) + §8.2 | **pass**: sandboxed or role-rejected |
| Host denial / profile removal | §8.3 + §8.4 | **pass** on state, token and fail-closed. **Gap:** participant text reads as lock contention, not execution permission (Gator `git_busy`) |
| Loop terminal | §8.5 + §8.6–8.8 | **pass**: participant stops; no loop data in profile; spike home removed; normal home byte-identical |

The fixture (`%TEMP%\gator-codex-spike-20261008\`, including its `work\`
token notes and Codex JSON logs) stays until checkpoint 4 is approved. It is
then deleted.

## 9. Checkpoint 4: decision and packaging

### 9.1 Architect decision

The draftor escalated the conditional pass with a decision request:
`gator loop escalate --file`, ledger entry `decision-1`. The Architect
answered **"Publish as opt-in."** That selects the pass branch, with the
trust cost stated first.

### 9.2 What was published

- **New** `reference-notes/codex-routine-participant-profile.md`, identical in
  `.gator/.includes/` and the starter template. It covers:
  - purpose;
  - the trust cost, placed first;
  - the verified surface;
  - setup with a dedicated `CODEX_HOME` outside `%TEMP%`, a pre-trusted
    repository, BOM-free files, the exact §7.1 rule, an `execpolicy check`,
    login, and launching from one terminal;
  - covered and not-covered commands;
  - participant guidance: read Gator's text rather than exit codes, and treat
    `git_busy … Permission denied` as a host denial;
  - removal, fallback, and a five-step validation checklist.
- **Links:**
  - `codex-loop-participant.md` §Boundaries points to the new note and names
    its trust cost;
  - the Loop protocol's runtime paragraph adds one sentence with the same
    pointer.

  Both are changed in both copies.
- **Layout fallback:** both `gator_layout.py` copies add
  `codex-loop-participant.md` and `codex-routine-participant-profile.md` to
  `MIXED_DIRECTORY_SHIPPED_DEFAULTS["reference-notes"]`. This follows the
  `scripts-layout.md` tripwire for adding a shipped note. The charter
  tripwire now names both.
- **Copy guards** in `tests/test_loop.py` `TestArtifactFormatAlignment`:
  - `codex-loop-participant.md` is added to `test_starter_copies_match`;
  - new `test_codex_routine_profile_copies_both_absent_or_identical`.

### 9.3 How each setup step maps to verified evidence

| Note step | Evidence |
|---|---|
| Dedicated `CODEX_HOME`; a profile cannot carry a rule | §2 (rules page, config reference), §3 |
| Outside `%TEMP%` | §7.1, Codex refused helper aliases under a temporary directory |
| Pre-trust the repository | §8.8, an untrusted run wrote trust into its home |
| Exact rule text | §7.1, the rule used in every passing run (SHA `eaacd4d1…`) |
| No BOM | §7.1, the files were written without a BOM. A BOM was not tested as a failure; this is a precaution. |
| `execpolicy check` expectations | §7.2 |
| Broken rule fails closed | §8.4 |
| `codex login` | not exercised. The spike copied `auth.json` (§7.1); the note says so. |
| Read text, not exit codes | §7.5.1 |
| `git_busy` = host denial | §6.2, §8.3 |
| Removal leaves the normal home unchanged | §8.6–8.7 |

## Connections

- Sketch and approved plan: the planning loop above.
- Issue: <https://github.com/cumberland-laboratories/gator/issues/37>
- Goal-mode workflow: `.gator/.includes/reference-notes/codex-loop-participant.md`
- Loop charter, `snapshot()` / `handle_submit_review`: `.gator/charters/scripts-loop.md`
