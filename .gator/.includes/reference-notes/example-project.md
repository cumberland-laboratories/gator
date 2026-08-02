# Worked Example: taskflow (a simple Python CLI task manager)

This is a complete reference showing what a populated Gator knowledge layer looks like for a small Python project. Study this before bootstrapping your own project. The format, density, and style shown here is what you're aiming for.

---

## The Project

`taskflow` — a CLI task manager in Python. ~800 lines across 5 files:
```
taskflow/
  __main__.py      # CLI entry point (click)
  store.py         # SQLite persistence
  models.py        # Task, Project dataclasses
  filters.py       # Query builder for task lists
  export.py        # Markdown/JSON export
```

---

## Example: mission.md

```markdown
# Mission

## What We're Building

A command-line task manager that stores tasks in SQLite and exports to Markdown.
Designed for solo developers who want something between a text file and Jira.

## Why It Exists

Every task manager either requires a browser or locks data in a proprietary format.
taskflow is local-first, file-friendly, and scriptable.

## What Success Looks Like

- `task add "fix login bug" --project api` works in under 50ms
- Tasks survive across machines via git (SQLite file in repo)
- Weekly review exports to Markdown that reads well in any viewer
```

---

## Example: roadmap.md

```markdown
# Roadmap

| # | Feature | Status | Next step |
|---|---------|--------|-----------|
| 1 | Core CRUD (add/done/delete/list) | Done | — |
| 2 | Project grouping | Done | — |
| 3 | Priority sorting | Building | Wire into `list` output |
| 4 | Markdown export | Designed | Template in export.py |
| 5 | Recurring tasks | Considering | Need cron-like syntax |
| 6 | Due dates with reminders | Deferred | After recurring tasks |
```

---

## Example: charters/INDEX.md

```markdown
# Charter Index

**Always read first:** [Cross-Cutting](cross-cutting.md)

| If you're changing... | Read these charters |
|---|---|
| `taskflow/__main__.py` | [CLI](cli.md) + [Cross-Cutting](cross-cutting.md) |
| `taskflow/store.py` | [Store](store.md) + [Cross-Cutting](cross-cutting.md) |
| `taskflow/models.py` | [Models](models.md) |
| `taskflow/filters.py` | [Store](store.md) + [Cross-Cutting](cross-cutting.md) |
| `taskflow/export.py` | [Export](export.md) |
```

---

## Example: charters/cross-cutting.md

```markdown
# Charter: Cross-Cutting Patterns

### TRIPWIRE: SQLite file locking

The store opens a single connection at CLI entry and closes on exit.
Concurrent access (two terminals) will hit SQLite's write lock.
This is intentional — taskflow is single-user. Do NOT add connection
pooling or WAL mode unless the mission changes to multi-user.

### TRIPWIRE: Task ID stability

Task IDs are SQLite rowids. They are permanent — deletion does not
reassign IDs. Export files reference IDs. If you ever compact/reindex,
every exported Markdown file breaks.

### Data flow: add command

__main__.py (parse args)
  → models.py (Task dataclass construction)
    → store.py (INSERT, returns ID)
      → __main__.py (prints confirmation with ID)

### Data flow: export command

__main__.py (parse args, date range)
  → filters.py (build WHERE clause)
    → store.py (SELECT with filter)
      → export.py (format as Markdown or JSON)
        → __main__.py (write to stdout or file)
```

---

## Example: charters/store.md

