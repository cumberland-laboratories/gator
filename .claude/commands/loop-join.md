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
     - **Draftor first turn**: read `sketch.md`
     - **Draftor revising**: read `findings.current.md`
     - **Reviewer**: read `plan.current.md` and `sketch.md`
   - Then proceed with your work as the protocol directs

6. If it is NOT your turn (exit code 1):
   - Report your status and wait for instructions
   - Remember: you can still escalate if you see a problem

Do NOT summarize the protocol — internalize it. Follow the 10 rules exactly. The CLI mediates all loop actions. You submit artifacts via `gator loop submit-draft` or `gator loop submit-review`, never by editing loop directory files directly.
