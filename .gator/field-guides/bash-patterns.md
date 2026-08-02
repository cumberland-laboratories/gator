---
generated: 2026-06-04
generator: field-guide-gen-v1
type: agent-patterns
language: bash
source-charters: [installer, cross-cutting]
source-file-count: 4
pattern-count: 12
tutorial: bash-tutorial.md
---

# Bash Patterns

### Source Chain Decomposition
Files: gatorize.sh, gatorize-lib.sh, gatorize-actions.sh, gatorize-post.sh
Main script sources three library files via `source "$SCRIPT_DIR/gatorize-*.sh"`. All four must be in the same directory. $SCRIPT_DIR must be set before sourcing.
! Adding a function called from multiple files? Put it in gatorize-lib.sh. New scenario action? gatorize-actions.sh. Charter: cross-cutting source chain tripwire.

### Path Normalization via Subshell
Files: gatorize.sh, gatorize-actions.sh, gatorize-post.sh
Normalize paths with `"$(cd "$DIR" && pwd)"`. Always double-quote. Handles relative paths, symlinks, and ./ prefixes uniformly.

### Git Operations in Subshells
Files: gatorize-actions.sh, gatorize-post.sh
Every git command runs in `( cd "$target"; git ... )`. No pushd/popd, no cd-then-cd-back. The subshell isolates the directory change.

### Confirm Gate Before Destructive Ops
Files: gatorize-lib.sh (definition), gatorize.sh, gatorize-actions.sh
`confirm "prompt" "Y"` (default yes) or `confirm "prompt" "N"` (default no). Risky ops get "N" default. Parse is case-insensitive.

### Boolean Variables as Strings
Files: gatorize.sh, gatorize-lib.sh, gatorize-actions.sh
Use `var=true`/`var=false`, test with `$var && action` or `[ "$var" = true ]`. Never 0/1 for booleans.

### Scenario Detection via Bitmask-Style Flags
Files: gatorize.sh, gatorize-lib.sh
Set boolean flags (has_git, has_gator, has_memex), then case-dispatch on the combination. Returns scenario 1-5. All paths are explicit.

### Marker-Based Idempotency
Files: gatorize.sh, gatorize-actions.sh, gatorize-post.sh
Define markers at top (GATOR_MARKER). Use `grep -q "marker" "$file"` to detect if already processed. Allows safe re-runs without duplicating content.

### Backup Before Overwrite
Files: gatorize-actions.sh, gatorize-post.sh
Check if file exists, check if it already has the gator marker, if not create `.pre-gator` backup, then write. Preserves user customizations, enables rollback.

### Overlay-Not-Replace for Templates
Files: gatorize-actions.sh
Template files overwrite same-named files. Files that exist only in the target are never deleted. User charters, threads, and artifacts are sacred.
! Charter: cross-cutting overlay-not-replace pattern. Same invariant as Python gator-update.py.

### Here-Doc with Quoted Marker
Files: gatorize-actions.sh, gatorize-post.sh
Write multi-line content with `cat > "$path" << 'STUB'` (quoted marker prevents variable expansion). Used for all stub files and version markers.

### Counter + Log Pattern
Files: gatorize-actions.sh, gatorize-post.sh
Initialize counter before loop, `counter=$((counter + 1))` inside, `[ "$counter" -gt 0 ] && log_step ...` after. Used for install_hooks, morph migrations, template copies.

### Section Markers for Function Groups
Files: gatorize-actions.sh, gatorize-lib.sh
Visual separators: `# ====...====` followed by `# Section Name`. Creates clear boundaries between 100+ line functions.
