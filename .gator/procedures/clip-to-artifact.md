# Procedure: Clip to Artifact

Save a conversational exchange (human message + AI response) directly to an artifact, preserving the verbatim exchange. No triage, no thread restructuring, no compression.

## Trigger

Human says `[save]`, `[clip]`, or otherwise indicates the current exchange should be preserved as-is.

## Steps

1. Identify the exchange to save. Default: the immediately preceding human message + AI response. The human may specify a different range (e.g., "save the last three exchanges").
2. Write the exchange to `.gator/artifacts/` as a dated artifact:
   - Filename: `YYYY-MM-DD-clip-<short-descriptor>.md`
   - YAML frontmatter: `date`, `tags`, `source-thread`, `clip: true`. No `summary` field — clips are verbatim captures, not synthesized records. The `clip: true` flag signals this exception to tooling and auditors.
   - Header: one-line context note (what thread or topic was active)
   - Body: the raw exchange, verbatim, formatted as a dialogue (`**Human:** ... **Agent:** ...`)
   - No synthesis, no summary, no restructuring. The conversational form is the value.
3. Add a one-liner reference in the most relevant active thread's `## Connections` section:
   - Format: `→ Artifact: [Clip — short description](../artifacts/YYYY-MM-DD-clip-short-descriptor.md)`
   - If no active thread is clearly relevant, add the reference to the thread currently under discussion.
4. Move on. No follow-up triage. Organization happens later if needed.

## Design Rationale

Consistent with the constitution's principle: **capture and organization are different operations and must never be forced to happen at the same time.** The inbox embodies this for raw thoughts. Clip-to-artifact embodies it for conversational moments worth preserving in their original form.

Artifacts created this way are not always-loaded. They live in the archive, reachable via cross-reference, surfaced when relevant — the same lifecycle as any other artifact.
