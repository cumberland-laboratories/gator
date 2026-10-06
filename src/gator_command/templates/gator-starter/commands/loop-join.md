You are joining a gator loop as a participant. Your token is: $ARGUMENTS

Before doing anything else, orient yourself by reading these files in order:

1. Read the loop protocol: find and read `procedures/gator-loop-protocol.md` in `.gator/`, `.gator/.includes/`, or `gator-command/` (whichever exists). This is your behavioral contract — the rules you must follow.

2. Read the artifact format reference: find and read `reference-notes/loop-artifact-formats.md` (same locations as the protocol). This shows the expected structure for plans and findings.

3. Run your status check:
```
gator loop status --token $ARGUMENTS
```

4. Read the output carefully. It tells you:
   - Your role (draftor or reviewer)
   - Whether it's your turn
   - The loop directory (`Dir:` line)
   - What action to take next

5. If it IS your turn (exit code 0):
   - Read the relevant files from the loop directory shown in status:
     - **Architect brief (any role)**: if status lists `Architect brief: ... [OK] (required reading)`, read `architect-brief.md` first. Coding loops may also list the planning brief, `source-architect-brief.md`; read both. If a brief is marked `[!!]`, do not rely on it; escalate to the Architect.
     - **Draftor first turn**: read `sketch.md`, then the charters and code it touches
     - **Draftor revising**: read `findings.current.md`
     - **Reviewer**: read `plan.current.md` and `sketch.md`
     - **Coding loop** (status shows `Mode: coding`): the Draftor reads `approved-plan.md`, implements the change, stages it (no commit), and submits with `gator loop submit-implementation`. If status shows a `Checkpoint:` line, implement and stage only that active checkpoint and submit with `--checkpoint <id>`. The Reviewer reads `implementation.current.md` and reviews exactly the `git diff` that status prints (for a checkpoint: `git diff <checkpoint base> <staged_tree>`). After approval, the Draftor makes ONE normal commit. See "Coding Loops" in the protocol.
   - Then proceed with your work as the protocol directs

6. If it is NOT your turn (exit code 1, which includes a loop paused or blocked on the Architect — you are still a participant):
   - If you have a genuine Architect-owned blocker, escalate first: `gator loop escalate --token $ARGUMENTS --reason "..."`
   - Otherwise, run `gator loop wait --token $ARGUMENTS --max-seconds 45` to wait until the loop becomes actionable
   - `wait` exit 0: it is your turn — re-read the status output and proceed with your work
   - `wait` exit 3: still not your turn — reissue the same `wait` command immediately; a returned `wait` does not end your participation
   - `wait` exit 2: the loop ended — stop and report the status (a pause or block never ends a `wait`; it keeps waiting)
   - **Claude Code option (preferred while this session stays open):** instead of repeated `wait` calls, run `gator loop participant watch --token $ARGUMENTS --max-seconds 600 --json` with the Bash tool's `run_in_background: true`, then end your turn. You will be re-invoked when it exits: read the last JSON line of its output file. `turn_ready` (exit 0) → act; `still_waiting` (also during a pause or block) or a legacy `architect_block` → relaunch the watcher; `terminal` or `superseded` → stop; `error` → fall back to bounded `wait`. The watcher never submits for you, and it cannot wake a session that has already been closed.

Do NOT summarize the protocol — internalize it. Follow the 10 rules exactly. The CLI mediates all loop actions. You submit artifacts via `gator loop submit-draft` or `gator loop submit-review`, never by editing loop directory files directly.

**Required in every submission**: include a `## Executive Summary` section (four bullets or ~120 words). The Dashboard extracts this for at-a-glance inspection. See the artifact format reference for the full template.

**Required in every plan draft and revision** (planning loops): exactly one `## Context Checked` section listing the Architect brief, charters, and code you actually consulted, or `None — <reason>`. The CLI rejects a missing, empty, or bare-placeholder section. Reviewers: check that it is credible.
