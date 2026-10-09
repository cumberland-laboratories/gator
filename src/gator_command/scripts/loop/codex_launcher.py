"""Opt-in Codex loop-participant launcher (`gator loop codex`, #37 follow-up).

Packages the verified #37 Phase 1 profile (reference note
`codex-routine-participant-profile.md`) as one explicit command. It prepares a
dedicated, loop-only `CODEX_HOME` containing exactly the verified
five-subcommand rule plus a Gator-owned trust/sandbox block in `config.toml`.

Boundaries (see scripts-loop.md):
- writes only inside the dedicated home; never reads the normal Codex home;
- never accepts, stores, prints, or passes a loop token;
- never starts, joins, or authorizes a loop;
- unfamiliar rules and config conflicts fail closed (manual-note pointer).

This module has no imports from the loop state modules (session,
state_machine, submit, host), so it cannot affect loop authority.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


MANUAL_NOTE = "reference-notes/codex-routine-participant-profile.md"
VERIFIED_CODEX_VERSION = "0.144.1"

# The exact rule verified in #37 Phase 1. Must stay byte-identical (after the
# note's three-space indent is removed) to the rule in MANUAL_NOTE; pinned by
# tests/test_loop_codex_launcher.py. Written UTF-8 without a BOM, LF endings.
RULE_TEXT = (
    'prefix_rule(\n'
    '    pattern = ["gator", "loop", ["status", "wait", "submit-draft", "submit-review", "submit-implementation"]],\n'
    '    decision = "allow",\n'
    '    justification = "Gator loop participant routine commands; Gator enforces token, role, turn and candidate freshness.",\n'
    '    match = [\n'
    '        ["gator", "loop", "status", "--token", "glp_x"],\n'
    '        ["gator", "loop", "submit-review", "--token", "glp_x", "--file", "r.md", "--approve"],\n'
    '    ],\n'
    '    not_match = [\n'
    '        ["gator", "loop", "end", "--token", "glp_x"],\n'
    '        ["gator", "gatorize", "."],\n'
    '        ["git", "write-tree"],\n'
    '    ],\n'
    ')\n'
)
RULE_BYTES = RULE_TEXT.encode("utf-8")
# Earlier Gator-generated forms that may be normalized to RULE_BYTES.
KNOWN_GENERATED_RULES = frozenset({
    RULE_TEXT.replace("\n", "\r\n").encode("utf-8"),
})
RULE_FILE = "default.rules"

TRUST_WARNING = (
    "  Trust cost: in this Codex session, `gator loop status | wait | submit-draft |\n"
    "  submit-review | submit-implementation` and every process they start (including\n"
    "  Gator's Git calls) run OUTSIDE the Codex sandbox with your full user rights,\n"
    "  without a prompt. Everything else stays subject to normal Codex policy.\n"
    "  Gator still enforces the token, role, turn and candidate freshness."
)
SIGN_IN_NOTE = (
    "  Codex will ask you to sign in for this isolated Gator Loop profile.\n"
    "  Sign in there, then continue in the same session."
)

# (argv after `--`, expected) for the per-launch policy proof. Literal
# placeholder arguments only; no real token is ever passed.
POLICY_PROBES = (
    (["gator", "loop", "status", "--token", "x"], "allow"),
    (["git", "write-tree"], "no-match"),
    (["gator", "loop", "end", "--token", "x"], "no-match"),
)

BLOCK_BEGIN = "# BEGIN GATOR LOOP PROFILE — managed by `gator loop codex`; edit outside this block only"
BLOCK_END = "# END GATOR LOOP PROFILE"
_PROJECT_HEADER = re.compile(r"^\[projects\.'(?P<key>[^'\r\n]*)'\]$")

_BOM = b"\xef\xbb\xbf"


class ProfileError(Exception):
    """A refusal with a user-facing message. Nothing has been written."""

    def __init__(self, message):
        super().__init__(f"{message}\n  Manual setup and recovery: {MANUAL_NOTE}")


# ---------------------------------------------------------------------------
# Home and trust key
# ---------------------------------------------------------------------------

def default_home():
    """Machine-local default dedicated home (user-private, never repo content)."""
    return Path.home() / ".gator" / "adapters" / "codex" / "loop-home"


def _norm(path):
    return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))


def _within(child, parent):
    child, parent = _norm(child), _norm(parent)
    return child == parent or child.startswith(parent.rstrip("\\/") + os.sep)


def validate_home(home, repo_root, env, tempdir=None):
    """Return the resolved dedicated home, or raise ProfileError.

    Refuses the normal Codex home (`~/.codex` or the caller's CODEX_HOME), a
    home inside the governed repository, and a home under the temp directory
    (Codex refuses to create its helpers there). Read-only.
    """
    home = Path(home).expanduser().resolve(strict=False)
    normal_homes = [Path.home() / ".codex"]
    if env.get("CODEX_HOME"):
        normal_homes.append(Path(env["CODEX_HOME"]))
    for normal in normal_homes:
        if _within(home, normal):
            raise ProfileError(
                f"Refusing to use {home}: it is (inside) your normal Codex home {normal}. "
                "The loop rule must live in a dedicated home only.")
    if _within(home, repo_root):
        raise ProfileError(
            f"Refusing to use {home}: it is inside the repository {repo_root}. "
            "The dedicated home is machine-local state, never repository content.")
    temp = tempdir if tempdir is not None else tempfile.gettempdir()
    if _within(home, temp):
        raise ProfileError(
            f"Refusing to use {home}: it is under the temp directory {temp}, "
            "where Codex refuses to create its helpers.")
    return home


def trust_key(repo_root, platform):
    """The `[projects.'<key>']` key for the repository.

    Windows: the form Codex itself writes (spike §8.8) — backslashes,
    lowercase, no `\\\\?\\` prefix. Elsewhere: the resolved POSIX path.
    """
    path = str(Path(repo_root).resolve(strict=False))
    if platform == "win32":
        path = path.replace("/", "\\")
        if path.startswith("\\\\?\\"):
            path = path[4:]
        path = path.lower()
    if "'" in path or "\n" in path or "\r" in path:
        raise ProfileError(
            f"Repository path {path!r} cannot be written as a literal TOML key.")
    return path


# ---------------------------------------------------------------------------
# config.toml: one Gator-owned block, always last
# ---------------------------------------------------------------------------

def _split_block(lines):
    """Return (outside_lines, block_keys) or raise on a malformed block."""
    begins = [i for i, l in enumerate(lines) if l.strip() == BLOCK_BEGIN]
    ends = [i for i, l in enumerate(lines) if l.strip() == BLOCK_END]
    if not begins and not ends:
        return list(lines), []
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        raise ProfileError(
            "config.toml has a malformed Gator loop profile block "
            "(missing, duplicated, or misordered markers).")
    b, e = begins[0], ends[0]
    keys = []
    for line in lines[b + 1:e]:
        m = _PROJECT_HEADER.match(line.strip())
        if m:
            keys.append(m.group("key"))
    return lines[:b] + lines[e + 1:], keys


def _outside_conflicts(outside, repo_key, platform):
    fold = (lambda s: s.lower()) if platform == "win32" else (lambda s: s)
    for line in outside:
        text = line.strip()
        if platform == "win32" and (re.match(r"^\[\s*windows\s*\]", text)
                                    or re.match(r"^windows\s*\.", text)):
            return f"a user-managed [windows] setting exists outside the Gator block: {text!r}"
        if text.startswith("[projects") and fold(repo_key) in fold(text):
            return f"a user-managed trust entry for this repository exists outside the Gator block: {text!r}"
    return None


def render_config(existing_text, repo_key, platform):
    """Return the new config.toml text. Pure; raises ProfileError on conflict.

    Every byte outside the Gator block is kept; the block is regenerated at
    the end of the file with the union of its trusted repositories and the
    current one, plus `[windows] sandbox = "elevated"` on Windows.
    """
    nl = "\r\n" if "\r\n" in existing_text else "\n"
    lines = existing_text.splitlines()
    outside, keys = _split_block(lines)
    conflict = _outside_conflicts(outside, repo_key, platform)
    if conflict:
        raise ProfileError(f"Refusing to edit config.toml: {conflict}.")
    if repo_key not in keys:
        keys.append(repo_key)
    for key in keys:
        if "'" in key:
            raise ProfileError("config.toml Gator block holds an unquotable key.")

    block = [BLOCK_BEGIN]
    if platform == "win32":
        block += ["[windows]", 'sandbox = "elevated"', ""]
    for key in keys:
        block += [f"[projects.'{key}']", 'trust_level = "trusted"', ""]
    if block[-1] == "":
        block.pop()
    block.append(BLOCK_END)

    while outside and not outside[-1].strip():
        outside.pop()
    out_lines = outside + ([""] if outside else []) + block
    text = nl.join(out_lines) + nl
    _parse_check(text)
    return text


def _parse_check(text):
    """On Python >= 3.11, prove the rendered file is valid TOML."""
    try:
        import tomllib
    except ImportError:  # 3.9 / 3.10: the closed generator + scan is the guard
        return
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"config.toml would not be valid TOML ({exc}); not writing it.")


# ---------------------------------------------------------------------------
# Plan / apply
# ---------------------------------------------------------------------------

def plan_preparation(home, repo_root, platform):
    """Return the ordered preparation actions. Read-only.

    Each action is a dict: {"action": "mkdir"|"write"|"keep", "path": Path,
    "content": bytes|None}. Raises ProfileError (nothing written) when the
    home holds an unfamiliar rule, extra rule files, or a conflicting config.
    """
    home = Path(home)
    rules_dir = home / "rules"
    rule_path = rules_dir / RULE_FILE
    config_path = home / "config.toml"
    actions = []

    for d in (home, rules_dir):
        if d.exists() and not d.is_dir():
            raise ProfileError(f"{d} exists and is not a directory.")
        actions.append({"action": "keep" if d.is_dir() else "mkdir", "path": d, "content": None})

    if rules_dir.is_dir():
        extra = sorted(p.name for p in rules_dir.iterdir() if p.name != RULE_FILE)
        if extra:
            raise ProfileError(
                f"{rules_dir} contains files Gator did not write ({', '.join(extra)}). "
                "Codex may load them and widen the allow-list.")
    if rule_path.exists():
        current = rule_path.read_bytes()
        if current == RULE_BYTES:
            actions.append({"action": "keep", "path": rule_path, "content": None})
        elif current in KNOWN_GENERATED_RULES:
            actions.append({"action": "write", "path": rule_path, "content": RULE_BYTES})
        else:
            raise ProfileError(
                f"{rule_path} is not the rule Gator generates (unfamiliar or edited rule). "
                "Gator will not overwrite a permission rule it does not recognize.")
    else:
        actions.append({"action": "write", "path": rule_path, "content": RULE_BYTES})

    existing = config_path.read_bytes() if config_path.exists() else b""
    if existing.startswith(_BOM):  # Codex expects UTF-8 without a BOM
        existing = existing[len(_BOM):]
    try:
        existing_text = existing.decode("utf-8")
    except UnicodeDecodeError:
        raise ProfileError(f"{config_path} is not UTF-8; not editing it.")
    new = render_config(existing_text, trust_key(repo_root, platform), platform).encode("utf-8")
    if config_path.exists() and config_path.read_bytes() == new:
        actions.append({"action": "keep", "path": config_path, "content": None})
    else:
        actions.append({"action": "write", "path": config_path, "content": new})
    return actions


def apply_preparation(actions):
    """Execute exactly the planned actions (UTF-8 bytes, atomic replace)."""
    for act in actions:
        path = act["path"]
        if act["action"] == "mkdir":
            path.mkdir(parents=True, exist_ok=True)
        elif act["action"] == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".gator-tmp")
            tmp.write_bytes(act["content"])
            os.replace(tmp, path)


def render_dry_run(actions, home, repo_root, platform):
    """Human-readable preview of what a real launch would do. Pure."""
    key = trust_key(repo_root, platform)
    lines = [
        "  gator loop codex (dry run) — nothing is written or launched",
        "",
        f"  dedicated CODEX_HOME: {home}",
        f"  repository:           {repo_root}",
        f"  trust entry:          [projects.'{key}'] trust_level = \"trusted\"",
        "",
        "  planned actions:",
    ]
    for act in actions:
        lines.append(f"    {act['action']:<5} {act['path']}")
    lines += ["", f"  rule ({Path(home) / 'rules' / RULE_FILE}):", ""]
    lines += [f"    {l}" for l in RULE_TEXT.splitlines()]
    lines += [
        "",
        f"  launch: codex (from PATH), cwd={repo_root}, CODEX_HOME={home} for that process only",
        "  remove later by deleting the dedicated home directory.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Verification and launch
# ---------------------------------------------------------------------------

def child_env(env, home):
    """A copy of `env` with CODEX_HOME set. The caller's mapping is untouched."""
    out = dict(env)
    out["CODEX_HOME"] = str(home)
    return out


def codex_version(codex, run):
    """Return the `x.y.z` Codex version string, or None if it cannot be read."""
    try:
        res = run([codex, "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+\.\d+\.\d+)", (res.stdout or "") + (res.stderr or ""))
    return m.group(1) if m else None


def check_policy(codex, rules_path, env, run):
    """Prove the rule boundary with `codex execpolicy check`, or raise.

    `gator loop status` must be allowed; `git write-tree` and `gator loop end`
    must match no rule. Any other result, a non-zero exit, or unparseable
    output raises ProfileError before launch.
    """
    for argv, expected in POLICY_PROBES:
        cmd = [codex, "execpolicy", "check", "--rules", str(rules_path), "--", *argv]
        shown = " ".join(argv)
        try:
            res = run(cmd, capture_output=True, text=True, env=env, timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProfileError(f"`codex execpolicy check` could not run for `{shown}`: {exc}")
        if res.returncode != 0:
            raise ProfileError(
                f"`codex execpolicy check` failed for `{shown}` (exit {res.returncode}): "
                f"{(res.stderr or res.stdout or '').strip()[:300]}")
        try:
            data = json.loads(res.stdout)
        except (TypeError, ValueError):
            raise ProfileError(f"`codex execpolicy check` printed unexpected output for `{shown}`.")
        if expected == "allow":
            ok = isinstance(data, dict) and data.get("decision") == "allow"
        else:
            ok = isinstance(data, dict) and data.get("matchedRules") == []
        if not ok:
            raise ProfileError(
                f"Rule boundary check failed: `{shown}` should be "
                f"{'allowed' if expected == 'allow' else 'unmatched'}, got {res.stdout.strip()[:300]}")


def launch(codex, repo_root, env, run):
    """Run interactive Codex with `env` (already holding CODEX_HOME). Returns its exit code."""
    return run([codex], cwd=str(repo_root), env=env).returncode


def main(args, *, env=None, platform=None, which=shutil.which, run=subprocess.run,
         cwd=None, tempdir=None):
    """`gator loop codex [--dry-run] [--home PATH]`. Returns an exit code."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    try:
        from gator_core import find_gator_root
        repo_root = find_gator_root(cwd)
        if repo_root is None:
            raise ProfileError("Not inside a Gator-governed repository (no .gator/ found).")
        if platform != "win32":
            raise ProfileError(
                f"`gator loop codex` is verified only on Windows; this platform is {platform}. "
                "Use the manual setup and its validation checklist.")
        home = validate_home(getattr(args, "home", None) or default_home(), repo_root, env,
                             tempdir=tempdir)
        actions = plan_preparation(home, repo_root, platform)
        if getattr(args, "dry_run", False):
            sys.stdout.write(render_dry_run(actions, home, repo_root, platform))
            return 0

        codex = which("codex")
        if not codex:
            raise ProfileError("`codex` was not found on PATH. Install Codex CLI first.")
        version = codex_version(codex, run)
        if version != VERIFIED_CODEX_VERSION:
            print(f"  warning: Codex {version or 'version unknown'} is unverified "
                  f"(verified: {VERIFIED_CODEX_VERSION}); the rule boundary is re-checked below.")

        apply_preparation(actions)
        launch_env = child_env(env, home)
        check_policy(codex, home / "rules" / RULE_FILE, launch_env, run)
    except ProfileError as exc:
        print(f"  gator loop codex: {exc}", file=sys.stderr)
        return 1

    key = trust_key(repo_root, platform)
    print(f"  dedicated CODEX_HOME: {home}")
    print(f"  trusted repository:   [projects.'{key}']")
    print("  rule boundary:        verified (status allowed; git write-tree and loop end unmatched)")
    print(TRUST_WARNING)
    auth = home / "auth.json"
    if not auth.exists():
        print(SIGN_IN_NOTE)
    print("  Next: run `gator loop join` with your role prompt, then optionally `/goal`.")
    sys.stdout.flush()

    rc = launch(codex, repo_root, launch_env, run)
    if rc != 0 and not auth.exists():
        print(f"  Codex exited ({rc}) without a sign-in for CODEX_HOME={home}.", file=sys.stderr)
        print("  Recovery: in a new terminal, set CODEX_HOME to that path for that terminal only "
              "and run `codex login`, then rerun `gator loop codex`.", file=sys.stderr)
    return rc
