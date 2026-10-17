"""Repo tree return pins (2026-10-17, dashboard-repo-tree-return-cache).

Each test proves a distinct risk:

- returning to a repository restores its own expanded folders and
  selected file (per-key tree state, one selected-file writer);
- a late listing response from an earlier mount never changes the
  current repository's view or state (mount-generation guard);
- two keys with the same display name never share tree state;
- revisiting repositories leaves exactly one search-box listener.
"""

import json

from ._harness import open_fleet  # noqa: F401  (shared harness import)


def _origin(fleet):
    return fleet["url"].rstrip("/") + "/"


def _keys(page, fleet):
    data = page.request.get(_origin(fleet) + "api/data").json()
    return {r["name"]: r.get("repo_key") for r in (data.get("repos") or [])}


def _sidebar(page):
    return page.evaluate("() => window.__gator_debug.sidebar")


def _nav(page, name, key):
    page.evaluate("([n, k]) => window.gatorNavToRepo(n, k)", [name, key])


def _wait_repo(page, name, key):
    page.wait_for_function(
        "([n, k]) => { const s = window.__gator_debug && window.__gator_debug.sidebar;"
        " return !!s && s.repoName === n && s.repoKey === k && !!s.selectedFile"
        " && !!document.querySelector('#repo-file-list .repo-file-item'); }",
        arg=[name, key], timeout=15000)


def _open_alpha(page, fleet):
    page.goto(_origin(fleet), wait_until="load")
    keys = _keys(page, fleet)
    _nav(page, "alpha", keys["alpha"])
    _wait_repo(page, "alpha", keys["alpha"])
    return keys


def _collapsed_dir_outside(page, path):
    """A collapsed directory that is not an ancestor of `path`."""
    return page.evaluate("""p => {
        for (const b of document.querySelectorAll('#repo-file-list .repo-tree-dir')) {
            const d = b.dataset.dir;
            const open = b.nextElementSibling && b.nextElementSibling.style.display !== 'none';
            if (!open && !p.startsWith(d + '/')) return d;
        }
        return null;
    }""", path)


def _expand(page, directory):
    page.click('#repo-file-list .repo-tree-dir[data-dir="%s"]' % directory)


def test_return_restores_expansion_and_selection(page, dashboard_fleet):
    """alpha → beta → alpha brings back alpha's expanded folder and its
    selected file, instead of resetting to the defaults."""
    keys = _open_alpha(page, dashboard_fleet)
    default = _sidebar(page)["selectedFile"]
    # Open a folder and select a document inside it (not the default).
    first = _collapsed_dir_outside(page, default)
    assert first, "the alpha fixture needs a collapsed folder"
    _expand(page, first)
    chosen = page.evaluate("""([d, dir]) => {
        const items = Array.from(document.querySelectorAll('#repo-file-list .repo-file-item'));
        const other = items.find(i => i.dataset.path !== d && i.offsetParent !== null
            && i.dataset.path.startsWith(dir + '/') && !/\\.html?$/i.test(i.dataset.path));
        return other ? other.dataset.path : null;
    }""", [default, first])
    assert chosen, "the opened folder needs a document"
    page.click('#repo-file-list .repo-file-item[data-path="%s"]' % chosen)
    # Then expand a second folder that is not an ancestor of the selection:
    # only remembered state can bring it back.
    directory = _collapsed_dir_outside(page, chosen)
    assert directory, "the alpha fixture needs a second collapsed folder"
    _expand(page, directory)
    before = _sidebar(page)
    assert directory in before["expandedDirs"] and before["selectedFile"] == chosen

    _nav(page, "beta", keys["beta"])
    _wait_repo(page, "beta", keys["beta"])
    assert directory not in _sidebar(page)["expandedDirs"] or directory == "section:gator"

    _nav(page, "alpha", keys["alpha"])
    _wait_repo(page, "alpha", keys["alpha"])
    after = _sidebar(page)
    assert after["selectedFile"] == chosen
    assert directory in after["expandedDirs"]
    assert page.locator(
        '#repo-file-list .repo-file-item.active[data-path="%s"]' % chosen).count() == 1


