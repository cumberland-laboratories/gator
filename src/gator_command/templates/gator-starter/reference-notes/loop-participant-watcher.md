# Loop Participant Watcher — Receiver Contract

**Audience:** agents joining a `gator loop`, and anyone writing a runtime adapter. The behavioral rules live in `procedures/gator-loop-protocol.md`; this note specifies the watcher contract those rules rely on.

## What It Is

`gator loop participant watch` is an optional, **bounded** background receiver for a Draftor or Reviewer. It tells the Architect's Dashboard that a participant is reachable. It exits the moment the participant has something to do, so a supervising runtime can start a new agent turn.

It is **not** automatic dispatch. It never submits drafts or reviews, never changes loop state, and cannot resume a vendor session that has already ended. `gator loop wait --max-seconds 45` remains the supported fallback for every runtime.

## The Three Parties

| Party | Responsibility |
|---|---|
| **Supervisor**: the agent runtime's background-process facility | Starts the watcher as a background process that outlives the turn that launched it. When the process exits, it starts a new agent turn that carries (or points to) the output. It owns the process: when the session ends, the watcher ends with it. |
| **Watcher**: `gator loop participant watch` | Registers, heartbeats, polls, acknowledges the first deliverable notification, prints one JSON line, records its registration state, and exits. It never loops forever and never relaunches itself. |
| **Agent**, when re-invoked | Reads the **last line that parses as JSON** from the watcher output (stdout and stderr may share one file), then follows the exit table below. |

**Supported supervisor:** Claude Code's Bash tool with `run_in_background: true`, while the session is open and the agent is idle between turns. This was verified on Claude Code 2.1.283 on Windows 10 (see the M0 vendor spike record). The wake turn gives the task's output-file path; the agent reads it. Runtimes without such a facility (Codex CLI today) use bounded `wait`.

## Command

```
gator loop participant watch --token <token> --max-seconds <N> [--poll-seconds 5] [--adapter-label <label>] [--json]
gator loop participant status --token <token> [--json]
```

- `--max-seconds` is **required**. A suggested value is 600; relaunch the watcher when it exits `3` (still waiting).
- `--json` prints exactly one compact JSON line on stdout. Normal outcomes print nothing to stderr.
- `--adapter-label` is optional: at most 40 printable characters, stored privately. The Dashboard does not display it.
- Output never contains the token or the private registration id.

## Exit Contract

| Exit | `wake_reason` | Meaning | Agent action | Registration afterwards |
|---|---|---|---|---|
| 0 | `turn_ready` | It is your turn | `gator loop status`, then act | released |
| 2 | `terminal` | The loop ended | Stop; do not relaunch | closed (one-way) |
| 3 | `still_waiting` | `--max-seconds` elapsed, including during a pause or block | Relaunch the same command | released |
| 4 | `superseded` | A newer watcher owns this role | Stop | untouched |
| 1 | `error` | Bad token, Architect token, or storage unavailable | Fall back to bounded `wait` | — |
| 130 | `interrupted` | Ctrl+C / SIGTERM | — | released (best effort) |

JSON keys: `schema` (`gator-loop-participant-v1`), `wake_reason`, `loop_id`, `role`, and on delivery `kind`, `seq`, `stage`, `round`, `acked`. They also include `max_seconds` on `still_waiting` (plus `suspended: true` and the paused `stage` when the loop is suspended) and `error` on errors.

**Suspension is not departure.** When the Architect pauses the loop or a participant escalates, the watcher acknowledges the `architect-block` notification and keeps watching. Its registration stays active, so the Dashboard keeps showing it as connected. It exits on `turn_ready` after the unblock, on `terminal`, or at `--max-seconds`. Older watchers exited `2` / `architect_block` instead; if you see that wake reason, relaunch the watcher.

## Semantics

- **Acknowledged means received.** It never means read, complied with, worked on, or submitted.
- **One actionable notification per loop-state generation.** Rereading unchanged state never duplicates a notification. Older pending notifications expire when the loop moves on.
- **Re-registration supersedes.** A newly launched watcher replaces the previous one for its role and receives anything the old one never acknowledged. The old watcher can no longer poll or acknowledge.
- **Stale** applies only to a watcher that stopped heartbeating without exiting, for example one that was killed or lost with its session. A watcher that exited normally shows as **released**, not stale.
- **Architect Re-notify** adds a new notification and an audit entry. It never changes loop state or whose turn it is.

## Privacy and Storage

- Liveness data is stored per worktree at `$(git rev-parse --git-path gator-loop-liveness)/<loop_id>.json`. It is never staged, never served by the Dashboard's content routes, and never written to `events.jsonl`.
- It holds operational data only: no tokens, prompts, artifacts, or model identity.
- It isolates liveness data from repository participants. It is not a security boundary against other processes running as the same OS user.

## Extension Point for Future Adapters

A vendor-specific adapter (for example one that launches a headless session) should either:

- run `participant watch` under its own supervisor and consume the exit contract above, or
- import the loop package's `liveness` module in-process: `register`, then `poll`/`ack` in a loop, then `release`, presenting the token and the in-memory registration id on every call.

Adapters must keep the same boundaries: no automatic submission, no loop-state writes, and no token persistence. Waking supervisor-less runtimes (Codex) is tracked as follow-on work.
