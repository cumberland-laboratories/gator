# Charter: Graph and Wiki

**Covers**: `src/gator_command/scripts/legacy/generate_wiki.py`, `src/gator_command/scripts/legacy/generate_markdown.py`, `src/gator_command/scripts/legacy/graph_health.py`, `src/gator_command/scripts/legacy/crawler.py`

**Status**: Legacy — these are Memex-era tools. No new feature development.

## Owns

Thread graph rendering and health analysis for the Memex knowledge layer:

- `generate_wiki.py` owns thread graph parsing and MediaWiki rendering. Provides the core data structures (`Thread`, `Link`) and loading/parsing functions used by `graph_health.py`.
- `generate_markdown.py` owns Markdown rendering of the thread graph. Parallel output path to `generate_wiki.py` — same input, different output format.
- `graph_health.py` owns directed graph analysis of thread cross-references: backlink index, 3-hop reachability violations, bridge edge detection, and PNG visualization. Depends on networkx and imports thread-loading from `generate_wiki.py`.
- `crawler.py` owns automated maintenance: runs `graph_health.py`, triages findings against procedure thresholds, and optionally invokes Claude Sonnet to propose fixes on a maintenance branch.

## Does Not Own

- Thread content authoring — threads are PI-owned markdown files.
- Fleet repo thread graphs — this cluster operates on the command-post's `gator-command/` thread graph only.
- The graph-health-response procedure thresholds — those live in `.gator/procedures/graph-health-response.md`.
- Session archaeology or governance telemetry — that belongs to the session-archaeology and fleet-intelligence clusters.

---

### parse_frontmatter(text) / parse_sections(body)
File: `src/gator_command/scripts/generate_wiki.py`
`parse_frontmatter()` splits YAML frontmatter from Markdown body and returns `(dict, body)`. `parse_sections()` extracts h1 title and section bodies keyed by heading.
Filesystem: none (pure parsing)
<- `load_threads()`
! Frontmatter parsing uses a simple split on `---\n` — not a full YAML parser. Keys with colons in values may mis-parse. Thread frontmatter should use simple scalar values only.

### load_threads(memex_dir)
File: `src/gator_command/scripts/generate_wiki.py`
Loads all threads from `active-threads/` and `threads/` under a memex directory. Returns a list of `Thread` dataclass instances with parsed frontmatter, summary lines, and connection lines.
Filesystem: `gator-command/active-threads/`, `gator-command/threads/` (R)
<- `graph_health.build_graph()`, wiki/markdown rendering pipelines
! The `graph:` frontmatter field determines which graph namespace a thread belongs to ("user", "design", or custom). Threads without a `graph:` field default to "user". `graph_health.py` can filter to a single namespace via `--graph`.

### extract_links(connection_lines)
File: `src/gator_command/scripts/generate_wiki.py`
Extracts `Link` objects from the Connections section of a thread. Parses standard Markdown links `[label](path)` plus annotation text after the closing paren.
Filesystem: none
<- `graph_health.build_graph()`
! Links with relative paths are resolved relative to the thread's source file. Broken links (paths that don't resolve to a real file) become graph edges to non-existent nodes — `graph_health.py` will flag them as reachability violations.

---

### build_graph(memex_dir, graph_filter=None)
File: `src/gator_command/scripts/graph_health.py`
Builds a directed networkx `DiGraph` from thread cross-references. When `graph_filter` is set, only threads with matching `graph:` frontmatter are included; cross-graph links to excluded threads are dropped.
Filesystem: thread directories (R)
<- `main()`, `crawler.run_health_check()`
-> `load_threads()`, `extract_links()` from `generate_wiki`
! networkx is a required external dependency. The graph is directed (A → B does not imply B → A). Bridge edge detection and reachability analysis assume the graph is connected — isolated threads are noted separately.

### run_health_check(graph_filter=None)
File: `src/gator_command/scripts/crawler.py`
Runs `graph_health.py --json` as a subprocess and reads the resulting JSON from `wiki/graph-health-crawler.json`.
Filesystem: `wiki/graph-health-crawler.json` (R after subprocess)
<- `main()`
! `REPO_ROOT` is hardcoded as 2 parents up from `SCRIPTS_DIR` (i.e., the gator-command repo root). This script is not relocatable — it must run from inside the gator-command repo tree. The subprocess approach avoids Python import issues with networkx availability.

### triage(health)
File: `src/gator_command/scripts/crawler.py`
Applies procedure thresholds from `graph-health-response.md` to the health dict. Returns a list of findings with severity and recommended action.
Filesystem: none (reads threshold constants, not the procedure file at runtime)
<- `main()`
! Threshold values are currently hardcoded in `triage()`, not read from the procedure file at runtime. If thresholds change in the procedure, update the code too.

---

## TRIPWIRE: generate_wiki.py as a Shared Library

`graph_health.py` imports `extract_links` and `load_threads` directly from `generate_wiki.py`:

```python
from generate_wiki import extract_links, load_threads
```

`generate_wiki.py` is both a standalone rendering script and a library. Any change to these two functions' signatures or return types breaks `graph_health.py`. The `Thread` and `Link` dataclass field names are also part of this contract — `graph_health.py` reads `.graph`, `.source_path`, `.title`, `.connection_lines` directly.

## TRIPWIRE: crawler.py Hardcoded Paths

`crawler.py` uses `REPO_ROOT = Path(__file__).resolve().parents[2]` and hardcodes `MEMEX_DIR = REPO_ROOT / "gator-command"`. This script is not relocatable and will break if moved more than 2 directory levels from the repo root, or if the `gator-command/` directory is renamed.

## Before Changing This Module

- `graph_health.py` requires networkx (`pip install networkx`). Other scripts in this codebase have zero required dependencies. Do not add networkx imports to any other script without a fallback.
- The `graph:` frontmatter field in threads is the mechanism for graph namespace filtering. Adding a new namespace requires no code change — just use the new value in thread frontmatter and pass `--graph` to `graph_health.py`.
- `crawler.py` invokes Claude Sonnet (via subprocess or API) in `--fix` mode. This is the only script in the codebase that makes outbound LLM calls. Changes to the invocation method must preserve the dry-run/fix-mode separation.
- `generate_wiki.py` and `generate_markdown.py` share the same thread-loading infrastructure but have separate rendering pipelines. If `load_threads()` changes, both renderers are affected.

## Connections

-> [scripts-core-library](scripts-core-library.md) — no direct dependency on gator_core (graph scripts predate it)
-> [procedures/graph-health-response](../procedures/graph-health-response.md) — procedure thresholds that crawler.py enforces
-> [scripts-cross-cutting](scripts-cross-cutting.md) — library/script dual-use pattern
-> [Index](INDEX.md)
