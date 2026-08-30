"""Snapshot mode — self-contained offline HTML generation.

Produces a single HTML file with inlined CSS, JS, and Tier 1 data.
No server required to view the result.
"""

import json
import re

from dashboard.helpers import DASHBOARD_DIR


def _read_asset(rel_path):
    """Read a frontend asset file from the dashboard/ directory."""
    return (DASHBOARD_DIR / rel_path).read_text(encoding="utf-8")


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
    repo_js = _read_asset("views/repo.js")
    blueprint_js = _read_asset("views/blueprint.js")
    updates_js = _read_asset("views/updates.js")
    settings_js = _read_asset("views/settings.js")
    shell_js = _read_asset("dashboard.js")

    data_block = (
        "<script>\n"
        "window.GATOR_SNAPSHOT = true;\n"
        f"window.DASHBOARD_DATA = {json.dumps(fast_data, default=str)};\n"
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
        f"<script>\n{repo_js}\n</script>\n"
        f"<script>\n{blueprint_js}\n</script>\n"
        f"<script>\n{updates_js}\n</script>\n"
        f"<script>\n{settings_js}\n</script>\n"
        f"{data_block}\n"
        f"<script>\n{shell_js}\n</script>"
    )
    html = re.sub(
        r'\s*<script src="views/fleet\.js"></script>\s*'
        r'<script src="views/history\.js"></script>\s*'
        r'<script src="views/repo\.js"></script>\s*'
        r'<script src="views/blueprint\.js"></script>\s*'
        r'<script src="views/updates\.js"></script>\s*'
        r'<script src="views/settings\.js"></script>\s*'
        r'<script src="dashboard\.js"></script>',
        lambda m: scripts_block,
        html,
    )

    return html
