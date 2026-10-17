# Review: Dashboard Threaded Request Server

## Executive Summary

- REVISE: the plan has a thorough shared-state audit, a bounded server design, and concrete verification pins.
- The lifecycle exclusion is incomplete: remove is not covered by the same per-repository exclusion as update, gatorize, config, and topology.
- This permits a remove to race a long-running or durable same-repository action, contrary to the sketch's lifecycle-mutation requirement.
- Add the remove/register interaction to the mutation contract and test it before threading is enabled.

## Verdict

REVISE

The plan is close, but it is not ready to implement until its lifecycle contract prevents a repository from being removed concurrently with another mutation of that repository.

## Findings

### Finding 1: Remove is outside the per-repository lifecycle exclusion

**Severity**: High

**Location**: Shared-State Audit "Lifecycle", Changes 2 and 4, and Coding Checkpoints 1–2.

**Issue**: `_repo_action(repo_path)` is proposed only for update, gatorize, config, and topology. `_handle_repo_remove()` instead takes the registry/Fleet writer path without the resolved-path action lock. An update or gatorize can therefore pass its registry lookup and begin its subprocess while a concurrent remove deletes the durable registry entry and publishes a Fleet without that repository. Likewise, config/topology can write into a repository that the Dashboard has already reported removed. The short writer lock does not serialize those operations because it is deliberately released while lifecycle work runs. This misses the sketch's requirement to classify register/remove and serialize same-repository mutation at the smallest meaningful scope.

**Suggestion**: Define the lifecycle contract so remove acquires the same `_repo_action(resolved_path)` before its durable registry write and keeps it through registry/Fleet publication and response; return the same documented busy result if another same-path lifecycle action owns it. Make the route resolve the action key before invoking an update/gatorize subprocess (including its Fleet fallback), so those actions can acquire that same lock before work starts. State how register is serialized with register/remove at the registry writer boundary, and add a race test for remove versus each relevant same-path action that proves one action is rejected or completes before removal, with no post-removal mutation/success response.

## Scope Check

The plan remains within the sketch and its Context Checked section credibly covers the Dashboard, cross-cutting, and Loop contracts as well as the affected implementation and tests. Its four Coding Checkpoints are responsibility-based and independently reviewable. The missing remove/lifecycle exclusion is a required correctness detail, not a scope expansion.

## What Looks Good

- The immutable publication and refresh reconciliation approach directly addresses the pre-threading shared-state hazards.
- The bounded worker/heavy-work design makes an explicit, testable admission decision rather than relying on unbounded standard-library threading.
- The in-process and browser-level verification strategy covers both server admission and security-regression behavior.
