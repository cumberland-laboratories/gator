---
message: "Loop: gator loop codex — one-command opt-in Codex participant profile launcher (#37 follow-up)"
change-type: feature
significance: notable
decision-tags: [loop, codex, cli]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- Checkpoint 1 (dedicated profile preparation): new `scripts/loop/codex_launcher.py`.
  - **Home:** default `~/.gator/adapters/codex/loop-home`. `validate_home` refuses the normal Codex home, the caller's `CODEX_HOME`, a home inside the repo, and the temp directory.
  - **Trust key:** `trust_key` uses Codex's own lowercase Windows form.
  - **Rule:** canonical `RULE_TEXT`, byte-identical to the reference note's rule, written UTF-8 without a BOM. An unfamiliar rule or an extra file in `rules/` fails closed.
  - **Config:** one Gator-owned block kept at the end of `config.toml` (`[windows] sandbox = "elevated"` plus trusted project keys). User bytes outside the block are preserved. A user `[windows]` table, a same-repo trust entry or a malformed block fails closed. `tomllib` validates the result on Python 3.11+.
  - **Plan/apply:** `plan_preparation()` is read-only and `apply_preparation()` executes only its actions. `render_dry_run()` previews everything.
  - **Other:** `pyproject.toml` package-data gains `codex_launcher.py`. Charters: loop (Covers/Owns, "Does Not Own: auto-launching" narrowed to this opt-in launcher, three new entries) and cross-cutting (package-data example).
  - **Tests:** `tests/test_loop_codex_launcher.py`.
- Checkpoint 2 (verified launch and command surface):
  - **Rule check:** `codex_launcher.check_policy()` runs `codex execpolicy check` for three probes before every launch. `gator loop status` must be allowed; `git write-tree` and `gator loop end` must match nothing. Any other result, a non-zero exit or non-JSON output blocks the launch.
  - **Launch:** `main()` checks for a governed repo, refuses non-Windows platforms, finds `codex` on PATH, and warns (without refusing) on an unverified Codex version. It prints the trust summary and trust cost, plus the first-sign-in note when the home has no `auth.json` (existence check only). It launches `[codex]` with `CODEX_HOME` set for the child only, returns Codex's exit code, and prints a `codex login` recovery hint naming the home.
  - **CLI:** `gator loop codex [--dry-run] [--home]` in `loop/cli.py` (17 subcommands; no token argument).
  - **Docs:** a "Quick Setup: `gator loop codex`" section in both copies of `codex-routine-participant-profile.md`.
  - **Charters:** loop (entries, 17 subcommands) and cross-cutting (note-pair and `RULE_TEXT` pin).
  - **Tests:** child-only `CODEX_HOME`, the rule-check gate, refusals that write nothing, the version warning, the sign-in/recovery notes, the `auth.json` never-read guard, CLI routing and the absence of a token flag, the note section and pair, plus a real `codex execpolicy` integration test (skipped when Codex is absent).
