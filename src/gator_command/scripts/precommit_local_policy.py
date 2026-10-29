"""Machine-local commit policy for one checkout (fleet commit-policy slice).

The commit policy is an engineer's own choice on their own machine. It lives
in Git's private area for this clone, never in the repository:

    $(git rev-parse --git-path gator-commit-policy.json)

so it is never staged, never pushed, and one engineer can never relax the
checks for another. Absent, unreadable or invalid means **strict** (the team
default). Only ``strict`` and ``warn`` exist locally; ``off`` is not offered.
When Enterprise manages the repository, its hook mode decides and this file
is ignored.

The tracked ``.gator/config.json`` ``enforcement_level`` is no longer read
for the policy: a committed relaxation would change every engineer's
checks. ``tracked_relaxation()`` reports it so the hook can say it is
ignored.

Byte-identical copies: ``templates/gator-starter/scripts/`` (the hook,
``gator enforce``) and ``scripts/`` (the Dashboard); pinned by
tests/test_local_commit_policy.py.
"""

import json
import os
import subprocess
from pathlib import Path

POLICY_FILENAME = "gator-commit-policy.json"
POLICY_SCHEMA = "gator-commit-policy-v1"
LOCAL_LEVELS = ("strict", "warn")
DEFAULT_LEVEL = "strict"


class LocalPolicyError(Exception):
    """The per-clone policy path cannot be resolved or written."""


def policy_path(repo_root):
    """Absolute path of this clone's policy file (not created)."""
    repo_root = Path(repo_root)
    try:
        r = subprocess.run(["git", "rev-parse", "--git-path", POLICY_FILENAME],
                           cwd=str(repo_root), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalPolicyError(f"cannot run git in {repo_root}: {exc}")
    out = (r.stdout or "").strip()
    if r.returncode != 0 or not out:
        raise LocalPolicyError(f"cannot resolve the Git private path in {repo_root}")
    p = Path(out)
    return p if p.is_absolute() else (repo_root / p)


def enterprise_managed(repo_root):
    """True when Enterprise manages the repository.

    Same semantics as ``gator_core.is_enterprise_active()`` (the starter
    scripts do not ship that helper): ``.gator/enterprise.json`` exists,
    parses as an object, and has ``enabled: true``. Pinned equal by
    tests/test_local_commit_policy.py.
    """
    marker = Path(repo_root) / ".gator" / "enterprise.json"
    if not marker.exists():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    return isinstance(payload, dict) and payload.get("enabled") is True


def read_level(repo_root):
    """This clone's level: ``strict`` or ``warn``. Fails closed to strict."""
    if enterprise_managed(repo_root):
        return DEFAULT_LEVEL
    try:
        data = json.loads(policy_path(repo_root).read_text(encoding="utf-8"))
    except (LocalPolicyError, OSError, ValueError):
        return DEFAULT_LEVEL
    level = data.get("level") if isinstance(data, dict) else None
    return level if level in LOCAL_LEVELS else DEFAULT_LEVEL


def write_level(repo_root, level):
    """Set this clone's level. ``strict`` removes the file. Returns the path.

    Raises ValueError for a level outside LOCAL_LEVELS, LocalPolicyError when
    Enterprise manages the repository or the path cannot be resolved.
    """
    if level not in LOCAL_LEVELS:
        raise ValueError(f"level must be one of {', '.join(LOCAL_LEVELS)}")
    if enterprise_managed(repo_root):
        raise LocalPolicyError(
            "Enterprise manages this repository's commit policy; it cannot be set locally.")
    path = policy_path(repo_root)
    if level == DEFAULT_LEVEL:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"schema": POLICY_SCHEMA, "level": level}, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return path


def tracked_relaxation(gator_dir):
    """The non-strict ``enforcement_level`` committed in config.json, or None.

    Reported only so the hook can say it is ignored; never applied.
    """
    try:
        config = json.loads((Path(gator_dir) / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    level = config.get("enforcement_level") if isinstance(config, dict) else None
    return level if level in ("warn", "off") else None