def test_stale_listing_response_is_ignored(page, dashboard_fleet):
    """A late alpha listing that arrives after beta has mounted changes
    neither beta's tree nor beta's state."""
    page.goto(_origin(dashboard_fleet), wait_until="load")
    keys = _keys(page, dashboard_fleet)
    held = []
    page.route("**/api/repo/alpha/files*", lambda route: held.append(route))
    _nav(page, "alpha", keys["alpha"])
    page.wait_for_function("() => true")
    page.wait_for_timeout(200)
    assert held, "alpha's listing should be held"

    _nav(page, "beta", keys["beta"])
    _wait_repo(page, "beta", keys["beta"])
    before = _sidebar(page)
    tree = page.inner_html("#repo-file-list")

    # Release alpha with a listing whose default document beta does not
    # have: an unguarded write would select it in beta's state.
    body = json.dumps({"files": [{"path": "pulse.md", "name": "pulse.md",
                                  "source": "gator", "mtime": 1}]})
    for route in held:
        route.fulfill(status=200, content_type="application/json", body=body)
    page.unroute("**/api/repo/alpha/files*")
    page.wait_for_timeout(1000)

    assert _sidebar(page) == before
    assert page.inner_html("#repo-file-list") == tree


def test_same_name_different_key_state_is_separate(page, dashboard_fleet):
    """Two repository keys with one display name never share tree state."""
    keys = _open_alpha(page, dashboard_fleet)
    directory = _collapsed_dir_outside(page, _sidebar(page)["selectedFile"])
    assert directory
    _expand(page, directory)
    assert directory in _sidebar(page)["expandedDirs"]

    _nav(page, "alpha", "fakekey0001")
    _wait_repo(page, "alpha", "fakekey0001")
    assert directory not in _sidebar(page)["expandedDirs"]

    _nav(page, "alpha", keys["alpha"])
    _wait_repo(page, "alpha", keys["alpha"])
    assert directory in _sidebar(page)["expandedDirs"]


_COUNT_SEARCH_LISTENERS = """
    window.__searchInputListeners = 0;
    const add = EventTarget.prototype.addEventListener;
    const remove = EventTarget.prototype.removeEventListener;
    EventTarget.prototype.addEventListener = function (type, fn, opts) {
        if (this && this.id === 'repo-search-input' && type === 'input') window.__searchInputListeners++;
        return add.call(this, type, fn, opts);
    };
    EventTarget.prototype.removeEventListener = function (type, fn, opts) {
        if (this && this.id === 'repo-search-input' && type === 'input') window.__searchInputListeners--;
        return remove.call(this, type, fn, opts);
    };
"""


def test_single_search_listener_after_revisits(page, dashboard_fleet):
    """After alpha → beta → alpha, exactly one search-box listener is
    registered and one query runs exactly one search, for alpha. (Counting
    requests alone would not see a leak: the handlers share one debounce
    timer, so a leftover handler's search is cancelled by the next.)"""
    page.add_init_script(script=_COUNT_SEARCH_LISTENERS)
    keys = _open_alpha(page, dashboard_fleet)
    _nav(page, "beta", keys["beta"])
    _wait_repo(page, "beta", keys["beta"])
    _nav(page, "alpha", keys["alpha"])
    _wait_repo(page, "alpha", keys["alpha"])
    assert page.evaluate("() => window.__searchInputListeners") == 1

    searches = []
    page.on("request", lambda r: searches.append(r.url) if "/search?" in r.url else None)
    page.fill("#repo-search-input", "mission")
    page.wait_for_timeout(1200)
    assert len(searches) == 1, searches
    assert "/api/repo/alpha/search?" in searches[0]


