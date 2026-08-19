#!/usr/bin/env python3
"""
gator-hook.py — Machine-side hook dispatcher (runtime-split Phase 3).

The single entry point git hook stubs and vendor SessionStart hooks call
on pinned repos. Applies `gator_core.resolve_governed_runtime` and runs
the governing runtime from wherever the decision says it lives:

  - `current` / `cli-newer`     → the installed wheel's runtime
                                  (templates/gator-starter/scripts/)
  - `repo-scripts` / `pin-unreadable`
                                → the repo-resident copy (pre-split behavior)
  - `refuse` + repo copy exists → the repo copy IS the pinned runtime —
                                  run it with an upgrade advisory (true
                                  refusal only bites post-Phase-4 when no
                                  repo copy exists)
  - `refuse` + no repo copy     → pre-commit: block (exit 1);
                                  other hooks: warn + exit 0 (never strand
                                  a mid-flight commit or a session open)
  - `ungoverned`                → warning mode, exit 0 (matches the
                                  pre-split stub's warning contract)

Usage:  gator-hook.py <hook-name> [passthrough-args...]
Hooks:  pre-commit | commit-msg | post-commit | session-open | session-start

Invoked by the pin-aware stubs `build_git_hook_wrappers` generates (git
hooks) and by the `gator hook` CLI verb (vendor SessionStart hooks).
stdin is inherited by the child — session-start reads its vendor payload
from stdin and must see it untouched.

@reads: .gator/runtime-pin.json (via resolver), repo + wheel runtime dirs
@writes: nothing itself — the dispatched script owns all side effects
"""

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from gator_core import ensure_utf8_stdout, resolve_governed_runtime  # noqa: E402


# hook name → (runtime script, fixed args, passthrough argv?)
HOOK_MAP = {
    "pre-commit":    ("gator-pre-commit.py", ["--phase", "validate"], False),
    "commit-msg":    ("gator-pre-commit.py", ["--phase", "trailers"], True),
    "post-commit":   ("gator-pre-commit.py", ["--phase", "cleanup"], False),
    "session-open":  ("gator-session-open.py", [], False),
    "session-start": ("gator-session-start.py", [], False),
}

# Hooks whose failure must block the git operation. Everything else
# degrades to warn-and-proceed — a session hook or trailer pass must
# never strand the user.
BLOCKING_HOOKS = {"pre-commit"}


def _wheel_runtime_dir():
    """The installed wheel's runtime — the template scripts dir."""
    return SCRIPTS_DIR.parent / "templates" / "gator-starter" / "scripts"


def _repo_runtime_dir(repo_root):
    """The repo-resident runtime dir, v2-first, or None."""
    for candidate in (
        repo_root / ".gator" / ".includes" / "scripts",
        repo_root / ".gator" / "scripts",
    ):
        if candidate.is_dir():
            return candidate
    return None


def plan_dispatch(hook_name, repo_root, decision, wheel_dir=None):
    """Pure planning: decide what to run for this hook under this decision.

    Returns {"action": "run"|"block"|"skip", "script": Path|None,
             "advisory": str|None, "exit_code": int}
    """
    script_name = HOOK_MAP[hook_name][0]
    wheel_dir = wheel_dir or _wheel_runtime_dir()
    repo_dir = _repo_runtime_dir(Path(repo_root))
    mode = decision["mode"]

    if mode in ("current", "cli-newer"):
        advisory = decision["reason"] if mode == "cli-newer" else None
        wheel_script = wheel_dir / script_name
        if wheel_script.is_file():
            return {"action": "run", "script": wheel_script,
                    "advisory": advisory, "exit_code": 0}
        # Wheel runtime incomplete (packaging fault) — repo copy is the
        # honest fallback while it exists; otherwise treat as refusal.
        if repo_dir and (repo_dir / script_name).is_file():
            return {"action": "run", "script": repo_dir / script_name,
                    "advisory": f"installed wheel is missing {script_name}; "
                                f"using the repo-resident copy — reinstall "
                                f"gator-command.", "exit_code": 0}
        mode = "refuse"
        decision = dict(decision, reason=(
            f"installed wheel is missing {script_name} and this repo "
            f"carries no runtime copy. Reinstall: pipx reinstall "
            f"gator-command."))

    if mode in ("repo-scripts", "pin-unreadable"):
        advisory = decision["reason"] if mode == "pin-unreadable" else None
        if repo_dir and (repo_dir / script_name).is_file():
            return {"action": "run", "script": repo_dir / script_name,
                    "advisory": advisory, "exit_code": 0}
        return {"action": "skip", "script": None,
                "advisory": "Gator: no runtime found for this branch — "
                            "proceeding in warning mode.", "exit_code": 0}

    if mode == "refuse":
        # The repo copy IS the pinned runtime — running it honors the pin.
        if repo_dir and (repo_dir / script_name).is_file():
            return {"action": "run", "script": repo_dir / script_name,
                    "advisory": f"gator runtime: {decision['reason']} "
                                f"(using the repo-resident pinned runtime "
                                f"for this run)", "exit_code": 0}
        if hook_name in BLOCKING_HOOKS:
            return {"action": "block", "script": None,
                    "advisory": f"\n  gator pre-commit: RUNTIME VERSION "
                                f"MISMATCH\n\n  {decision['reason']}\n",
                    "exit_code": 1}
        return {"action": "skip", "script": None,
                "advisory": f"gator runtime: {decision['reason']} — "
                            f"{hook_name} skipped.", "exit_code": 0}

    # ungoverned
    return {"action": "skip", "script": None,
            "advisory": "\n  Gator: governance hooks are installed, but the "
                        "current branch\n  does not contain .gator/. "
                        "Proceeding in warning mode.\n  If this branch "
                        "should be governed, merge or restore the Gator "
                        "layer.\n", "exit_code": 0}


def main(argv=None):
    ensure_utf8_stdout()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in HOOK_MAP:
        print(f"usage: gator-hook.py <{'|'.join(HOOK_MAP)}> [args...]",
              file=sys.stderr)
        return 2

    hook_name = argv[0]
    passthrough = argv[1:]
    repo_root = Path.cwd()

    decision = resolve_governed_runtime(repo_root)
    plan = plan_dispatch(hook_name, repo_root, decision)

    if plan["advisory"]:
        print(plan["advisory"])
    if plan["action"] != "run":
        return plan["exit_code"]

    _, fixed_args, wants_passthrough = HOOK_MAP[hook_name]
    cmd = [sys.executable, str(plan["script"])] + fixed_args
    if wants_passthrough:
        cmd += passthrough
    return subprocess.call(cmd, cwd=str(repo_root))


if __name__ == "__main__":
    sys.exit(main())
