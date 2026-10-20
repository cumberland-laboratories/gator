"""
Search visibility (#70, checkpoint 3).

`/api/repo/<name>/search` takes its candidates only from the live
candidate seam, so it can never be broader than `/files`: it applies
the listing visibility policy, then narrows to governance documents
(`.gator/`, `gator-command/`, `.md`/`.json`). It never acts as an
existence oracle. `search_documents()` keeps its AND/OR/phrase
matching, snippets, 50-result limit and ranking.
"""

import collections
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

import pytest

from ._harness import build_dashboard_fleet


def _get_json(fleet, path):
    url = fleet["url"].rstrip("/") + path
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_dir_link(link, target):
    """Junction on Windows, symlink on POSIX. Returns success."""
    if sys.platform == "win32":
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True)
        return r.returncode == 0
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        return False


def _remove_link(link):
    try:
        if sys.platform == "win32" and link.is_dir():
            os.rmdir(str(link))
        else:
            os.unlink(str(link))
    except OSError:
        pass


# ── Matrix rows ──────────────────────────────────────────────────
# (id, repo, logical path the file would have, listed, searchable).
# Each file carries the marker `svmark-<id>` and nothing else does.

ROWS = [
    ("gator-md", "alpha", "artifacts/sv-gator-md.md", True, True),
    ("gator-json", "alpha", "sv-gator-json.json", True, True),
    ("gc-md", "alpha", "gator-command/sv-gc-md.md", True, True),
    ("gator-yaml", "alpha", "sv-gator-yaml.yaml", True, False),
    ("source-md", "alpha", "source/sv-source-md.md", True, False),
    ("active", "alpha", "sessions/_active/sv-active.json", False, False),
    ("includes", "alpha", ".includes/sv-includes.md", False, False),
    ("node-modules", "alpha", "node_modules/sv-node-modules.md",
     False, False),
    ("override", "alpha", "override-request.json", False, False),
    ("tokens", "alpha", "loops/l/.tokens.json", False, False),
    ("in-repo-alias", "alpha", "aliasdir/sv-in-repo-alias.json",
     False, False),
    ("external-link", "alpha", "extlink/sv-external-link.md",
     False, False),
    ("gc-root-link", "beta", "gator-command/sv-gc-root-link.md",
     False, False),
]

LINK_ROWS = {"in-repo-alias", "external-link", "gc-root-link"}


def _marker(row_id):
    return f"svmark-{row_id}"


def _plant(fleet, tmp_path_factory):
    """Plant every matrix row. Returns (created link rows, cleanup)."""
    alpha = fleet["repos"]["alpha"]["path"]
    beta = fleet["repos"]["beta"]["path"]
    gator = alpha / ".gator"

    plain = {
        "gator-md": gator / "artifacts" / "sv-gator-md.md",
        "gator-json": gator / "sv-gator-json.json",
        "gc-md": alpha / "gator-command" / "sv-gc-md.md",
        "gator-yaml": gator / "sv-gator-yaml.yaml",
        "source-md": alpha / "sv-source-md.md",
        "active": gator / "sessions" / "_active" / "sv-active.json",
        "includes": gator / ".includes" / "sv-includes.md",
        "node-modules": gator / "node_modules" / "sv-node-modules.md",
        "override": gator / "override-request.json",
        "tokens": gator / "loops" / "l" / ".tokens.json",
    }
    for row_id, path in plain.items():
        _write(path, f"{_marker(row_id)}\n")

    created = set()
    links = []

    # In-repo alias into `_active` state.
    _write(gator / "sessions" / "_active" / "sv-in-repo-alias.json",
           f"{_marker('in-repo-alias')}\n")
    if _make_dir_link(gator / "aliasdir", gator / "sessions" / "_active"):
        created.add("in-repo-alias")
        links.append(gator / "aliasdir")

    # Link to a directory outside the repository.
    external = tmp_path_factory.mktemp("search_external")
    _write(external / "sv-external-link.md",
           f"{_marker('external-link')}\n")
    if _make_dir_link(gator / "extlink", external):
        created.add("external-link")
        links.append(gator / "extlink")

    # A `gator-command` namespace root that is itself an in-repo
    # link. The seed has a real `gator-command/`; move it aside and
    # link to it, then restore it on cleanup.
    gc_root = beta / "gator-command"
    gc_real = beta / "gc-real"
    if gc_root.exists():
        gc_root.rename(gc_real)
    _write(gc_real / "sv-gc-root-link.md", f"{_marker('gc-root-link')}\n")
    if _make_dir_link(gc_root, gc_real):
        created.add("gc-root-link")
        links.append(gc_root)

    def cleanup():
        for link in links:
            _remove_link(link)
        if not gc_root.exists():
            gc_real.rename(gc_root)

    return created, cleanup


@pytest.fixture(scope="module")
def search_fleet(tmp_path_factory):
    gen = build_dashboard_fleet(
        tmp_path_factory, extra_registry_size=0, debug=True)
    fleet = next(gen)
    created, cleanup = _plant(fleet, tmp_path_factory)
    fleet["created_links"] = created
    try:
        yield fleet
    finally:
        cleanup()
        try:
            next(gen)
        except StopIteration:
            pass