# ── cached return and background reconciliation (checkpoint 2) ───────────

import pytest  # noqa: E402

ALPHA_FILES = "**/api/repo/alpha/files*"


def _cache(page):
    return page.evaluate("() => window.__gator_debug.listingCache")


def _alpha_beta_alpha_held(page, fleet):
    """alpha, beta, then return to alpha with its listing held. Returns
    (keys, held routes); the cached tree is drawn when this returns."""
    keys = _open_alpha(page, fleet)
    _nav(page, "beta", keys["beta"])
    _wait_repo(page, "beta", keys["beta"])
    held = []
    page.route(ALPHA_FILES, lambda route: held.append(route))
    _nav(page, "alpha", keys["alpha"])
    _wait_repo(page, "alpha", keys["alpha"])
    return keys, held


def _select_visible_document(page):
    """Open a folder and select a non-default document inside it."""
    default = _sidebar(page)["selectedFile"]
    folder = _collapsed_dir_outside(page, default)
    _expand(page, folder)
    chosen = page.evaluate("""([d, dir]) => {
        const items = Array.from(document.querySelectorAll('#repo-file-list .repo-file-item'));
        const other = items.find(i => i.dataset.path !== d && i.offsetParent !== null
            && i.dataset.path.startsWith(dir + '/') && !/\\.html?$/i.test(i.dataset.path));
        return other ? other.dataset.path : null;
    }""", [default, folder])
    page.click('#repo-file-list .repo-file-item[data-path="%s"]' % chosen)
    return chosen


_OBSERVE = """() => {
    window.__treeMutations = 0;
    window.__treeObserver = new MutationObserver(m => { window.__treeMutations += m.length; });
    window.__treeObserver.observe(document.getElementById('repo-file-list'),
        {subtree: true, childList: true, attributes: true, characterData: true});
}"""


def test_return_draws_cached_tree_before_listing(page, dashboard_fleet):
    """Returning to alpha draws its tree while alpha's listing request is
    still held: the tree comes from the cache, not the network."""
    keys, held = _alpha_beta_alpha_held(page, dashboard_fleet)
    assert held, "alpha's listing should be in flight"
    assert page.locator("#repo-file-list .repo-file-item").count() > 0
    assert "Loading files" not in page.inner_text("#repo-file-list")
    for route in held:
        route.continue_()
    page.unroute(ALPHA_FILES)


def test_return_restores_scroll(page, dashboard_fleet):
    """The tree's scroll position comes back on return."""
    page.set_viewport_size({"width": 1280, "height": 600})
    keys = _open_alpha(page, dashboard_fleet)
    for folder in ("artifacts", "artifacts/many"):
        if page.locator('#repo-file-list .repo-tree-dir[data-dir="%s"]' % folder).count():
            if folder not in _sidebar(page)["expandedDirs"]:
                _expand(page, folder)
    saved = page.evaluate("""() => {
        const s = document.getElementById('repo-file-list');
        s.scrollTop = 300;
        return s.scrollTop;
    }""")
    assert saved > 0, "the alpha tree must be scrollable for this test"

    _nav(page, "beta", keys["beta"])
    _wait_repo(page, "beta", keys["beta"])
    assert _sidebar(page)["scrollTop"] == 0  # beta has its own state
    _nav(page, "alpha", keys["alpha"])
    _wait_repo(page, "alpha", keys["alpha"])
    restored = page.evaluate("() => document.getElementById('repo-file-list').scrollTop")
    assert abs(restored - saved) <= 1, (restored, saved)


