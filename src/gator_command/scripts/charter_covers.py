"""The shared charter `Covers` matcher (grammar `gator-covers-v1`).

One closed grammar answers "does this `Covers` entry name this file?" for
every producer that has moved onto it: the charter verifier and the
Dashboard charter sync check (#88). Other producers keep their own matching
until a later decision moves them.

Grammar, over normalized repo-relative POSIX paths:

- a path or entry is normalized by turning `\\` into `/` and removing a
  leading `./`; matching is case-sensitive on every OS;
- an empty entry, an absolute entry (leading `/` or a drive letter) or an
  entry with a `..` segment matches nothing;
- an entry containing `*`, `?` or `[` is an `fnmatchcase` pattern over the
  full path, never the basename alone (`*` also crosses `/`);
- an entry ending in `/` is a directory prefix;
- anything else matches only the identical path.

Standard library only; safe to import from scripts run by filename.
"""

import fnmatch
import re

GRAMMAR = "gator-covers-v1"

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def normalize_path(path):
    """Repo-relative POSIX form of `path`: `\\` to `/`, no leading `./`."""
    path = str(path).strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _normalize_entry(entry):
    """The normalized entry, or None when the grammar matches nothing for it."""
    entry = normalize_path(entry)
    if not entry or entry.startswith("/") or _DRIVE_RE.match(entry):
        return None
    if ".." in entry.rstrip("/").split("/"):
        return None
    return entry


def covers_match(path, entry):
    """True when repo-relative `path` is named by one `Covers` entry."""
    entry = _normalize_entry(entry)
    if entry is None:
        return False
    path = normalize_path(path)
    if any(c in entry for c in "*?["):
        return fnmatch.fnmatchcase(path, entry)
    if entry.endswith("/"):
        return path.startswith(entry)
    return path == entry


def covering_charters(path, charters):
    """Names of the charters whose `covers` name `path`, in `charters` order.

    `charters` is an iterable of mappings with `name` and `covers`.
    """
    return [c["name"] for c in charters
            if any(covers_match(path, e) for e in c["covers"])]


def coverage_index(files, charters):
    """`{file: [charter names]}` for every file in `files` some charter covers.

    Uncovered files are absent, so `file in index` is the coverage test.
    """
    charters = list(charters)
    index = {}
    for f in files:
        names = covering_charters(f, charters)
        if names:
            index[f] = names
    return index
