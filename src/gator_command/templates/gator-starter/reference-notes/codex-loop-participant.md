# Codex Loop Participant — Goal-Mode Workflow

**Audience:** a Draftor or Reviewer using an interactive Codex session after
successfully joining a Gator loop.

## Purpose

Codex Goal mode is an optional way to keep one interactive Codex session
working through the normal bounded-wait protocol until the loop reaches a
terminal state. It does not replace Gator's CLI, watcher contract, role token,
or submission rules.

Use it only **after** `gator loop join` has completed in the same session. The
join has already established the role and made the token available in session
context, so do not paste the token into the Goal text.

## Copy/Paste Prompt

Enter `/goal` in the same interactive Codex session, then provide:

```text
Remain an active participant in the Gator loop I just joined until it reaches a terminal state. Follow the Gator loop protocol exactly. If it is not my turn, use the existing role token and reissue `gator loop wait --token <token> --max-seconds 45` whenever it returns exit code 3; if the Architect gave me a different `--max-seconds` interval, use that value instead, because the Architect's instructions take precedence over protocol defaults. Stay connected through paused and blocked states. When my turn arrives, perform the required governed review or submission through the CLI. Stop only on terminal exit code 2; do not edit loop files directly or submit without completing the required work.
```

`<token>` means the role token established by the earlier join; it is an
instruction to reuse it, not text that must be pasted literally.

## Boundaries

- Goal mode keeps the participant objective active; each wait remains bounded
  and resumable under the ordinary Loop protocol.
- A Codex host permission prompt can still pause a command before Gator sees
  it. After the Architect approves or denies that host prompt, continue from
  the same Goal/session. This is not a normal Gator escalation. To remove
  the routine prompts for `gator loop status`, `wait` and submissions, the
  Architect can opt into `codex-routine-participant-profile.md`. Read its
  trust cost first: the allowed commands run outside the Codex sandbox.
- Goal mode does not make `gator loop participant watch` a supported Codex
  supervisor, and it does not wake an already-ended session. Use the normal
  bounded-wait/manual-rejoin path if Goal mode is unavailable or ends.
- Do not place the token in a recurring scheduled-task prompt or write it to a
  repository file. Scheduled-task integration remains a separate, unproven
  runtime adapter.

## Evidence Status

This workflow has been successfully exercised in interactive Codex sessions.
It remains an opt-in participant pack: Gator's model-neutral protocol and CLI
are authoritative, and runtime availability can vary by Codex surface and
workspace policy.
