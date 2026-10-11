"""Snapshot mode — self-contained offline HTML generation.

Produces a single HTML file with inlined CSS, JS, and Tier 1 data.
No server required to view the result.
"""

import json
import re

from dashboard.content_policy import html_csp_meta_policy
from dashboard.helpers import (
    DASHBOARD_DIR, WELCOME_DOC_NAMES, read_welcome_html,
)


def _read_asset(rel_path):
    """Read a frontend asset file from the dashboard/ directory."""
    return (DASHBOARD_DIR / rel_path).read_text(encoding="utf-8")


def _json_script(value):
    """JSON for an inline <script>. Every `<`, `>` and `&` becomes a
    `\\uXXXX` escape (non-ASCII, including U+2028/2029, is already
    escaped by `json.dumps`), so neither `</script>` nor `<!--` can
    appear and document text can never leave the script element."""
    return (json.dumps(value)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026"))


_HEAD_OPEN_RE = re.compile(r"<head(?:\s[^>]*)?>", re.IGNORECASE)


def _with_csp_meta(html):
    """Insert the Dashboard HTML CSP as a <meta> right after `<head>`.

    Returns None for None or a document without a `<head>` tag: a
    snapshot never embeds a Welcome document without the policy.
    """
    if html is None:
        return None
    m = _HEAD_OPEN_RE.search(html)
    if m is None:
        return None
    meta = ('<meta http-equiv="Content-Security-Policy" content="'
            + html_csp_meta_policy() + '">')
    return html[:m.end()] + meta + html[m.end():]


def _welcome_docs_for_snapshot():
    """The four Welcome documents for `window.GATOR_WELCOME_DOCS`:
    name -> text with the CSP meta, or None (unavailable / no `<head>`).
    `welcome.js` assigns each through the `iframe.srcdoc` property."""
    return {name: _with_csp_meta(read_welcome_html(name))
            for name in sorted(WELCOME_DOC_NAMES)}


def build_snapshot(fast_data):
    """Produce a self-contained HTML snapshot (Tier 1 data only).

    Inlines CSS, JS, and data. No server required to view.
    Repo view is disabled in snapshot mode.

    Args:
        fast_data: Tier 1 data dict from collect_fast_data() or
                   collect_standalone_data().
    """
    html = _read_asset("dashboard.html")
    css = _read_asset("dashboard.css")
    fleet_js = _read_asset("views/fleet.js")
    # history.js replaces audit.js in Individual; read whichever exists
    history_path = DASHBOARD_DIR / "views" / "history.js"
    audit_path = DASHBOARD_DIR / "views" / "audit.js"
    if history_path.exists():
        history_or_audit_js = history_path.read_text(encoding="utf-8")
    elif audit_path.exists():
        history_or_audit_js = audit_path.read_text(encoding="utf-8")
    else:
        history_or_audit_js = ""
    syntax_js = _read_asset("views/syntax.js")
    repo_js = _read_asset("views/repo.js")
    updates_js = _read_asset("views/updates.js")
    loop_markdown_js = _read_asset("views/loop-markdown.js")  # #45
    loop_js = _read_asset("views/loop.js")
    settings_js = _read_asset("views/settings.js")
    welcome_js = _read_asset("views/welcome.js")  # #72
    shell_js = _read_asset("dashboard.js")

    data_block = (
        "<script>\n"
        "window.GATOR_SNAPSHOT = true;\n"
        f"window.DASHBOARD_DATA = {json.dumps(fast_data, default=str)};\n"
        # Welcome topics: a snapshot has no server, so the four documents
        # are inlined (script-safe JSON; null if unavailable).
        f"window.GATOR_WELCOME_DOCS = {_json_script(_welcome_docs_for_snapshot())};\n"
        "</script>"
    )

    # Replace external stylesheet link with inline <style>
    # Use lambda replacement to avoid re.sub interpreting backslashes in content.
    css_block = f"\n<style>\n{css}\n</style>"
    html = re.sub(
        r'\s*<link rel="stylesheet" href="dashboard\.css">',
        lambda m: css_block,
        html,
    )

    # Replace the view script tags with inlined versions
    scripts_block = (
        f"\n<script>\n{fleet_js}\n</script>\n"
        f"<script>\n{history_or_audit_js}\n</script>\n"
        f"<script>\n{syntax_js}\n</script>\n"
        f"<script>\n{repo_js}\n</script>\n"
        f"<script>\n{updates_js}\n</script>\n"
        f"<script>\n{loop_markdown_js}\n</script>\n"
        f"<script>\n{loop_js}\n</script>\n"
        f"<script>\n{settings_js}\n</script>\n"
        f"<script>\n{welcome_js}\n</script>\n"
        f"{data_block}\n"
        f"<script>\n{shell_js}\n</script>"
    )
    html = re.sub(
        r'\s*<script src="views/fleet\.js"></script>\s*'
        r'<script src="views/history\.js"></script>\s*'
        r'<script src="views/syntax\.js"></script>\s*'
        r'<script src="views/repo\.js"></script>\s*'
        r'<script src="views/updates\.js"></script>\s*'
        r'<script src="views/loop-markdown\.js"></script>\s*'
        r'<script src="views/loop\.js"></script>\s*'
        r'<script src="views/settings\.js"></script>\s*'
        r'<script src="views/welcome\.js"></script>\s*'
        r'<script src="dashboard\.js"></script>',
        lambda m: scripts_block,
        html,
    )

    return html
