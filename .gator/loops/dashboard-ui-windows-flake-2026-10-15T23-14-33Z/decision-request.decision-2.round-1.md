# Decision Request: Slice 1 scope without tracing, or stop this implementation

## Decision Needed

Decision-1 said CI must not get longer and asked whether this implementation should continue. The reviewer returned REVISE (High). The approved plan and sketch require failed-test Playwright traces. A deviation needs an Architect decision delivered through the loop channel, naming what replaces trace-based request-delay evidence; text in an implementation artifact does not count. Which of the following do you authorize?

## Context

- **Staged candidate** (tree `7d1e25b5`):
  - failure-only screenshot plus `gator-diagnostics.json` (≤48 KiB);
  - failure-only upload;
  - `GatorShell.activeRepo()`;
  - charter updates.
- **No tracing.** Pass-time cost is unmeasurable: 43/36 s with the change against 39/40 s at HEAD.
- **Tracing (`retain-on-failure`) costs about +45% test time.** Windows job wall times are 13.6–15.9 min against the 20-minute cap.
- **Without a trace, the bundle classifies** server exit, wrong view or repository, JavaScript error, and DOM visibility. It cannot evidence the "request delayed" class.
- **Evidence already in hand:** on a loaded Repo view, `.repo-file-item` reports `count 131, visible 1`. That bears directly on the CI failure "resolved to 132 elements, then waited 15 s for visibility", and makes a hidden first match the leading hypothesis.
- The reviewer had no critique of the continue-or-not question. The protocol does not let them see decision-1's message.

## Options Considered

1. **Accept Slice 1 without tracing.** This amends the scope: the accepted request-delay evidence is "none in per-push CI". If the bundle points at request timing, a follow-up adds a manually triggered (`workflow_dispatch`) Windows evidence job with tracing. The reviewer then reviews the current candidate against that amended scope. Per-push CI time is unchanged.
2. **Option 1, plus add the `workflow_dispatch` traced evidence job now,** as a separate job in this checkpoint. Per-push CI is unchanged; tracing runs only when you trigger it. It adds a small amount of workflow surface.
3. **Stop this implementation** (end the coding loop and unstage). Go straight to a Slice 2 readiness loop driven by the 131/1 visibility evidence, and confirm with a local Windows stress run. Nothing from this checkpoint ships.
4. **Keep tracing as approved** and raise the job cap. Decision-1 already ruled this out; listed only for completeness.

## Recommendation

**Option 1.** The bundle is cheap, already verified, and classifies most failure classes. The visibility evidence suggests the request-delay class is not the leading candidate. Option 3 is reasonable if you prefer to spend the effort on the fix directly, but it ships no evidence capture for future Windows flakes.

## Consequence of Delay

The coding loop stays blocked. The staged tree is unchanged. Once you unblock with a message naming the option, I will apply it and resubmit (Options 1 and 2), or stop and unstage (Option 3).
