---
generated: 2026-06-04
generator: field-guide-gen-v1
type: pi-tutorial
language: bash
source-charters: [installer, cross-cutting]
patterns: bash-patterns.md
---

# Bash Tutorial

Companion to [bash-patterns.md](bash-patterns.md). Real code snippets from this repo, with rationale and charter connections. Read this to restore sharpness on the Bash idioms used in the installer suite.

### Source Chain Decomposition

**Charter connection**: Cross-Cutting — "gatorize.sh Source Chain" TRIPWIRE; Installer — "Decomposed structure" invariant

From `gatorize.sh`:
```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/gatorize-lib.sh"
source "$SCRIPT_DIR/gatorize-actions.sh"
source "$SCRIPT_DIR/gatorize-post.sh"
```

The installer is decomposed into four files:
- `gatorize.sh` — orchestrator (constants, args, scenario dispatch)
- `gatorize-lib.sh` — utilities and detection functions
- `gatorize-actions.sh` — scenario actions (install, upgrade, morph)
- `gatorize-post.sh` — post-install actions (thin link, entry points, registry)

**Why it matters**: The installer was originally one 800+ line file. Decomposition makes each piece independently readable, but introduces a coupling: all four files must coexist in the same directory, and $SCRIPT_DIR must resolve correctly before sourcing. Moving one file breaks the chain silently — Bash will source an empty path and continue with undefined functions.

**What to watch for**: Any operation that moves or copies only some of the four files. The installer template copy logic in gatorize-actions.sh must handle this set as a unit.

### Path Normalization via Subshell

**Charter connection**: Installer — action_feature_branch(), action_install_gator()

From `gatorize.sh`:
```bash
COMMAND_POST="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATES="$COMMAND_POST/templates/gator-starter"
```

From `gatorize-actions.sh`:
```bash
local target
target="$(cd "$1" && pwd)"
```

**Why it matters**: The installer runs from Git Bash on Windows and from native shells on Unix. Paths arrive as relative (`../gator-command`), with dots (`./project`), or as symlinks. The `cd + pwd` pattern resolves all of these to absolute canonical paths in a subshell, without affecting the calling shell's directory. Without this, path comparisons fail (is `/c/Users/../project` the same as `/c/project`?).

**What to watch for**: String-based path manipulation (`$DIR/../other`) instead of the cd+pwd pattern. Also: forgetting to double-quote — unquoted paths with spaces will word-split.

### Git Operations in Subshells

**Charter connection**: Installer — action_feature_branch(), action_register()

From `gatorize-actions.sh`:
```bash
( cd "$target"; git checkout -b "$GATOR_BRANCH" 2>/dev/null || \
  git checkout "$GATOR_BRANCH" 2>/dev/null )
```

From `gatorize-post.sh`:
```bash
( cd "$COMMAND_POST"; git add registry.md )
```

**Why it matters**: The installer operates on two directories simultaneously — the target repo being gatorized and the command-post repo where the registry lives. Using `cd` in the main shell would require tracking which directory you're in and restoring it. Subshells make each git invocation self-contained: the `cd` is local, and the parent shell's working directory is unchanged after the subshell exits.

**What to watch for**: A `cd "$target"` in the main flow (not in a subshell) that changes the working directory without restoring it. Also: assuming `git` commands run in the right directory without an explicit `cd`.

### Scenario Detection via Bitmask-Style Flags

**Charter connection**: Installer — "Five scenarios" invariant

From `gatorize-lib.sh`:
```bash
detect_scenario() {
    local target="$1"
    local has_git=false has_gator=false has_memex=false
    [ -d "$target/.git" ] && has_git=true
    [ -d "$target/.gator" ] && has_gator=true
    [ -d "$target/memex" ] && has_memex=true

    if ! $has_git && ! $has_gator && ! $has_memex; then echo 1  # fresh
    elif $has_git && ! $has_gator && ! $has_memex; then echo 2  # clean git
    elif $has_git && $has_gator; then echo 3                     # upgrade
    elif $has_git && $has_memex && ! $has_gator; then echo 4     # morph
    # ...
```

**Why it matters**: The installer handles 5 mutually exclusive scenarios. Nested if-else chains would be unreadable and easy to get wrong. The bitmask approach tests all conditions upfront, then dispatches. Every combination is explicit — there's no default case that silently handles an unexpected state.

**What to watch for**: A new filesystem condition (e.g., detecting .cursor/) that needs to be added to the scenario matrix. Every new flag doubles the potential combinations — make sure all meaningful combinations are handled.

### Marker-Based Idempotency

**Charter connection**: Installer — action_install_entry_points()

From `gatorize.sh`:
```bash
GATOR_MARKER="# --- Gator Navigation Coding ---"
```

