"""Docs view: the shipped Gator HTML documents, repository-independent.

Since 2026-10-13 the Docs sidebar entry is always enabled, like Updates.
It lists the documents shipped in the installed package (the Welcome
topics first, in Welcome order, then the Docs-only documents) with
reader-friendly labels, and opens each in a sandboxed iframe served by
the closed-allowlist route `/api/welcome/docs/<name>`. Selecting a
repository does not change the list.
"""
from pathlib import Path

DOC_ROUTE = "/api/welcome/docs/"
EXPECTED = [
    ("gator-overview.html", "Gator overview"),
    ("what-gator-can-do.html", "What Gator can do"),
    ("gatorize-a-repo.html", "Gatorize a repo"),
    ("start-a-session.html", "Start a session"),
    ("gator-docs.html", "Asking for a Gator doc"),
    ("gator-loop.html", "Gator loop"),
    ("gator-loop-extras.html", "Gator loop extras"),
    ("pre-commit-checks.html", "Pre-commit checks"),
    ("charter-formation-process.html", "Charter formation process"),
    ("charter-schema-v1.html", "Charter schema"),
    ("code-migrations.html", "Code migrations"),
]
SHIPPED = (Path(__file__).resolve().parents[2] / "src" / "gator_command"
           / "templates" / "gator-starter" / "docs")


def _origin(fleet):
    return fleet["url"].rstrip("/") + "/"


def _items(page):
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('.docs-sidebar .repo-file-item')).map(
            b => ({doc: b.dataset.doc, label: b.textContent,
                   active: b.classList.contains('active'),
                   current: b.getAttribute('aria-current')}))""")


def _open_docs(page):
    page.click('.sidebar-item[data-view="docs"]')
    page.wait_for_selector(".docs-sidebar .repo-file-item", timeout=15000)


def _frame_text(page, selector):
    return page.frame_locator(".docs-content iframe.docs-frame").locator(
        selector).first.text_content(timeout=10000)


def test_docs_is_enabled_without_a_repository(page, dashboard_fleet):
    page.goto(_origin(dashboard_fleet), wait_until="load")
    page.wait_for_selector(".welcome-workspace", timeout=15000)
    tab = page.locator('.sidebar-item[data-view="docs"]')
    assert "dimmed" not in (tab.get_attribute("class") or "")
    _open_docs(page)
    assert page.evaluate(
        "() => document.getElementById('topbar-title').textContent") == "Docs"
    # No repository context was created, and the repo search box is hidden.
    assert "dimmed" in (page.locator("#repo-tab").get_attribute("class") or "")
    # The unavailable state has a non-colour cue (Paper).
    assert page.locator("#repo-tab").get_attribute("aria-disabled") == "true"
    assert page.locator("#repo-tab").get_attribute("title") == "Choose a repository in Fleet first"
    assert page.evaluate("""() => {
        const s = document.getElementById('repo-search-input');
        return !s || s.style.display === 'none'; }""")


def test_docs_lists_the_shipped_documents_in_order(page, dashboard_fleet):
    page.goto(_origin(dashboard_fleet), wait_until="load")
    _open_docs(page)
    items = _items(page)
    assert [(i["doc"], i["label"]) for i in items] == EXPECTED
    assert {p.name for p in SHIPPED.glob("*.html")} == {d for d, _ in EXPECTED}


def test_docs_opens_the_first_document_sandboxed(page, dashboard_fleet):
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(_origin(dashboard_fleet), wait_until="load")
    _open_docs(page)
    items = _items(page)
    assert items[0]["active"] and items[0]["current"] == "page"
    assert sum(i["active"] for i in items) == 1
    frame = page.locator(".docs-content iframe.docs-frame")
    assert frame.get_attribute("sandbox") == "allow-scripts"
    assert frame.get_attribute("src") == DOC_ROUTE + "gator-overview.html"
    assert frame.get_attribute("title") == "Gator overview"
    assert _frame_text(page, "h2") == "About Gator"
    # Docs reads the package, never a repository endpoint.
    assert not any("/api/repo/" in u for u in requests), requests


def test_docs_switches_document_on_click(page, dashboard_fleet):
    page.goto(_origin(dashboard_fleet), wait_until="load")
    _open_docs(page)
    page.click(".docs-sidebar .repo-file-item[data-doc='charter-schema-v1.html']")
    frame = page.locator(".docs-content iframe.docs-frame")
    assert frame.get_attribute("src") == DOC_ROUTE + "charter-schema-v1.html"
    assert _frame_text(page, "#about h2") == "What the schema covers"
    assert [i["label"] for i in _items(page) if i["active"]] == ["Charter schema"]
    assert page.locator(".docs-content iframe").count() == 1


def test_docs_is_the_same_with_a_repository_selected(page, dashboard_fleet):
    page.goto(_origin(dashboard_fleet) + "?repo=alpha", wait_until="load")
    page.wait_for_selector(".repo-file-item", timeout=15000)
    _open_docs(page)
    assert [(i["doc"], i["label"]) for i in _items(page)] == EXPECTED
    # The repository stays selected for Repo/Loop.
    assert "dimmed" not in (page.locator("#repo-tab").get_attribute("class") or "")
    assert page.locator("#repo-tab").get_attribute("aria-disabled") is None
    assert page.locator("#repo-tab").get_attribute("title") is None
