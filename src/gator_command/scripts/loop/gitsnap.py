"""
Git snapshot helper for coding-mode loops (#41).

Owns: ``snapshot(worktree_root, base_head)`` — the single typed source of
raw Git facts a coding loop binds to: worktree root, current HEAD and its
tree, detached state, the staged tree (``git write-tree``), changed paths
against the captured base, and unstaged/untracked residue.

Facts are RAW: no path filtering or normalization. The staged-tree OID is
the review authority; prose never substitutes for it.

Failure is explicit and never yields a misleading binding: the result is
``{"ok": False, "error": <code>, "detail": <text>}`` with ``error`` one of
``git_unavailable``, ``not_a_repo``, ``bare``, ``unborn``, ``conflict``,
``bad_base``, ``git_busy``, ``git_error``.

Side effect (documented): ``git write-tree`` writes tree objects for the
current index into the object database. They are ordinary unreferenced
objects (reclaimed by ``git gc``); refs, the index and the worktree are
never touched.
"""

import subprocess
import time
from pathlib import Path

SNAPSHOT_SCHEMA = "gator-loop-gitsnap-v1"

# Persisted path lists are capped so session.json stays bounded; the
# staged-tree OID (not the list) is the binding. Truncation is counted.
MAX_PATHS = 1000

ERROR_CODES = frozenset({
    "git_unavailable", "not_a_repo", "bare", "unborn", "conflict",
    "bad_base", "git_busy", "git_error",
})

_BUSY_MARKERS = ("index.lock", "Unable to create", "unable to create")
_BUSY_RETRY_DELAY = 0.2


class _GitError(Exception):
    def __init__(self, code, detail=""):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _run(args, cwd):
    """Run git; returns CompletedProcess with bytes output. Test seam."""
    return subprocess.run(["git"] + list(args), cwd=str(cwd),
                          capture_output=True)


def _invoke(args, cwd):
    """Run git, classifying launch failures precisely.

    ``git_unavailable`` is reserved for failure to execute Git itself. A
    bad working directory (deleted, or not a directory) is ``not_a_repo``;
    any other OS-level failure is ``git_error``.
    """
    try:
        return _run(args, cwd)
    except (FileNotFoundError, NotADirectoryError) as exc:
        if not Path(cwd).is_dir():
            raise _GitError("not_a_repo", f"not a directory: {cwd}")
        raise _GitError("git_unavailable", str(exc))
    except PermissionError as exc:
        if not Path(cwd).is_dir():
            raise _GitError("not_a_repo", f"not a directory: {cwd}")
        raise _GitError("git_unavailable", str(exc))
    except OSError as exc:
        raise _GitError("git_error", str(exc))


def _git(args, cwd, *, retry_busy=False):
    r = _invoke(args, cwd)
    if r.returncode != 0 and retry_busy and _is_busy(r):
        time.sleep(_BUSY_RETRY_DELAY)
        r = _invoke(args, cwd)
        if r.returncode != 0 and _is_busy(r):
            raise _GitError("git_busy", _err(r))
    return r


def _is_busy(r):
    msg = _err(r)
    return any(m in msg for m in _BUSY_MARKERS)


def _err(r):
    return (r.stderr or b"").decode("utf-8", "replace").strip()


def _out(r):
    return (r.stdout or b"").decode("utf-8", "replace").strip()


def _split_z(raw):
    return [p for p in (raw or b"").decode("utf-8", "replace").split("\0")
            if p != ""]


def _parse_name_status_z(raw):
    """``git diff --name-status -z`` -> [{status, path[, old_path]}]."""
    tokens = _split_z(raw)
    out = []
    i = 0
    while i < len(tokens):
        status = tokens[i]
        if status[:1] in ("R", "C"):
            if i + 2 >= len(tokens):
                raise _GitError("git_error", "malformed rename record")
            out.append({"status": status[:1], "old_path": tokens[i + 1],
                        "path": tokens[i + 2]})
            i += 3
        else:
            if i + 1 >= len(tokens):
                raise _GitError("git_error", "malformed name-status record")
            out.append({"status": status[:1], "path": tokens[i + 1]})
            i += 2
    return out


def _cap(items):
    if len(items) <= MAX_PATHS:
        return items, 0
    return items[:MAX_PATHS], len(items) - MAX_PATHS


def snapshot(worktree_root, base_head=None):
    """Capture raw Git facts for a coding loop.

    ``worktree_root``: any path inside the target worktree.
    ``base_head``: the commit captured at coding-loop start. When given,
    ``changed_paths`` is the staged diff against it and ``base_tree`` is
    its tree; when None (capturing the base itself) the diff is against
    HEAD.

    Returns ``{"ok": True, ...facts}`` or ``{"ok": False, "error", "detail"}``
    — never raises for Git conditions.
    """
    try:
        return _snapshot(Path(worktree_root), base_head)
    except _GitError as exc:
        return {"schema": SNAPSHOT_SCHEMA, "ok": False, "error": exc.code,
                "detail": exc.detail[:500]}