def _listed(fleet, repo):
    status, data = _get_json(fleet, f"/api/repo/{repo}/files")
    assert status == 200
    return {f["path"] for f in data["files"]}


def _search(fleet, repo, query):
    q = urllib.parse.quote(query)
    return _get_json(fleet, f"/api/repo/{repo}/search?q={q}")


# ── 5. Search/listing visibility matrix ─────────────────────────

@pytest.mark.parametrize(
    "row_id, repo, logical, listed, searchable", ROWS,
    ids=[r[0] for r in ROWS])
def test_search_and_listing_visibility_matrix(
        search_fleet, row_id, repo, logical, listed, searchable):
    if row_id in LINK_ROWS and row_id not in search_fleet["created_links"]:
        pytest.skip("link creation refused on this machine")

    assert (logical in _listed(search_fleet, repo)) is listed

    status, data = _search(search_fleet, repo, _marker(row_id))
    assert status == 200 and "error" not in data, data
    hits = [r["path"] for r in data["results"]]
    assert hits == ([logical] if searchable else []), hits


@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX chmod-0 pattern.")
def test_unreadable_document_is_not_an_oracle(search_fleet):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root reads chmod-0 files")
    path = (search_fleet["repos"]["alpha"]["path"] / ".gator"
            / "sv-unreadable.md")
    _write(path, f"{_marker('unreadable')}\n")
    os.chmod(str(path), 0)
    try:
        status, data = _search(search_fleet, "alpha",
                               _marker("unreadable"))
    finally:
        os.chmod(str(path), 0o644)
    assert status == 200 and data["results"] == [], data


# ── 6. Every search hit is a listing candidate ──────────────────

@pytest.mark.parametrize("repo", ["alpha", "beta"])
def test_every_search_hit_is_a_listing_candidate(search_fleet, repo):
    listed = {p for p in _listed(search_fleet, repo)
              if not p.startswith("source/")
              and os.path.splitext(p)[1].casefold() in (".md", ".json")}
    status, data = _search(search_fleet, repo, "svmark")
    assert status == 200
    hits = {r["path"] for r in data["results"]}
    assert hits <= listed, hits - listed
    if repo == "alpha":
        assert {"artifacts/sv-gator-md.md", "sv-gator-json.json",
                "gator-command/sv-gc-md.md"} <= hits


# ── 7. search_documents semantics ───────────────────────────────

Cand = collections.namedtuple(
    "Cand", "namespace_root disk_rel logical target")


def _cand(tmp_path, ns, disk_rel, text):
    target = (tmp_path / (ns or "src")).joinpath(*disk_rel.split("/"))
    if text is not None:
        _write(target, text)
    logical = {"": "source/", ".gator": "",
               "gator-command": "gator-command/"}[ns] + disk_rel
    return Cand(ns, disk_rel, logical, target)


def test_search_documents_semantics(dashboard_module, tmp_path):
    search = dashboard_module._search_documents

    # Boolean modes.
    both = _cand(tmp_path, ".gator", "both.md", "alpha and beta here")
    one = _cand(tmp_path, ".gator", "one.md", "alpha only")
    phrase = _cand(tmp_path, ".gator", "phrase.md", "see alpha beta")
    docs = [both, one, phrase]
    assert {r["path"] for r in search(docs, "alpha AND beta")} == {
        "both.md", "phrase.md"}
    assert {r["path"] for r in search(docs, "alpha OR beta")} == {
        "both.md", "one.md", "phrase.md"}
    assert [r["path"] for r in search(docs, "alpha beta")] == [
        "phrase.md"]

    # Snippet window and ellipses.
    long_doc = _cand(tmp_path, ".gator", "long.md",
                     "x" * 200 + "needle" + "y" * 200)
    [hit] = search([long_doc], "needle")
    assert hit["snippet"].startswith("...")
    assert hit["snippet"].endswith("...")
    assert "needle" in hit["snippet"]

    # Scope, documented order and the stop after max_results.
    scoped = tmp_path / "scoped"
    shuffled = [
        _cand(scoped, "gator-command", "a.md", "term"),
        _cand(scoped, ".gator", "b.json", "term"),
        _cand(scoped, ".gator", "z.md", "term"),
        _cand(scoped, "", "x.md", "term"),            # source: out of scope
        _cand(scoped, ".gator", "a.md", "term"),
        _cand(scoped, ".gator", "n.yaml", "term"),    # extension out of scope
        _cand(scoped, ".gator", "sub/c.md", "term"),
        _cand(scoped, ".gator", "missing.md", None),  # unreadable: skipped
    ]
    expected = ["a.md", "sub/c.md", "z.md", "b.json", "gator-command/a.md"]
    assert [r["path"] for r in search(shuffled, "term")] == expected
    assert [r["path"] for r in search(shuffled, "term",
                                      max_results=2)] == expected[:2]

    # Ranking by match_count after the cut-off.
    few = _cand(tmp_path / "rank", ".gator", "a.md", "hit")
    many = _cand(tmp_path / "rank", ".gator", "b.md", "hit hit hit")
    ranked = search([few, many], "hit")
    assert [(r["path"], r["match_count"]) for r in ranked] == [
        ("b.md", 3), ("a.md", 1)]
