# Charter: [Module Name]

**Covers**: `path/to/module/`

## Owns

[What this module is responsible for]

## Does Not Own

[What belongs elsewhere — prevents scope creep]

---

### function_name(args)
File: path/to/file.py
[One line: what it does]
Models: [what it reads/writes — e.g., User(R), Order(RW)]
← [callers — what calls this]
→ [callees — what this calls]
! [tripwire — non-obvious behavior to preserve]

---

## Before Changing This Module

[Institutional knowledge: implicit contracts, stubs, intentional decisions]

## Connections

→ [Other Charter](other-module.md) — why the link exists