From `gatorize-post.sh`:
```bash
if [ -f "$entry_file" ]; then
    if grep -q "$GATOR_MARKER" "$entry_file"; then
        log_step "  $name already has Gator section — refreshing"
        # ... replace existing section
    else
        log_step "  $name exists — appending Gator section (backup: $backup)"
        # ... backup + append
    fi
else
    log_step "  creating $name"
    # ... create new
fi
```

**Why it matters**: The installer needs to be safe to re-run. Without the marker check, running `gatorize.sh` twice would append duplicate Gator sections to CLAUDE.md, AGENTS.md, etc. The marker provides three-state detection: not present (first install), present (refresh), and present-in-existing-file (append with backup). Each state has different behavior.

**What to watch for**: Adding a new entry point file (e.g., for a new AI tool) without following the marker pattern. Also: changing the GATOR_MARKER string without updating all grep checks.

### Backup Before Overwrite

**Charter connection**: Installer — install_hooks(), action_install_entry_points()

From `gatorize-post.sh`:
```bash
local backup="${entry_file}.pre-gator"
if [ ! -f "$backup" ]; then
    cp "$entry_file" "$backup"
    log_step "  backed up existing $name → ${name}.pre-gator"
fi
```

**Why it matters**: Users may have custom CLAUDE.md instructions, existing git hooks, or other configuration. The .pre-gator backup ensures they can restore their original files if the installation goes wrong. The `[ ! -f "$backup" ]` guard prevents overwriting a backup from a previous run — the first backup is always the original pre-gator state.

**What to watch for**: A new file-writing operation that overwrites user content without creating a backup. The backup suffix is always `.pre-gator` (not `.bak`, `.backup`, `.orig`).

### Overlay-Not-Replace for Templates

**Charter connection**: Cross-Cutting — overlay-not-replace pattern; Installer — overlay_templates()

From `gatorize-actions.sh`:
```bash
overlay_templates() {
    local src_dir="$1" dest_dir="$2"
    # Copy all files from source, preserving directory structure
    # Files in dest that don't exist in src are left untouched
    find "$src_dir" -type f | while read -r src_file; do
        local rel="${src_file#$src_dir/}"
        local dest_file="$dest_dir/$rel"
        mkdir -p "$(dirname "$dest_file")"
        cp "$src_file" "$dest_file"
    done
}
```

**Why it matters**: This is a trust invariant shared with Python's gator-update.py. When templates are refreshed (via gatorize upgrade or gator update), user-created files in .gator/ must survive. A user's charters, threads, mission.md, and artifacts are their intellectual property — overwriting them with blank templates would destroy project knowledge. The overlay ensures template files are refreshed while everything else is preserved.

**What to watch for**: Any code path that deletes files from .gator/ during an upgrade. Also: `rm -rf .gator/` followed by a fresh install — that destroys user content.

### Here-Doc with Quoted Marker

**Charter connection**: Installer — write_stubs(), write_gator_version()

From `gatorize-actions.sh`:
```bash
cat > "$target/.gator/.gator-version" << 'STUB'
generation: 2
installed: YYYY-MM-DD
installer: gatorize.sh
STUB
```

**Why it matters**: The quoted marker ('STUB' vs STUB) prevents variable expansion inside the here-doc. Without quotes, `$variables` in the template content would be expanded — producing broken files if the variable is undefined, or wrong content if it happens to be set. The installer writes YAML, markdown frontmatter, and structured configuration where literal `$` characters or backticks might appear.

**What to watch for**: A here-doc with an unquoted marker that contains text with `$`, backticks, or other shell-interpreted characters. If you need variable expansion in part of the content, use the unquoted form deliberately and document which variables are expanded.

### Confirm Gate Before Destructive Ops

**Charter connection**: Installer — action_feature_branch() (dirty tree), action_install_gator()

From `gatorize-lib.sh`:
```bash
confirm() {
    local prompt="$1" default="$2"
    if [ "$default" = "Y" ]; then
        read -r -p "$prompt [Y/n] " answer
        case "$answer" in [Nn]*) return 1 ;; *) return 0 ;; esac
    else
        read -r -p "$prompt [y/N] " answer
        case "$answer" in [Yy]*) return 0 ;; *) return 1 ;; esac
    fi
}
```

**Why it matters**: The installer creates branches, copies files, and modifies git state. The confirmation gate ensures the PI has a chance to abort before irreversible changes. The default parameter is load-bearing: safe operations default to "Y" (pressing enter proceeds), risky operations default to "N" (pressing enter aborts). The case-insensitive match (`[Yy]*`) handles both "y" and "Yes".

**What to watch for**: A new destructive operation without a confirm gate. Also: using "Y" as the default for an operation that modifies existing content.