```markdown
# Charter: Store

**Covers**: `taskflow/store.py`

## Owns

SQLite connection lifecycle, all INSERT/UPDATE/DELETE/SELECT operations,
schema migration, file path resolution.

## Does Not Own

Task validation (models.py owns that).
Query building for complex filters (filters.py owns that).
Formatting output (export.py owns that).

---

### init_db(path)
File: taskflow/store.py
Creates SQLite DB at path if absent. Runs migrations.
← __main__.py (called once at startup)
→ sqlite3.connect()
! Path defaults to ./tasks.db relative to CWD, not the package.
  This is intentional — the DB lives in the project, not globally.

### add_task(task: Task) -> int
File: taskflow/store.py
Inserts Task, returns rowid.
Models: Task(R), sqlite(W)
← __main__.py add command
! Returns the rowid, not a Task object. Caller must use this ID.

### get_tasks(filter: Filter) -> list[Task]
File: taskflow/store.py
Runs SELECT with filter's WHERE clause, returns Task list.
Models: Task(R), sqlite(R)
← __main__.py list command, export.py
→ filters.py build_where()
! Returns empty list (not None) when no matches. Callers rely on this.

### mark_done(task_id: int) -> bool
File: taskflow/store.py
Sets done=True, done_at=now(). Returns False if ID not found.
Models: sqlite(RW)
← __main__.py done command
! Does NOT delete the task. "Done" is a state, not removal.

### delete_task(task_id: int) -> bool
File: taskflow/store.py
Hard deletes by rowid. Returns False if ID not found.
Models: sqlite(W)
← __main__.py delete command
! See cross-cutting TRIPWIRE on ID stability.

---

## Before Changing This Module

- Schema changes require a migration function (see bottom of file)
- The connection is opened once and passed around — not per-query
- All timestamps are UTC ISO-8601 strings, not datetime objects

## Connections

→ [Models](models.md) — Task dataclass definition
→ [Cross-Cutting](cross-cutting.md) — SQLite locking, ID stability
```

---

## Example: charters/cli.md

```markdown
# Charter: CLI

**Covers**: `taskflow/__main__.py`

## Owns

Argument parsing (click), command routing, DB initialization,
user-facing output formatting, exit codes.

## Does Not Own

Business logic (store.py). Data shapes (models.py).
Export formatting (export.py).

---

### main()
File: taskflow/__main__.py
Click group entry point. Initializes DB connection.
→ init_db() in store.py
! Exit code 0 on success, 1 on error. Scripts depend on this.

### add(name, project, priority)
File: taskflow/__main__.py
Parses add-command args, creates Task, calls store.
→ Task() in models.py, add_task() in store.py
← CLI: `task add "name" --project X --priority N`

### list(project, status, sort)
File: taskflow/__main__.py
Builds filter from flags, fetches tasks, prints table.
→ Filter() in filters.py, get_tasks() in store.py
! --sort=priority is descending (high first). Not alphabetical.

---

## Before Changing This Module

- Every command prints to stdout. Errors go to stderr.
- Click handles --help automatically. Don't duplicate.
- The DB path comes from --db flag or TASKFLOW_DB env var.

## Connections

→ [Store](store.md) — all persistence
→ [Cross-Cutting](cross-cutting.md) — data flows start here
```

---

## Example: threads/sqlite-vs-postgres.md

```markdown
---
last-touched: 2026-05-10
tags: [architecture, database, decision]
---

# SQLite vs Postgres

## Summary

Evaluated Postgres for multi-user support. Decision: stay on SQLite.
The project is single-user by mission. Postgres adds deployment complexity
(managed service, connection strings, migrations) for zero benefit at
current scope. Revisit only if mission changes to multi-user.

## Connections

→ [Store charter](../charters/store.md) — the module this decision constrains
```

---

## Example: commit_draft.md

```markdown
# Session Change Log

- Added priority field to Task model and store schema [#feature] [#models] -agent
- Updated store charter: add_task now accepts priority param [#charter-update] -agent
- Architect decision: priority is 1-5 integer, not string label [#decision] [#models] -architect
- Updated cross-cutting: added note about priority sort direction [#charter-update] -agent
```

---

## Key Observations

1. **Charters are short.** Each function entry is 3-5 lines. The whole store charter is maybe 60 lines for a real module. This is a small, compressed map — not a rewrite of the code.

2. **Cross-cutting is the star.** The TRIPWIREs prevent the two most common agent mistakes: adding connection pooling to a single-user app, and reindexing IDs that exported files depend on.

3. **"Does not own" is load-bearing.** It prevents the agent from putting export logic in the store, or validation logic in the CLI. Scope boundaries are the first thing that erodes without governance.

4. **Threads are tiny.** The SQLite-vs-Postgres thread is 8 lines. It exists so the decision doesn't have to be re-explained every session.

5. **The loop is visible in commit_draft.** Charter updates appear alongside code changes. They're the same operation.
