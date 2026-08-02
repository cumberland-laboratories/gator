---
generated: 2026-06-07
generator: field-guide-gen-v1
type: pi-tutorial
language: javascript
source-charters: [scripts-dashboard]
patterns: javascript-patterns.md
---

# JavaScript Tutorial

Companion to [javascript-patterns.md](javascript-patterns.md). Real code snippets from the dashboard JS files, with rationale and charter connections. Read this to restore sharpness on the frontend idioms used here.

### IIFE Encapsulation

**Charter connection**: Dashboard — Architecture Rule (business logic stays in CLI scripts)

From `dashboard.js`:
```javascript
(function () {
  "use strict";

  const state = {
    data: null,
    activeView: "fleet",
    activeRepo: null,
  };

  // ... all code lives inside this closure ...
})();
```

**Why it matters**: Without the IIFE, every variable and function would pollute the global scope. Since the dashboard loads 5 JS files sequentially, name collisions between `escHtml`, helper functions, or loop variables would cause silent bugs. The IIFE also enables strict mode per-file.

**What to watch for**: Any new JS file that doesn't start with `(function () { "use strict";` and end with `})();`.

### View Registration

**Charter connection**: Dashboard — view routing in dashboard.js

From `fleet.js`:
```javascript
window.GatorViews = window.GatorViews || {};

window.GatorViews.fleet = function (data, container) {
  const fleet = data.fleet || {};
  // ... build HTML, assign to container.innerHTML ...
};
```

From `repo.js` (async variant):
```javascript
window.GatorViews.repo = async function (data, container, repoName) {
  container.innerHTML = `<div class="repo-spinner">Loading repo status…</div>`;
  const resp = await fetch(`/api/repo/${encodeURIComponent(repoName)}`);
  // ...
};
```

**Why it matters**: The dashboard shell (`dashboard.js`) dispatches to views by name: `views[name](state.data, viewSlot)`. This registry pattern means adding a new view is just a new file that registers itself — no imports, no build step, no modification to the shell. The `|| {}` guard ensures load order doesn't matter between view files.

**What to watch for**: A new view file that forgets the `window.GatorViews = window.GatorViews || {};` guard, or that uses a different function signature.

### escHtml for All Dynamic Content

**Charter connection**: Dashboard — Architecture Rule (security)

From `fleet.js`:
```javascript
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
```

Used everywhere data enters HTML:
```javascript
html += `<td>${escHtml(repo.name)}</td>`;
html += `<button class="link-btn" onclick="window.gatorNavToRepo('${escHtml(repo.name)}')">${escHtml(repo.name)}</button>`;
```

**Why it matters**: The dashboard renders server data (repo names, commit messages, trailers) directly into HTML strings. Without escaping, a repo named `<script>alert(1)</script>` would execute. Every view defines its own copy because there's no shared module system — this is deliberate (no build step, no framework).

**What to watch for**: Any template literal that inserts `${variable}` into innerHTML without wrapping it in `escHtml()`. The duplication is intentional — don't try to extract it into a shared file.

### X-Gator-Dashboard Header on POSTs

**Charter connection**: Dashboard — `_check_post_auth()` function entry

From `fleet.js`:
```javascript
const resp = await fetch(`/api/repo/${encodeURIComponent(repoName)}/update`, {
  method: "POST",
  headers: { "X-Gator-Dashboard": "1" },
});
```

From `updates.js`:
```javascript
const fetchResp = await fetch("/api/updates/fetch", {
  method: "POST",
  headers: { "X-Gator-Dashboard": "1" },
});
```

**Why it matters**: The dashboard is a localhost HTTP server. Without protection, any webpage the user visits can POST to `localhost:8420` and trigger repo writes (gator-update, git pull). Browsers enforce CORS: a cross-origin `fetch()` with a custom header triggers a preflight OPTIONS request, which the server doesn't answer — so the browser blocks the POST. Simple form submissions and `<img>` embeds can't send custom headers at all. This single header closes the entire CSRF attack surface.

**What to watch for**: Any new `fetch()` with `method: "POST"` that forgets the `X-Gator-Dashboard` header. Also: never add a CORS handler or OPTIONS route to the server — that would reopen the attack surface.

### Snapshot Mode Guard

**Charter connection**: Dashboard — Snapshot banner entry; Update button entry

From `fleet.js`:
```javascript
const isSnapshot = !!window.GATOR_SNAPSHOT;

// In table header:
${isSnapshot ? "" : "<th>Update</th>"}

// In row cells:
${isSnapshot ? "" : `<td class="update-cell">${updateBtn}...</td>`}
```

From `updates.js`:
```javascript
if (window.GATOR_SNAPSHOT) {
  container.innerHTML = `...Updates are not available in snapshot mode...`;
  return;
}
```

