# Charter: Strategic Pulse

**Covers**: `src/gator_command/scripts/gator-pulse.py`, `src/gator_command/templates/gator-starter/scripts/gator-pulse.py`

## Owns

- Generation of `.gator/pulse.md` from repository strategy and recent evidence.
- Bounded parsing of roadmap, inbox, issues, assessments, sessions, and Git activity.

## Does Not Own

- The content or priorities in mission, roadmap, inbox, or project assessments.
- Dashboard rendering of pulse documents.
- Session aggregation beyond reading committed decisions.

---

### get_recent_commits() / get_branch()
File: src/gator_command/scripts/gator-pulse.py
Read bounded recent Git activity and current branch without mutating the repository.
<- `build_pulse()`
-> Git
! Git failure yields an explicit unavailable/empty section rather than aborting the full brief.

### get_latest_assessment()
File: src/gator_command/scripts/gator-pulse.py
Select the newest dated project assessment artifact.
Filesystem: `.gator/artifacts/*-project-assessment.md` (R)
<- `build_pulse()`
! Selection is deterministic by dated artifact name; arbitrary artifacts are not treated as assessments.

### extract_roadmap_table() / parse_roadmap_items()
File: src/gator_command/scripts/gator-pulse.py
Extract concise roadmap state while preserving priority order.
<- `build_pulse()`
! Bound output size; pulse is an operations brief, not a copy of the roadmap.

### parse_issues() / parse_inbox_items() / get_session_decisions()
File: src/gator_command/scripts/gator-pulse.py
Extract actionable open items and recent committed decisions from stable repository formats.
<- `build_pulse()`
! Malformed individual items are skipped or reported without discarding the rest of the brief.

### build_pulse(repo_path, days=7)
File: src/gator_command/scripts/gator-pulse.py
Compose the strategic brief from current strategy, recent activity, and the latest assessment.
Filesystem: `.gator/pulse.md` content source surfaces (R)
<- `main()`
-> parsers and Git readers
! Sections stay bounded and source-attributed. Do not infer a new roadmap priority from commit volume alone.

### main()
File: src/gator_command/scripts/gator-pulse.py
Resolve the governed repo, generate the brief, and write `.gator/pulse.md`.
Filesystem: `.gator/pulse.md` (W)
<- `gator pulse`
! Package and starter-template copies remain synchronized where compatibility tests require it.

## Before Changing This Module

- Test missing/malformed optional inputs and an empty Git history.
- Preserve deterministic ordering and bounded output.
- Run pulse tests and template-sync checks.

## Connections

-> [Session Archaeology](scripts-session-archaeology.md) - committed decision input
-> [Cross-Cutting](scripts-cross-cutting.md) - template-copy and Git conventions
-> [Dashboard UI](scripts-dashboard-ui.md) - pulse document consumer
