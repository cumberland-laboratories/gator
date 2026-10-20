"""
Live candidate seam (#70 listing cost, checkpoint 1).

In-process pins for `_iter_live_candidates()` /
`_live_namespace_bases()` / `_scanner_target()` in
`gator-dashboard.py`: the seam yields exactly what the listing
policy admits, never yields a path through or beneath a link, and
its per-survivor F2 proof (resolve-equality, Architect decision-1)
rejects a link swapped in after the scan on its own.
"""

import os
import subprocess
import sys

import pytest


NAMESPACES = (".gator", "gator-command", "")


def _write(path, text="x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_dir_link(link, target):
    """Junction on Windows, symlink on POSIX. Skips if refused."""
    if sys.platform == "win32":
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True)
        if r.returncode != 0:
            pytest.skip(f"mklink /J failed (permission?): {r.stderr!r}")
        return
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation failed: {exc}")


def _make_file_link(link, target):
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"file symlink creation failed: {exc}")


def _remove_link(link):
    """Remove the link only, never its target."""
    try:
        if sys.platform == "win32" and link.is_dir():
            os.rmdir(str(link))
        else:
            os.unlink(str(link))
    except OSError:
        pass


def _logicals(dashboard, repo):
    return [c.logical for c in dashboard._iter_live_candidates(
        str(repo), NAMESPACES)]


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    _write(root / ".gator" / "control.md")
    return root


# ── 1. The seam does not change the listing policy ──────────────

def test_candidates_are_authorized_and_canonical(
        dashboard_module, repo):
    d = dashboard_module
    for rel in (
            ".gator/artifacts/a.md",
            ".gator/notes.json",
            ".gator/config.yaml",
            ".gator/script.py",                    # not governance text
            ".gator/sessions/_active/t.json",      # _active
            ".gator/.includes/p.md",               # dot-dir
            ".gator/override-request.json",        # denied basename
            ".gator/loops/l/.tokens.json",         # dot-file
            ".gator/node_modules/n.md",            # denied dir
            "gator-command/doc.md",
            "gator-command/sub/deep/d.json",
            "README.md",
            "src/app.py",
            "src/key.pem",                         # denied suffix
            "build/out.md",                        # denied dir
            ".git/HEAD.md",                        # dot-dir
    ):
        _write(repo / rel)

    expected = set()
    for ns in NAMESPACES:
        root = repo / ns if ns else repo
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                disk_rel = os.path.relpath(
                    os.path.join(dirpath, name), root).replace(os.sep, "/")
                logical = d._canonical_logical_for(ns, disk_rel)
                lp = d.parse_logical_path(logical)
                if lp and d.is_browsable(lp.namespace_root, lp.disk_rel,
                                         "files"):
                    expected.add(logical)

    candidates = list(d._iter_live_candidates(str(repo), NAMESPACES))
    got = [c.logical for c in candidates]
    assert len(got) == len(set(got)), got
    assert set(got) == expected
    # Guard against a vacuous oracle.
    assert {"control.md", "artifacts/a.md", "notes.json", "config.yaml",
            "gator-command/doc.md", "gator-command/sub/deep/d.json",
            "source/README.md", "source/src/app.py"} <= set(got)

    repo_r = repo.resolve(strict=True)
    for c in candidates:
        base = repo_r / c.namespace_root if c.namespace_root else repo_r
        lexical = base.joinpath(*c.disk_rel.split("/"))
        assert c.target == lexical
        assert c.entry.name == c.disk_rel.rsplit("/", 1)[-1]
        assert c.logical == d._canonical_logical_for(
            c.namespace_root, c.disk_rel)


# ── 2. No candidate through or beneath a link ───────────────────

def _case_in_repo_alias(repo, tmp_path):
    _write(repo / ".gator" / "sessions" / "_active" / "token.json")
    link = repo / "public"
    _make_dir_link(link, repo / ".gator" / "sessions" / "_active")
    return link, ("source/public/",)


def _case_external_dir(repo, tmp_path):
    external = tmp_path / "external"
    _write(external / "smuggled.md")
    link = repo / ".gator" / "linked"
    _make_dir_link(link, external)
    return link, ("linked/",)


def _case_file_link(repo, tmp_path):
    external = tmp_path / "external-file.md"
    _write(external)
    link = repo / ".gator" / "link.md"
    _make_file_link(link, external)
    return link, ("link.md",)


def _case_namespace_root_link(repo, tmp_path):
    _write(repo / "docs" / "doc.md")
    link = repo / "gator-command"
    _make_dir_link(link, repo / "docs")
    return link, ("gator-command/",)


@pytest.mark.parametrize("make_case", [
    _case_in_repo_alias,
    _case_external_dir,
    _case_file_link,
    _case_namespace_root_link,
], ids=["in-repo-alias", "external-dir", "file-link",
        "namespace-root-link"])