**Why it matters**: Snapshot mode produces a self-contained HTML file with inline data — no server, no API. Write controls (Update buttons, Pull button) would be dead UI at best, and they'd muddy the dashboard's read-only contract. The banner (`#snapshot-banner`) is a sibling of `#view-slot`, not a child, so `showView()` clearing the slot doesn't destroy it.

**What to watch for**: Any new write control (button, form, POST-triggering element) that doesn't check `window.GATOR_SNAPSHOT` before rendering.

### Health Badge Semantics

**Charter connection**: Dashboard — Health badge and summary card "Drifted" definition

From `fleet.js`:
```javascript
function repoHealth(fleetRepo, driftSeverity) {
  if (!fleetRepo.gatorized) {
    return { label: "Ungoverned", cls: "badge-ungoverned" };
  }
  if (!fleetRepo.hooks_installed) {
    return { label: "Hook missing", cls: "badge-critical" };
  }
  if (driftSeverity === "drift") {
    return { label: "Drifted", cls: "badge-drifted" };
  }
  return { label: "Healthy", cls: "badge-healthy" };
}

// Summary card must match:
const driftedCount = (drift.repos || []).filter(r => r.severity === "drift").length;
```

**Why it matters**: This was a bug twice during development. The natural instinct is to map `warn` to `Drifted`, but the plan definition is precise: "Drifted = Hook present AND policy drift detected." `warn` covers charter gaps, stale templates, branch read failures — governance hygiene, not policy drift. Those surface in the Policy Drift column. If the badge and the summary card use different filters, the numbers disagree and the dashboard looks broken.

**What to watch for**: Any change to `repoHealth()` that doesn't also update `driftedCount`, or vice versa.

### Stale Sources Not Covers

**Charter connection**: Dashboard — Stale charters panel entry

From `repo.js`:
```javascript
function renderStaleCharters(staleList) {
  // ...
  for (const item of staleList) {
    // CORRECT: iterate stale_sources (files actually newer than charter)
    for (const sf of (item.stale_sources || [])) {
      html += `<li class="stale-file">${escHtml(sf)}</li>`;
    }
  }
}
```

**Why it matters**: `gator-repo-status.py` returns both `covers` (all files a charter declares) and `stale_sources` (only the files that are actually newer than the charter's last update). A charter that covers 10 files but has only 1 stale file should show 1 stale file, not 10. Using `covers` instead of `stale_sources` overstates staleness and makes the dashboard alarmist.

**What to watch for**: Any reference to `item.covers` in the stale charters rendering path.

### Null-Safe Data Extraction

**Charter connection**: Dashboard — Architecture Rule (thin renderer over JSON)

From `fleet.js`:
```javascript
const repos   = fleet.repos   || [];
const summary = fleet.summary || {};

const driftedCount = (drift.repos || []).filter(r => r.severity === "drift").length;
const governedTotal = (audit.governed_commits || {}).total || 0;
```

**Why it matters**: Each CLI script returns its own JSON independently. If one fails, its key contains `{"error": "..."}` but the other keys are fine. The dashboard must render gracefully with partial data — a fleet-report timeout shouldn't crash the audit view. The `|| []` / `|| {}` pattern ensures iteration and property access never throw on undefined.

**What to watch for**: Any `data.something.nested` access without a fallback at each level. Also watch for `.filter()` or `.map()` called on a potentially undefined array.

### parseSummaryLine Priority

**Charter connection**: Dashboard — parseSummaryLine entry

From `fleet.js`:
```javascript
function parseSummaryLine(output) {
  if (!output) return "Done";
  const lines = output.split("\n").map(l => l.trim()).filter(Boolean);
  const policy = lines.find(l => l.startsWith("Policy version:"));
  if (policy) return policy;
  const done = lines.find(l => l.startsWith("Done:"));
  if (done) return done;
  const current = lines.find(l => l.includes("Everything is current"));
  if (current) return "Already current";
  return "Done";
}
```

**Why it matters**: The Update button shows one line of result inline. When gator-update bumps the policy version, that's the most informative signal ("Policy version: bumped to 2026-05-29"). The "Done: 3 added, 2 updated" line is secondary. Reordering would hide the policy bump behind generic counts.

**What to watch for**: Changes to the priority order, or new gator-update output lines that should be prioritized.

### Disabled Button During Async

**Charter connection**: Dashboard — Update button entry

From `fleet.js`:
```javascript
btn.addEventListener("click", async function () {
  this.disabled = true;
  this.textContent = "Updating…";
  resultSpan.textContent = "";

  try {
    // ... async work ...
  } catch (err) {
    // ... error display ...
  }

  this.disabled = false;
  this.textContent = "↑ Update";
});
```

**Why it matters**: Without disabling, a double-click fires two concurrent gator-update runs on the same repo. The text change gives visual feedback that the action is in progress. The restore happens outside try/catch so the button always returns to usable state.

**What to watch for**: Any new async button handler that doesn't disable the button before starting work.
