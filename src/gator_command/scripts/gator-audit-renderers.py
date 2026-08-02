#!/usr/bin/env python3
"""
gator-audit-renderers.py — Output renderers for gator audit.

Pure rendering functions: take an assembled audit data dict, return a string.
No data collection, no side effects, no shared state.

Consumers:
    from gator_audit_renderers import render_text, render_html

@reads: nothing (pure functions)
@writes: nothing (returns strings)
"""


# ---------------------------------------------------------------------------
# Text Output
# ---------------------------------------------------------------------------

def render_text(data):
    """Render audit data as terminal text."""
    lines = []

    lines.append("")
    lines.append(f"  gator audit")
    lines.append(f"  {data['generated_local']}  |  {data['version']}  |  {data.get('machine', {}).get('label', '?')}")
    lines.append("")

    # Build drift lookup for fleet indicator
    drift_by_name = {}
    for d in data.get("drift", []):
        drift_by_name[d.get("name", "")] = d.get("severity", "ok")

    # Fleet Status
    fleet = data.get("fleet_status", [])
    if fleet:
        lines.append(f"  FLEET STATUS ({len(fleet)} repos)")
        lines.append("")
        for r in fleet:
            if not r.get("accessible"):
                lines.append(f"    ✗ {r.get('name', '?')} — NOT ACCESSIBLE")
                continue

            hooks = "✓" if r.get("has_hooks") else "✗"
            trailers = "✓" if r.get("trailers") else "·"

            # Indicator reflects governance health, not just issues
            repo_drift = drift_by_name.get(r.get("name", ""), "ok")
            if repo_drift == "drift":
                indicator = "✗"
            elif repo_drift == "warn" or not r.get("has_hooks"):
                indicator = "⚠"
            else:
                indicator = "✓"

            charters = r.get("charters", 0)
            functions = r.get("functions", 0)

            commit = r.get("last_commit")
            commit_str = ""
            if commit and not commit.get("error"):
                commit_str = f"  last: {commit['age']}"

            lines.append(
                f"    {indicator} {r.get('name', '?'):<20}"
                f"  charters: {charters:>2} ({functions:>2} fn)"
                f"  hooks: {hooks}  trailers: {trailers}"
                f"{commit_str}"
            )
        lines.append("")

    # Drift
    drift_list = data.get("drift", [])
    drift_sum = data.get("drift_summary", {})
    if drift_list:
        ok = drift_sum.get("ok", 0)
        warn = drift_sum.get("warn", 0)
        drifted = drift_sum.get("drift", 0)

        # Surface command-post git failure once, not per-repo
        cp_state = drift_sum.get("command_post", {})
        if cp_state.get("git_failed"):
            lines.append(f"  DRIFT (command post git access failed — policy comparison skipped)")
        else:
            lines.append(f"  DRIFT ({ok} current, {warn} warnings, {drifted} drifted)")
        lines.append("")

        seen_cp_warn = False
        for r in drift_list:
            if r.get("severity") == "ok":
                continue
            name = r.get("name", "?")
            sev = "✗" if r["severity"] == "drift" else "⚠"
            lines.append(f"    {sev} {name}")
            for f in r.get("findings", []):
                # Deduplicate command-post git failure across repos
                if f["check"] == "policy-version" and "git failed" in f.get("message", ""):
                    if not seen_cp_warn:
                        seen_cp_warn = True
                        marker = "⚠"
                        lines.append(f"      {marker} {f['check']}: {f['message']}")
                    continue
                marker = "✗" if f["severity"] == "drift" else "⚠"
                lines.append(f"      {marker} {f['check']}: {f['message']}")
        if drifted == 0 and warn == 0:
            lines.append(f"    All repos current.")
        lines.append("")

    # Sessions
    sessions = data.get("sessions", {})
    if sessions and not sessions.get("error"):
        since = sessions.get("since_days", 7)
        recent = sessions.get("recent", 0)
        total = sessions.get("total", 0)
        lines.append(f"  SESSIONS (last {since} days: {recent} of {total} total)")
        lines.append("")

        by_vendor = sessions.get("by_vendor", {})
        if by_vendor:
            vendor_parts = [f"{v}: {c}" for v, c in sorted(by_vendor.items())]
            lines.append(f"    Vendors: {' | '.join(vendor_parts)}")

        by_repo = sessions.get("by_repo", {})
        if by_repo:
            repo_parts = [f"{r}({c})" for r, c in list(by_repo.items())[:6]]
            lines.append(f"    Repos:   {', '.join(repo_parts)}")

        pending = sessions.get("pending_export", 0)
        exported = sessions.get("exported", 0)
        lines.append(f"    Export:  {exported} exported, {pending} pending")
        lines.append("")

    # Governance Coverage
    gov = data.get("governance", {})
    if gov:
        lines.append(f"  GOVERNANCE COVERAGE")
        lines.append("")
        lines.append(f"    Charters: {gov.get('charters', 0)} across {gov.get('repos', 0)} repos ({gov.get('functions', 0)} functions)")
        lines.append(f"    Hooks:    {gov.get('hooks_installed', 0)}/{gov.get('repos', 0)} repos")
        lines.append(f"    Trailers: {gov.get('trailers_flowing', 0)}/{gov.get('repos', 0)} repos")
        lines.append(f"    Issues:   {gov.get('issues', 0)} open")
        lines.append("")

    # Recent Decisions
    decisions = data.get("decisions", [])
    if decisions:
        lines.append(f"  RECENT DECISIONS ({len(decisions)})")
        lines.append("")
        for d in decisions[:10]:
            ts = d.get("timestamp", "")[:10]
            repo = d.get("repo", "")
            repo_str = f" [{repo}]" if repo else ""
            text = d.get("text", "")[:80]
            lines.append(f"    [{ts}]{repo_str} {text}")
        lines.append("")

    lines.append(f"  Generated: {data['generated_local']}  |  Machine: {data.get('machine', {}).get('label', '?')}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML Output
# ---------------------------------------------------------------------------

def render_html(data):
    """Render audit data as a self-contained HTML file.

    Single file, inline CSS, no JavaScript dependencies, no external
    resources. Opens in any browser. Can be saved as PDF, emailed,
    attached to compliance reports. Air-gapped compatible.
    """
    fleet = data.get("fleet_status", [])
    drift = data.get("drift", [])
    drift_sum = data.get("drift_summary", {})
    sessions = data.get("sessions", {})
    gov = data.get("governance", {})
    decisions = data.get("decisions", [])
    machine = data.get("machine", {})

    # Build drift lookup for fleet indicator
    drift_by_name = {}
    for d in drift:
        drift_by_name[d.get("name", "")] = d.get("severity", "ok")

    # Fleet rows
    fleet_rows = ""
    for r in fleet:
        if not r.get("accessible"):
            fleet_rows += f'<tr class="drift"><td>{r.get("name","?")}</td><td colspan="5">NOT ACCESSIBLE</td></tr>\n'
            continue

        repo_drift = drift_by_name.get(r.get("name", ""), "ok")
        if repo_drift == "drift":
            status_class = "drift"
        elif repo_drift == "warn" or not r.get("has_hooks"):
            status_class = "warn"
        else:
            status_class = "ok"
        hooks = "&#10003;" if r.get("has_hooks") else "&#10007;"
        hooks_class = "ok" if r.get("has_hooks") else "drift"
        trailers = "&#10003;" if r.get("trailers") else "&middot;"
        trailers_class = "ok" if r.get("trailers") else "muted"

        commit = r.get("last_commit")
        age = commit.get("age", "?") if commit and not commit.get("error") else "?"

        fleet_rows += f'''<tr class="{status_class}">
  <td><strong>{r.get("name","?")}</strong></td>
  <td>{r.get("charters",0)} ({r.get("functions",0)} fn)</td>
  <td class="{hooks_class}">{hooks}</td>
  <td class="{trailers_class}">{trailers}</td>
  <td>{r.get("issues",0)}</td>
  <td>{age}</td>
</tr>\n'''

    # Drift rows — deduplicate command-post git failure (same as text view)
    drift_rows = ""
    cp_state = drift_sum.get("command_post", {})
    cp_git_failed = cp_state.get("git_failed", False)
    seen_cp_warn = False

    if cp_git_failed:
        drift_rows += '<tr class="warn"><td colspan="3">Command post git access failed — policy comparison skipped for all repos</td></tr>\n'

    for r in drift:
        if r.get("severity") == "ok":
            continue
        for f in r.get("findings", []):
            # Deduplicate command-post git failure
            if f["check"] == "policy-version" and "git failed" in f.get("message", ""):
                continue
            sev_class = "drift" if f["severity"] == "drift" else "warn"
            drift_rows += f'<tr class="{sev_class}"><td>{r.get("name","?")}</td><td>{f["check"]}</td><td>{f["message"]}</td></tr>\n'

    if not drift_rows:
        drift_rows = '<tr class="ok"><td colspan="3">All repos current. No drift detected.</td></tr>'

    # Session stats
    by_vendor_html = ""
    for v, c in sorted(sessions.get("by_vendor", {}).items()):
        by_vendor_html += f'<span class="tag">{v}: {c}</span> '

    # Decision rows
    decision_rows = ""
    for d in decisions[:10]:
        ts = d.get("timestamp", "")[:10]
        repo = d.get("repo", "")
        text = d.get("text", "")[:100]
        decision_rows += f'<tr><td>{ts}</td><td>{repo}</td><td>{text}</td></tr>\n'

    if not decision_rows:
        decision_rows = '<tr><td colspan="3">No decisions extracted from recent sessions.</td></tr>'

    ok_count = drift_sum.get("ok", 0)
    warn_count = drift_sum.get("warn", 0)
    drift_count = drift_sum.get("drift", 0)
    since_days = sessions.get("since_days", 7)
    recent_sessions = sessions.get("recent", 0)
    total_sessions = sessions.get("total", 0)
    pending = sessions.get("pending_export", 0)
    exported = sessions.get("exported", 0)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gator Audit — {data["generated_local"]}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
         background: #0d1117; color: #c9d1d9; padding: 24px; line-height: 1.5; }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ color: #58a6ff; font-size: 1.4em; margin-bottom: 4px; }}
  h2 {{ color: #8b949e; font-size: 1.1em; margin: 24px 0 12px 0;
        border-bottom: 1px solid #21262d; padding-bottom: 6px; }}
  .subtitle {{ color: #8b949e; font-size: 0.85em; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0 16px 0; font-size: 0.85em; }}
  th {{ text-align: left; color: #8b949e; padding: 6px 10px; border-bottom: 1px solid #21262d; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #161b22; }}
  tr:hover {{ background: #161b22; }}
  .ok {{ color: #3fb950; }}
  .warn {{ color: #d29922; }}
  .drift {{ color: #f85149; }}
  .muted {{ color: #484f58; }}
  .stats {{ display: flex; gap: 24px; flex-wrap: wrap; margin: 12px 0; }}
  .stat {{ background: #161b22; border: 1px solid #21262d; border-radius: 6px;
           padding: 12px 16px; min-width: 140px; }}
  .stat-value {{ font-size: 1.6em; font-weight: bold; color: #58a6ff; }}
  .stat-label {{ font-size: 0.8em; color: #8b949e; }}
  .tag {{ background: #21262d; padding: 2px 8px; border-radius: 3px;
          font-size: 0.8em; margin-right: 4px; }}
  .footer {{ margin-top: 32px; padding-top: 12px; border-top: 1px solid #21262d;
             color: #484f58; font-size: 0.75em; }}
  @media print {{
    body {{ background: white; color: #1f2328; }}
    .stat {{ border-color: #d0d7de; }}
    tr:hover {{ background: transparent; }}
  }}
</style>
</head>
<body>
<div class="container">

<h1>Gator Audit Dashboard</h1>
<div class="subtitle">{data["generated_local"]} &middot; {data["version"]} &middot; {machine.get("label", "?")}</div>

<div class="stats">
  <div class="stat"><div class="stat-value">{gov.get("repos", 0)}</div><div class="stat-label">Repos</div></div>
  <div class="stat"><div class="stat-value">{gov.get("charters", 0)}</div><div class="stat-label">Charters</div></div>
  <div class="stat"><div class="stat-value">{gov.get("functions", 0)}</div><div class="stat-label">Functions</div></div>
  <div class="stat"><div class="stat-value {("ok" if drift_count == 0 else "drift")}">{drift_count}</div><div class="stat-label">Drifted</div></div>
  <div class="stat"><div class="stat-value">{recent_sessions}</div><div class="stat-label">Sessions ({since_days}d)</div></div>
  <div class="stat"><div class="stat-value">{gov.get("issues", 0)}</div><div class="stat-label">Issues</div></div>
</div>

<h2>Fleet Status</h2>
<table>
  <tr><th>Repo</th><th>Charters</th><th>Hooks</th><th>Trailers</th><th>Issues</th><th>Last Commit</th></tr>
  {fleet_rows}
</table>

<h2>Drift Findings</h2>
<div class="subtitle">{ok_count} current, {warn_count} warnings, {drift_count} drifted</div>
<table>
  <tr><th>Repo</th><th>Check</th><th>Finding</th></tr>
  {drift_rows}
</table>

<h2>Sessions (last {since_days} days)</h2>
<div class="subtitle">{recent_sessions} of {total_sessions} total &middot; {exported} exported, {pending} pending</div>
<div style="margin: 8px 0;">{by_vendor_html}</div>

<h2>Recent Decisions</h2>
<table>
  <tr><th>Date</th><th>Repo</th><th>Decision</th></tr>
  {decision_rows}
</table>

<h2>Governance Coverage</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Charters</td><td>{gov.get("charters",0)} across {gov.get("repos",0)} repos ({gov.get("functions",0)} functions documented)</td></tr>
  <tr><td>Hooks Installed</td><td class="{"ok" if gov.get("hooks_installed",0) == gov.get("repos",0) else "warn"}">{gov.get("hooks_installed",0)} / {gov.get("repos",0)} repos</td></tr>
  <tr><td>Trailers Flowing</td><td class="{"ok" if gov.get("trailers_flowing",0) == gov.get("repos",0) else "warn"}">{gov.get("trailers_flowing",0)} / {gov.get("repos",0)} repos</td></tr>
  <tr><td>Open Issues</td><td>{gov.get("issues",0)}</td></tr>
</table>

<div class="footer">
  Generated by Gator {data["version"]} &middot; {data["generated_at"]} &middot;
  Machine: {machine.get("label", "?")} ({machine.get("id", "?")[:8]}) &middot;
  <a href="https://github.com/cumberland-laboratories/gator" style="color: #484f58;">cumberland-laboratories/gator</a>
</div>

</div>
</body>
</html>'''

    return html