def test_candidates_exclude_aliases(
        dashboard_module, repo, tmp_path, make_case):
    link, forbidden_prefixes = make_case(repo, tmp_path)
    try:
        got = _logicals(dashboard_module, repo)
    finally:
        _remove_link(link)

    assert "control.md" in got, got
    for logical in got:
        for prefix in forbidden_prefixes:
            assert not logical.startswith(prefix), (
                f"link leaked a candidate: {logical}")


# ── 3. F2 backstop works without the scanner ────────────────────

@pytest.mark.parametrize("target_kind", ["in-repo", "external"])
def test_scanner_target_rejects_link_created_after_scan(
        dashboard_module, repo, tmp_path, target_kind):
    d = dashboard_module
    _write(repo / ".gator" / "dir" / "file.md")
    base_r = (repo / ".gator").resolve(strict=True)
    lexical = base_r / "dir" / "file.md"
    assert d._scanner_target(base_r, "dir/file.md") == lexical

    # Replace `dir` with a link to a directory holding the same name.
    if target_kind == "in-repo":
        (repo / ".gator" / "dir").rename(repo / ".gator" / "dir-real")
        target = repo / ".gator" / "dir-real"
    else:
        target = tmp_path / "elsewhere"
        _write(target / "file.md")
        (repo / ".gator" / "dir" / "file.md").unlink()
        (repo / ".gator" / "dir").rmdir()
    link = repo / ".gator" / "dir"
    _make_dir_link(link, target)
    try:
        assert d._scanner_target(base_r, "dir/file.md") is None
    finally:
        _remove_link(link)


# ── 4. Listing containment cost does not grow with depth ────────

class _RecordingShim:
    """Minimal handler surface for `_handle_files` (the slice-3
    pattern): records the status and the JSON body.
    """

    def __init__(self):
        import io
        self.wfile = io.BytesIO()
        self.status_calls = []

    def send_response(self, status, message=None):
        self.status_calls.append(status)

    def send_header(self, name, value):
        pass

    def end_headers(self):
        pass


FILES_PER_NAMESPACE = 3


def _deep_repo(root, depth):
    """Same file count in every namespace; each file sits `depth`
    segments below its namespace root.
    """
    dirs = [f"d{i}" for i in range(depth - 1)]
    for ns in NAMESPACES:
        base = root / ns if ns else root
        for i in range(FILES_PER_NAMESPACE):
            _write(base.joinpath(*dirs, f"f{i}.md"))


def _measure_listing(d, monkeypatch, repo):
    import json
    import pathlib

    counts = {"resolve": 0, "probe": 0, "contained": 0}
    orig_resolve = pathlib.Path.resolve
    orig_probe = d._is_reparse_point
    orig_contained = d._contained_repo_path

    def resolve(self, *a, **kw):
        counts["resolve"] += 1
        return orig_resolve(self, *a, **kw)

    def probe(x):
        if not isinstance(x, os.DirEntry):
            counts["probe"] += 1
        return orig_probe(x)

    def contained(*a, **kw):
        counts["contained"] += 1
        return orig_contained(*a, **kw)

    monkeypatch.setattr(d, "_resolve_repo_path",
                        lambda *a, **kw: str(repo))
    shim = _RecordingShim()
    for name in ("_send_json", "_send_json_error", "_handle_files"):
        method = getattr(d.DashboardHandler, name)
        object.__setattr__(shim, name,
                           method.__get__(shim, d.DashboardHandler))
    req = d.Request(endpoint="files", repo_name="alpha",
                    logical_path=None, version_present=False,
                    version_value="", query={})
    with monkeypatch.context() as m:
        m.setattr(pathlib.Path, "resolve", resolve)
        m.setattr(d, "_is_reparse_point", probe)
        m.setattr(d, "_contained_repo_path", contained)
        shim._handle_files(req)
    assert shim.status_calls == [200]
    files = json.loads(shim.wfile.getvalue())["files"]
    return counts, len(files)


def test_listing_containment_cost_is_independent_of_depth(
        dashboard_module, monkeypatch, tmp_path):
    measured = {}
    for depth in (1, 6):
        repo = tmp_path / f"depth{depth}"
        _deep_repo(repo, depth)
        measured[depth] = _measure_listing(
            dashboard_module, monkeypatch, repo)

    for depth, (counts, survivors) in measured.items():
        assert survivors == FILES_PER_NAMESPACE * len(NAMESPACES), depth
        assert counts["contained"] == 0, (depth, counts)
        assert counts["resolve"] <= 1 + 3 + survivors, (depth, counts)
        assert counts["probe"] <= 2, (depth, counts)
    assert measured[1] == measured[6]
