# Review: Welcome HTML Documents

## Executive Summary

- **Verdict:** REVISE. The plan is strong on the closed serving route, iframe sandboxing, snapshot safety, bounded copy message, delivery paths, and staged verification.
- **Required correction:** The four reader-facing HTML documents must start from the required Cumberland master template; saying that their styles are merely “drawn from” it does not meet the repository HTML-document rule.
- **Scope:** This does not expand the feature or require showpiece content. It makes the planned placeholder documents use the already-governed document structure and visual grammar.
- **After revision:** State how the master is copied and pared down for each standalone document, while retaining self-containment and the sketch’s no-external-resource constraints. The rest of the plan can remain intact.

## Verdict

REVISE — make the mandated Cumberland-template usage explicit before implementation begins.

## Findings

### Finding 1: Cumberland master-template requirement is underspecified

**Severity**: Medium

**Location**: `## Changes`, Change 1 “Four placeholder documents”.

**Issue**: The plan specifies an inline style “drawn from the Cumberland master,” but the constitution and the HTML-authoring procedure require reader-facing non-Blueprint HTML documents to start from `templates/gator-starter/reference-notes/cumberland-html-document-template.html`. A style fragment alone can silently lose the template’s document structure, accessibility affordances, and shared visual grammar.

**Suggestion**: Amend Change 1 to copy the Cumberland master for each of the four documents, fill its header/meta-grid/summary/body with concise placeholder content, and deliberately delete components that do not serve a small standalone document. Keep CSS and any required script inline, remove all `==TODO==` markers, and retain the sketch’s no-external-resource, SVG-text-equivalent, and sandbox constraints. Add a focused document test that no `==TODO==` marker remains and that each document retains the selected Cumberland structural/style markers.

## Scope Check

The plan stays within the sketch’s content-serving, isolation, snapshot, and copy-protocol scope. It preserves the existing Welcome shell, repository independence, Loop behavior, and universal prompt boundary. Its `## Context Checked` is credible: it names the relevant Dashboard, package, installer/update, CSP, snapshot, and HTML-authoring surfaces. The two checkpoints are responsibility-based and independently reviewable.

The one finding is a repository-wide HTML authoring constraint. It should be corrected in the plan before the documents are implemented; no new product behavior is requested.

## What Looks Good

- The route uses a fixed four-name set instead of turning URL input into a path.
- The parent validates frame identity, opaque origin, and an exact structured-clone message before touching the clipboard.
- Snapshot handling accounts for script escaping and documents lacking a `<head>`.
- Delivery is verified across wheel, gatorize, and update surfaces rather than assumed from package globs.
