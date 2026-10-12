"""Docs view lists Gator narrative HTML documents only (2026-10-12).

The Docs sidebar entry is the Repo view with `filter="docs"`. It lists
the `.html` files directly in `.gator/docs/`: the four shipped Welcome
documents first, in Welcome-tab order and with their Welcome labels,
then any other HTML document alphabetically. Markdown in `.gator/docs/`
and anything in the repo-root `docs/` folder are not listed. The first
document opens automatically in the sandboxed inline preview.

Seed: `test_responsive_shell_seed.seed_sidebar_fixtures`.
"""


def _open_docs(page, fleet, repo="alpha"):
    origin = fleet["url"].rstrip("/") + "/"
    page.goto(origin + "?repo=" + repo, wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    page.click('.sidebar-item[data-view="docs"]')
    page.wait_for_selector(".repo-sidebar-header:text('Docs')", timeout=15000)
    page.wait_for_selector(".repo-file-item", timeout=15000)


def _items(page):
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('.repo-sidebar .repo-file-item')).map(
            b => ({label: b.textContent.trim(), path: b.dataset.path,
                   active: b.classList.contains('active')}))""")


def test_docs_view_lists_only_gator_html_documents(page, dashboard_fleet):
    _open_docs(page, dashboard_fleet)
    items = _items(page)
    names = [i["path"].rsplit("/", 1)[-1] for i in items]
    # Welcome documents first (Welcome order), then others A→Z.
    assert names == ["gator-overview.html", "start-a-session.html",
                     "alpha-guide.html", "zeta-notes.html"], names
    assert [i["label"] for i in items] == [
        "Gator overview", "Start a session",
        "Alpha guide", "Zeta notes"]
    # No Markdown, nothing from the repo-root docs/ folder.
    assert not any(n.endswith(".md") for n in names)
    assert not any("project-notes" in i["path"] for i in items)


def test_docs_view_opens_first_document_inline(page, dashboard_fleet):
    _open_docs(page, dashboard_fleet)
    items = _items(page)
    assert items[0]["active"] is True
    assert sum(i["active"] for i in items) == 1
    frame = page.locator(".repo-content iframe.repo-iframe")
    frame.wait_for(timeout=15000)
    assert frame.get_attribute("sandbox") == "allow-scripts"
    title = page.frame_locator(".repo-content iframe.repo-iframe").locator("#doc-title")
    assert title.text_content(timeout=10000) == "Overview"


def test_docs_view_switches_document_on_click(page, dashboard_fleet):
    _open_docs(page, dashboard_fleet)
    page.click(".repo-sidebar .repo-file-item:text('Zeta notes')")
    title = page.frame_locator(".repo-content iframe.repo-iframe").locator("#doc-title")
    assert title.text_content(timeout=10000) == "Zeta notes"
    active = [i["label"] for i in _items(page) if i["active"]]
    assert active == ["Zeta notes"]
