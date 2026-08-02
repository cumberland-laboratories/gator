/**
 * updates.js — Updates view for Gator Dashboard.
 *
 * Checks PyPI for newer versions and upgrades via pipx.
 */

(function () {
  "use strict";

  window.GatorViews = window.GatorViews || {};

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  window.GatorViews.updates = function (data, container) {
    if (window.GATOR_SNAPSHOT) {
      container.innerHTML = `
        <div class="view-header">
          <span class="view-title">Updates</span>
        </div>
        <p class="muted" style="padding:24px; text-align:center;">
          Updates are not available in snapshot mode.
        </p>`;
      return;
    }

    container.innerHTML = `
      <div class="card-row">
        <div class="card">
          <div class="card-label">Installed</div>
          <div class="card-value" id="upd-current">…</div>
        </div>
        <div class="card">
          <div class="card-label">Latest (PyPI)</div>
          <div class="card-value" id="upd-latest">…</div>
        </div>
      </div>

      <div class="section" id="upd-actions">
        <button class="update-btn" id="upd-check-btn" style="padding:6px 16px; font-size:13px;">
          Check for updates
        </button>
        <button class="update-btn" id="upd-upgrade-btn" style="padding:6px 16px; font-size:13px; margin-left:8px; display:none;">
          Upgrade
        </button>
        <span id="upd-activity" style="margin-left:12px; display:inline-block; width:24px;"></span>
        <span id="upd-status" style="margin-left:4px; font-size:13px;"></span>
      </div>

      <div class="section" style="margin-top:16px;">
        <button class="update-btn" id="upd-restart-btn" style="padding:6px 16px; font-size:13px;">
          Restart Dashboard
        </button>
      </div>

      <div id="upd-restart-overlay" style="display:none; position:fixed; inset:0; background:rgba(255,255,255,0.92); z-index:9999; align-items:center; justify-content:center;">
        <div style="text-align:center; font-family:var(--mono); font-size:14px; color:var(--color-muted);">
          <div style="font-size:18px; margin-bottom:8px;">Restarting Dashboard…</div>
          <div id="upd-restart-status">Waiting for server</div>
        </div>
      </div>
    `;

    const checkBtn     = document.getElementById("upd-check-btn");
    const upgradeBtn   = document.getElementById("upd-upgrade-btn");
    const activity     = document.getElementById("upd-activity");
    const statusSpan   = document.getElementById("upd-status");
    const currentEl    = document.getElementById("upd-current");
    const latestEl     = document.getElementById("upd-latest");

    function showWorking() { activity.innerHTML = '<span class="dot-pulse"></span>'; }
    function clearWorking() { activity.innerHTML = ""; }

    // ── check ────────────────────────────────────────────────────────────

    async function checkForUpdates() {
      checkBtn.disabled = true;
      upgradeBtn.style.display = "none";
      statusSpan.textContent = "";
      statusSpan.style.color = "";
      showWorking();

      try {
        const resp = await fetch("/api/updates/check");
        const info = await resp.json();

        currentEl.textContent = info.current_version || "—";
        latestEl.textContent = info.latest_version || "—";

        if (info.update_available) {
          upgradeBtn.style.display = "inline-block";
          statusSpan.textContent = "Update available";
          statusSpan.style.color = "var(--color-drifted, orange)";
        } else if (info.latest_version && info.latest_version !== "unknown") {
          statusSpan.textContent = "Up to date";
          statusSpan.style.color = "var(--color-healthy)";
        }
      } catch (err) {
        statusSpan.textContent = "Check failed";
        statusSpan.style.color = "var(--color-critical)";
      } finally {
        clearWorking();
        checkBtn.disabled = false;
      }
    }

    // ── upgrade ──────────────────────────────────────────────────────────

    async function runUpgrade() {
      upgradeBtn.disabled = true;
      checkBtn.disabled = true;
      statusSpan.textContent = "";
      statusSpan.style.color = "";

      // Show overlay — server will exit, upgrade, and relaunch
      restartOverlay.style.display = "flex";
      restartStatus.textContent = "Upgrading via pipx…";

      try {
        await fetch("/api/updates/upgrade", {
          method: "POST",
          headers: { "X-Gator-Dashboard": "1" },
        });
      } catch (_) {
        // Expected — server exits after responding
      }

      // Poll until the new server comes back
      restartStatus.textContent = "Waiting for upgrade + restart…";
      let attempts = 0;
      const maxAttempts = 60; // pipx upgrade can take a while

      const poll = setInterval(async () => {
        attempts++;
        try {
          const resp = await fetch("/api/updates/check");
          if (resp.ok) {
            clearInterval(poll);
            restartStatus.textContent = "Upgraded. Reloading…";
            setTimeout(() => window.location.reload(), 500);
          }
        } catch (_) {
          restartStatus.textContent = `Upgrading… (${attempts}s)`;
        }
        if (attempts >= maxAttempts) {
          clearInterval(poll);
          restartOverlay.style.display = "none";
          upgradeBtn.disabled = false;
          checkBtn.disabled = false;
          statusSpan.textContent = "Upgrade timed out — check terminal";
          statusSpan.style.color = "var(--color-critical)";
        }
      }, 1000);
    }

    // ── restart ──────────────────────────────────────────────────────────

    const restartBtn     = document.getElementById("upd-restart-btn");
    const restartOverlay = document.getElementById("upd-restart-overlay");
    const restartStatus  = document.getElementById("upd-restart-status");

    async function restartDashboard() {
      restartBtn.disabled = true;
      restartOverlay.style.display = "flex";
      restartStatus.textContent = "Sending restart signal…";

      try {
        await fetch("/api/restart", {
          method: "POST",
          headers: { "X-Gator-Dashboard": "1" },
        });
      } catch (_) {
        // Expected — server dies before response completes
      }

      restartStatus.textContent = "Waiting for server…";
      let attempts = 0;
      const maxAttempts = 30;

      const poll = setInterval(async () => {
        attempts++;
        try {
          const resp = await fetch("/api/updates/check");
          if (resp.ok) {
            clearInterval(poll);
            restartStatus.textContent = "Server is back. Reloading…";
            setTimeout(() => window.location.reload(), 500);
          }
        } catch (_) {
          restartStatus.textContent = `Waiting for server… (${attempts}s)`;
        }
        if (attempts >= maxAttempts) {
          clearInterval(poll);
          restartOverlay.style.display = "none";
          restartBtn.disabled = false;
          statusSpan.textContent = "Restart timed out — restart manually";
          statusSpan.style.color = "var(--color-critical)";
        }
      }, 1000);
    }

    // ── wire up ──────────────────────────────────────────────────────────

    checkBtn.addEventListener("click", checkForUpdates);
    upgradeBtn.addEventListener("click", runUpgrade);
    restartBtn.addEventListener("click", restartDashboard);

    // Auto-check on view load
    checkForUpdates();
  };
})();
