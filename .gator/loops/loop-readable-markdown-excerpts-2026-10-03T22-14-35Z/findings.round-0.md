# Review: Safe Readable Markdown for Loop Artifact Excerpts (#45)

## Executive Summary

- **Verdict:** APPROVE. The plan is ready to implement as written within the approved Loop-workspace presentation scope.
- **Security:** its DOM-only, constrained renderer and strict `http`/`https` link policy correctly avoid treating model-authored artifact bytes as HTML.
- **Behavior:** the Raw pane retains the exact fetched string, while the stable-node, request-revision, and unchanged-poll contracts are explicitly preserved.
- **Verification:** the proposed Playwright coverage tests normal Markdown, hostile input, parity, fallback, snapshot inlining, and refresh ordering.

## Verdict

APPROVE — the plan is ready to implement as written.

The proposed limited in-repo renderer is a modular and simplicity-first response to the Architect brief. It preserves the artifact endpoint and residue as the source of truth while giving the Dashboard a safe readable view.

## Findings

No revision findings.

## Scope Check

The plan stays within the sketch boundary: it changes only the Loop workspace's client-side presentation, its Dashboard asset loading/snapshot path, styles, tests, and the affected charters. It explicitly leaves loop artifact storage, authorization, route behavior, schemas, and the general Repository browser unchanged.

`## Context Checked` is credible. It includes the required Architect brief, the sketch, the Dashboard UI and server charters, the charter index, the relevant Loop/Repository/snapshot sources, and the existing workspace, refresh, seed, and snapshot tests. Spot checks confirm the plan accurately describes the current escaped `<pre>` body rendering, per-node revision guards, mutable-artifact refresh behavior, script inlining contract, and unsafe Repository Markdown seam it deliberately does not reuse.

## What Looks Good

- The renderer's construction-only element/attribute allowlist makes the security boundary auditable without a sanitizer dependency.
- Raw-versus-rendered parity is concrete: one fetched string feeds `pre.textContent`, never a reconstruction from rendered DOM.
- The text-equality short circuit complements the existing request revision and connected-node guards, protecting the zero-mutation polling invariant.
- The integration and snapshot order are explicit, including the regex and inline block that must change together.
- The charter-impact section replaces the obsolete escaped-`<pre>` tripwire rather than leaving documentation stale.
