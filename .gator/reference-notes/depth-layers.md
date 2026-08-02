# Depth Layers

The thread lifecycle describes **three tiers** that participate in rotation (promotion/demotion):

| Layer | Location | Loaded | Rotates |
|-------|----------|--------|---------|
| **Active thread** | `active-threads/` | Always | Yes |
| **Lightweight thread** | `threads/` | On demand | Yes |
| **Artifact** | `artifacts/` | On demand | Yes (synopsis absorption) |
| **Vault file** | `vault/` | Never (external) | No |

The vault is a **fourth depth layer** but not a rotation tier. Vault files don't promote or demote — they are raw external material (PDFs, papers, notebooks) that artifacts *reference* via `source:` frontmatter. The relationship is: artifact describes vault file, thread references artifact.

## PDF Discussion Workflow

When a PDF (or other external file) comes up in conversation, the flow is:

1. **Vault**: The file lands in `vault/<domain>/` (e.g., `vault/mathematics/some-paper.pdf`). This is just storage — gitignored, no metadata.
2. **Conversation**: We discuss the file. Ideas, reactions, and questions develop naturally.
3. **Thread**: A thread captures the *topic* that emerged — not "we read a PDF" but the idea it contributed to. The thread may already exist (the PDF was relevant to something active) or may be new.
4. **Artifact** (if warranted): If the discussion produces deep notes, a synopsis, or detailed analysis, that goes into an artifact with `source: vault/domain/filename.pdf` in its frontmatter. The thread cross-references the artifact.

The key principle: **the thread captures the idea, the artifact captures the depth, and the vault holds the source**. Not every PDF needs an artifact — if the discussion is light, a thread reference with a vault path is enough.

### When an artifact is warranted

- The PDF generated enough analysis to exceed what fits in a thread's Detail section
- You want a durable synopsis that stands on its own (e.g., for later reference without re-reading the PDF)
- Multiple threads reference the same source material — the artifact becomes a shared anchor

### When a thread reference is enough

- The PDF supported a point in an existing thread
- The discussion was brief or exploratory
- The ideas were absorbed into thread content directly
