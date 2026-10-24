---
date: 2026-10-23
type: implementation-sketch
status: implemented
---

# Welcome: Gator docs and Gator loop

## Intent

Add two beginner-oriented topics to the Dashboard's Welcome workspace. They
use the existing stripped-down Gator narrative HTML-document treatment: each
is a standalone, shipped HTML document in the Welcome tab bar, displayed in
the existing sandboxed iframe.

The new **Gator docs** topic is not an introduction to the Dashboard's
sidebar Docs library. It introduces a capability: an Architect can ask an
agent, "Create me a Gator doc for …" and receive a clear, visual, standalone
HTML explanation of a system, feature, decision, or procedure. It should make
that capability concrete without presenting a large catalogue of document
types. It is a starter, not a reference manual.

The new **Gator loop** topic explains the planning-and-coding collaboration
loop to a new user. The exact same document is also the Help surface inside
the Loop workspace. This gives the Loop feature a contextual explanation and
prevents Welcome and Loop help from describing different products.

## Proposed Welcome order

1. Start a session with Gator
2. Gator overview
3. What Gator can do
4. Gator docs
5. Gator loop
6. Gatorize a repo

The session topic remains the default. Adding topics must preserve the
existing roving-tabindex, arrow-key, Home, and End behavior.

## Document briefs

### Gator docs

Opening idea: Gator can turn codebase understanding into a readable document
for the people who need to make decisions about it.

The document should:

- show the user-facing prompt pattern: `Create me a Gator doc for …`;
- explain that the output is a standalone narrative HTML document, not an
  AI-chat answer or a source-code dump;
- show a small visual example of the kinds of questions it can answer:
  how a feature works, what a procedure does, what a system boundary is, or
  why an architectural decision was made;
- call out the visual strengths: diagrams, labelled relationships, readable
  prose, and repository-linked source context;
- explain that the document lives with the repository, so it can be reviewed,
  versioned, and kept alongside the code it explains.

It should avoid a long taxonomy of Blueprints, procedures, artifacts, and
reference notes. A new user needs the outcome and the request pattern first.

### Gator loop

Opening idea: a Loop gives an Architect a structured way to move from an idea
to an approved plan, and then to reviewed implementation, with the decision
trail retained in the repository.

The document should explain, in plain language:

- what to use a Loop for and when ordinary agent work is enough;
- the Architect, Draftor, and Reviewer roles;
- the planning path: sketch, draft, review, revision, approval;
- the coding path after approval, including checkpoints when the plan has
  them;
- what the Dashboard's Create/Active and History tabs are for;
- that the Architect remains the decision-maker: pause, clarify, redirect,
  approve, or end the work.

It should be conceptual help. It must not duplicate the full participant
protocol, CLI reference, or volatile status vocabulary.

## Shared delivery design

Add two documents to the existing shipped-document surface:

- `gator-docs.html`
- `gator-loop.html`

Both documents use the Cumberland narrative template with the local Welcome
format already used by the four shipped Welcome topics. They retain the
document CSP and work in an `allow-scripts` sandbox. The shared closed
allowlist (`WELCOME_DOC_NAMES`) continues to be the route and snapshot
authority; adding a file without adding it to that list remains invalid.

Welcome adds two entries to its topic list. The Docs sidebar library should
also list the new documents, with labels that distinguish the new **Gator
docs** capability explainer from the existing Docs workspace.

## Loop Help reuse

Extend the Loop workspace tab model from:

```
Create / Active | History
```

to:

```
Create / Active | History | Help
```

Help uses an iframe that loads the same allowlisted `gator-loop.html` route as
Welcome, with the same exact `sandbox="allow-scripts"` contract. It is static:
it does not fetch loop state, send messages to the shell, or affect polling.
This is deliberate. The Help text must be readable without an active loop and
must not become a second control surface.

Selecting Help must not discard the Create form, a selected active loop, or a
History selection. Returning to Create/Active or History restores the normal
Loop workspace state. The main tab list remains keyboard-operable and exposes
the Help tab through the same ARIA pattern as its peers.

## Implementation seams

| Surface | Change |
| --- | --- |
| `templates/gator-starter/docs/` | Add the two narrative HTML documents. |
| `dashboard/helpers.py` | Add both filenames to `WELCOME_DOC_NAMES`. |
| `dashboard/views/welcome.js` | Add the two Welcome topics in the stated order. |
| `dashboard/views/docs.js` | Add both documents to the library list. |
| `dashboard/views/loop.js` | Add the Help tab and render the shared loop-help iframe without entangling it with the Loop poller. |
| Dashboard UI tests | Extend Welcome, Docs, snapshot, and Loop tab/navigation/isolation coverage. |
| Dashboard charters | Update the server/UI charter immediately alongside the corresponding code edits. |

## Acceptance checks

- Welcome has six labelled topics; session remains first and the initial
  selection.
- Both new Welcome documents load only when their tab is first selected and
  are sandboxed exactly `allow-scripts`.
- Each new file is reachable through the allowlisted document route and is
  included in generated Dashboard snapshots.
- The Docs workspace lists both documents.
- Loop has a Help tab beside Create/Active and History. It displays the exact
  same `gator-loop.html` content as Welcome.
- Help is usable with no active Loop and does not change loop state, history,
  polling, or a partially completed Create form.
- Mouse and keyboard tab navigation continue to work at narrow and wide
  widths.

## Non-goals

- Reworking the existing Docs sidebar or renaming its route.
- Turning Help into a dynamic status panel or a replacement for the loop
  protocol.
- Adding actions, forms, or cross-frame messages to either new document.
- Writing a comprehensive Gator-document authoring reference in the Welcome
  topic.
