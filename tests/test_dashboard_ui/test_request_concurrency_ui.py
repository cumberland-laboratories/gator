"""Browser-level proof that a slow listing no longer blocks a document
(threaded-server plan, checkpoint 4; #70 head-of-line blocking).

The dashboard process runs with the debug files gate
(`GATOR_DASHBOARD_DEBUG_FILES_GATE`): while the gate file is absent, every
live `/files` listing is held server-side. Returning to a repository whose
tree is cached starts a background `/files` freshness check; with the
single-request server, the selected HTML document waited behind it. With
the threaded server the document frame loads while the listing is held.
"""

import os

import pytest

from ._harness import build_dashboard_fleet

GATE_VAR = "GATOR_DASHBOARD_DEBUG_FILES_GATE"


@pytest.fixture(scope="module")
def gated_fleet(tmp_path_factory):
    gate = tmp_path_factory.mktemp("files_gate") / "open"
    gate.write_text("open", encoding="utf-8")
    previous = os.environ.get(GATE_VAR)
    os.environ[GATE_VAR] = str(gate)
    try:
        builder = build_dashboard_fleet(
            tmp_path_factory, extra_registry_size=0, debug=True)
        fleet = next(builder)
    finally:
        if previous is None:
            os.environ.pop(GATE_VAR, None)
        else:
            os.environ[GATE_VAR] = previous
    yield {**fleet, "gate": gate}
    gate.write_text("open", encoding="utf-8")
    try:
        next(builder)
    except StopIteration:
        pass


def _origin(fleet):
    return fleet["url"].rstrip("/") + "/"


def _keys(page, fleet):
    data = page.request.get(_origin(fleet) + "api/data").json()
    return {r["name"]: r.get("repo_key") for r in (data.get("repos") or [])}


def _nav(page, name, key):
    page.evaluate("([n, k]) => window.gatorNavToRepo(n, k)", [name, key])


def _wait_repo(page, name, key):
    page.wait_for_function(
        "([n, k]) => { const s = window.__gator_debug && window.__gator_debug.sidebar;"
        " return !!s && s.repoName === n && s.repoKey === k && !!s.selectedFile"
        " && !!document.querySelector('#repo-file-list .repo-file-item'); }",
        arg=[name, key], timeout=15000)


def test_document_loads_while_the_listing_is_held(page, gated_fleet):
    fleet = gated_fleet
    page.goto(_origin(fleet), wait_until="load")
    keys = _keys(page, fleet)
    _nav(page, "alpha", keys["alpha"])
    _wait_repo(page, "alpha", keys["alpha"])

    # Let the default document finish loading first, so its late response
    # cannot replace the HTML frame selected below.
    page.wait_for_function(
        "() => { const c = document.querySelector('#repo-file-content');"
        " return !!c && c.innerText.trim() !== '' && !/^Loading/.test(c.innerText.trim()); }",
        timeout=15000)

    # Select alpha's plain HTML fixture (the document the HTML preview
    # tests use; shipped blueprint templates render differently).
    html_path = "blueprints/plain.html"
    assert page.evaluate("""p => !!document.querySelector(
        `#repo-file-list .repo-file-item[data-path="${p}"]`)""", html_path),         "the alpha fixture needs blueprints/plain.html"
    page.evaluate("""p => {
        const item = document.querySelector(`#repo-file-list .repo-file-item[data-path="${p}"]`);
        for (let dir = item.closest('.repo-tree-children'); dir;
             dir = dir.parentElement && dir.parentElement.closest('.repo-tree-children')) {
            if (dir.style.display === 'none' && dir.previousElementSibling)
                dir.previousElementSibling.click();
        }
        item.click();
    }""", html_path)
    page.wait_for_function(
        "p => window.__gator_debug.sidebar.selectedFile === p", arg=html_path,
        timeout=10000)
    page.wait_for_selector("iframe.repo-iframe", timeout=10000)

    _nav(page, "beta", keys["beta"])
    _wait_repo(page, "beta", keys["beta"])

    # Close the gate: from now on every live listing is held server-side.
    fleet["gate"].unlink()
    listing_responses = []
    page.on("response", lambda r: listing_responses.append(r.url)
            if "/api/repo/alpha/files" in r.url else None)

    with page.expect_request(lambda r: "/api/repo/alpha/files" in r.url,
                             timeout=10000):
        with page.expect_response(
                lambda r: "/api/repo/alpha/raw/" in r.url and html_path in r.url,
                timeout=8000) as raw:
            _nav(page, "alpha", keys["alpha"])
    assert raw.value.status == 200
    handle = page.locator("iframe.repo-iframe").element_handle()
    frame = handle.content_frame()
    assert frame is not None
    frame.wait_for_load_state("load", timeout=5000)
    assert listing_responses == [], (
        "the document should load while alpha's listing is still held")

    # Open the gate: the held freshness check completes.
    with page.expect_response(lambda r: "/api/repo/alpha/files" in r.url,
                              timeout=35000) as listing:
        fleet["gate"].write_text("open", encoding="utf-8")
    assert listing.value.status == 200
