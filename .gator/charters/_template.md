# Charter: [Module Name]

**Covers**: `path/to/module/**`

## Owns

[Durable responsibilities and contracts. Keep this about ownership, not history.]

## Does Not Own

[Adjacent responsibilities that belong elsewhere.]

### function_name(args)
File: path/to/file.py
[One line describing behavior and important state access.]
Filesystem: [important paths and R/W mode, if any]
<- [callers or entry points]
-> [callees or dependencies]
! [non-obvious invariant to preserve]

## Before Changing This Module

- [Contract or boundary to verify.]
- [Focused validation to run.]

## Connections

-> [Other Charter] - replace this placeholder with a real relative link and explain the boundary