def _snapshot(start, base_head):
    if not start.exists():
        raise _GitError("not_a_repo", f"path does not exist: {start}")
    if not start.is_dir():
        # A file (or other non-directory) is a caller input error, never
        # an infrastructure failure: reject before any Git invocation.
        raise _GitError("not_a_repo", f"not a directory: {start}")

    r = _git(["rev-parse", "--is-bare-repository"], start)
    if r.returncode != 0:
        raise _GitError("not_a_repo", _err(r))
    if _out(r) == "true":
        raise _GitError("bare", "bare repositories have no worktree")

    r = _git(["rev-parse", "--show-toplevel"], start)
    if r.returncode != 0:
        raise _GitError("not_a_repo", _err(r))
    root = Path(_out(r))

    r = _git(["rev-parse", "--verify", "-q", "HEAD^{commit}"], root)
    if r.returncode != 0:
        raise _GitError("unborn", "HEAD has no commit yet")
    current_head = _out(r)

    head_tree = _out(_git(["rev-parse", "HEAD^{tree}"], root))

    r = _git(["symbolic-ref", "-q", "HEAD"], root)
    detached = r.returncode != 0
    branch = None if detached else _out(r)

    r = _git(["ls-files", "--unmerged", "-z"], root)
    if r.returncode == 0 and _split_z(r.stdout):
        raise _GitError("conflict", "the index has unmerged entries")

    r = _git(["write-tree"], root, retry_busy=True)
    if r.returncode != 0:
        msg = _err(r)
        if "unmerged" in msg.lower():
            raise _GitError("conflict", msg)
        raise _GitError("git_error", msg)
    staged_tree = _out(r)

    base_tree = None
    if base_head is not None:
        r = _git(["rev-parse", "--verify", "-q", f"{base_head}^{{commit}}"],
                 root)
        if r.returncode != 0:
            raise _GitError("bad_base", f"base commit not found: {base_head}")
        base_head = _out(r)
        base_tree = _out(_git(["rev-parse", f"{base_head}^{{tree}}"], root))
        diff_against = base_head
    else:
        diff_against = current_head

    r = _git(["diff", "--cached", "--name-status", "-z", "-M",
              diff_against], root, retry_busy=True)
    if r.returncode != 0:
        raise _GitError("git_error", _err(r))
    changed, changed_trunc = _cap(_parse_name_status_z(r.stdout))

    r = _git(["diff", "--name-only", "-z"], root, retry_busy=True)
    if r.returncode != 0:
        raise _GitError("git_error", _err(r))
    unstaged = set(_split_z(r.stdout))
    r = _git(["ls-files", "--others", "--exclude-standard", "-z"], root)
    if r.returncode != 0:
        raise _GitError("git_error", _err(r))
    unstaged.update(_split_z(r.stdout))
    unstaged_list, unstaged_trunc = _cap(sorted(unstaged))

    return {
        "schema": SNAPSHOT_SCHEMA,
        "ok": True,
        "worktree_root": str(root),
        "current_head": current_head,
        "head_tree": head_tree,
        "detached": detached,
        "branch": branch,
        "staged_tree": staged_tree,
        "base_head": base_head,
        "base_tree": base_tree,
        "changed_paths": changed,
        "changed_truncated": changed_trunc,
        "unstaged_paths": unstaged_list,
        "unstaged_truncated": unstaged_trunc,
    }


def diff_trees(worktree_root, from_tree, to_tree):
    """Changed paths between two tree OIDs (#55 checkpoint diff).

    ``git diff-tree -r -z -M --name-status`` is a pure object-database
    read: it takes no index lock and never touches refs, the index or the
    worktree. Returns ``{"ok": True, "changed_paths", "changed_truncated"}``
    (the same record shape and cap as ``snapshot``) or
    ``{"ok": False, "error", "detail"}`` — never raises for Git conditions.
    """
    try:
        root = Path(worktree_root)
        if not root.is_dir():
            raise _GitError("not_a_repo", f"not a directory: {root}")
        r = _git(["diff-tree", "-r", "-z", "-M", "--name-status",
                  str(from_tree), str(to_tree)], root)
        if r.returncode != 0:
            raise _GitError("git_error", _err(r))
        changed, trunc = _cap(_parse_name_status_z(r.stdout))
        return {"ok": True, "changed_paths": changed,
                "changed_truncated": trunc}
    except _GitError as exc:
        return {"ok": False, "error": exc.code, "detail": exc.detail[:500]}