@pytest.mark.parametrize("outcome", ["unchanged", "changed", "failed"])
def test_background_listing_reconciles(page, dashboard_fleet, outcome):
    """After a cached return: an unchanged listing writes nothing; a changed
    listing redraws once and drops a selection whose file is gone; a failed
    request keeps the cached tree."""
    keys = _open_alpha(page, dashboard_fleet)
    chosen = _select_visible_document(page)
    _nav(page, "beta", keys["beta"])
    _wait_repo(page, "beta", keys["beta"])
    held = []
    page.route(ALPHA_FILES, lambda route: held.append(route))
    _nav(page, "alpha", keys["alpha"])
    _wait_repo(page, "alpha", keys["alpha"])
    assert _sidebar(page)["selectedFile"] == chosen
    page.evaluate(_OBSERVE)

    route = held[0]
    if outcome == "unchanged":
        route.continue_()
    elif outcome == "changed":
        response = route.fetch()
        data = response.json()
        data["files"] = [f for f in data["files"] if f["path"] != chosen]
        route.fulfill(response=response, body=json.dumps(data))
    else:
        route.abort()
    page.unroute(ALPHA_FILES)
    page.wait_for_timeout(1200)

    mutations = page.evaluate("() => window.__treeMutations")
    gone = page.locator('#repo-file-list .repo-file-item[data-path="%s"]' % chosen).count() == 0
    if outcome == "changed":
        assert mutations > 0 and gone
        assert _sidebar(page)["selectedFile"] is None
    else:
        assert mutations == 0, mutations
        assert not gone and _sidebar(page)["selectedFile"] == chosen


def test_versioned_view_bypasses_cache(page, dashboard_fleet):
    """A historical (?version=) mount loads honestly and neither reads nor
    writes the live cache."""
    _open_alpha(page, dashboard_fleet)
    before = _cache(page)
    assert any(e["items"] > 0 for e in before)
    page.click("#branch-history-btn")
    page.wait_for_selector('#branch-history-dropdown .history-item[data-hash]:not([data-hash=""])',
                           timeout=10000)
    held = []
    page.route("**/api/repo/alpha/files?version=*", lambda route: held.append(route))
    page.click('#branch-history-dropdown .history-item[data-hash]:not([data-hash=""])')
    page.wait_for_function("() => document.getElementById('repo-file-list')"
                           " && document.getElementById('repo-file-list').innerText"
                           ".includes('Loading files')", timeout=10000)
    assert held, "the versioned listing should be fetched, not drawn from the cache"
    for route in held:
        route.continue_()
    page.unroute("**/api/repo/alpha/files?version=*")
    page.wait_for_selector("#repo-file-list .repo-file-item", timeout=15000)
    assert _cache(page) == before


def test_cache_bounds_evict_oldest(page, dashboard_fleet):
    """The cache keeps at most 8 repositories, evicting the least recently
    used; a listing over the 20,000-entry budget renders but is not cached."""
    keys = _open_alpha(page, dashboard_fleet)
    fakes = ["k%02d" % i for i in range(1, 10)]
    for fake in fakes:
        _nav(page, "alpha", fake)
        _wait_repo(page, "alpha", fake)
    cached = [e["repoKey"] for e in _cache(page)]
    assert cached == fakes[1:], cached  # the real key and k01 were evicted
    assert len(cached) == 8

    sample = page.request.get(_origin(dashboard_fleet) + "api/repo/alpha/files").json()["files"][0]
    bulk = []
    for i in range(20001):
        entry = dict(sample)
        entry["path"] = "bulk/f%05d.md" % i
        entry["name"] = "f%05d.md" % i
        bulk.append(entry)
    page.route(ALPHA_FILES, lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"files": bulk})))
    _nav(page, "alpha", "bigkey01")
    # The copies may be filtered out of the visible tree (top-level names
    # are allow-listed); the budget applies to the canonical listing, so
    # wait for the listing to have rendered at all.
    page.wait_for_function(
        "() => window.__gator_debug.sidebar.repoKey === 'bigkey01'"
        " && !document.getElementById('repo-file-list').innerText.includes('Loading files')",
        timeout=30000)
    page.unroute(ALPHA_FILES)
    after = [e["repoKey"] for e in _cache(page)]
    assert "bigkey01" not in after and after == cached
