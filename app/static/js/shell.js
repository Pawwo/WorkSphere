/* Odoo-like shell — sidebar, badges, settings toggle */

function initShell() {
  const sidebar = document.getElementById("oSidebar");
  const toggle = document.getElementById("oMenuToggle");
  if (toggle && sidebar) {
    toggle.addEventListener("click", () => sidebar.classList.toggle("open"));
  }

  const settingsBtn = document.getElementById("oSettingsToggle");
  const settingsSub = document.getElementById("oSettingsSub");
  if (settingsBtn && settingsSub) {
    const stored = localStorage.getItem("settingsOpen");
    if (stored === "1") {
      settingsBtn.classList.add("open");
      settingsSub.classList.add("open");
      settingsBtn.setAttribute("aria-expanded", "true");
    }
    settingsBtn.addEventListener("click", () => {
      settingsBtn.classList.toggle("open");
      settingsSub.classList.toggle("open");
      const open = settingsSub.classList.contains("open");
      settingsBtn.setAttribute("aria-expanded", open ? "true" : "false");
      localStorage.setItem("settingsOpen", open ? "1" : "0");
    });
  }

  const active = document.body.dataset.active;
  if (
    active &&
    ["setup", "documents", "profile", "scrape", "tools", "dashboard"].includes(active)
  ) {
    if (settingsBtn && settingsSub) {
      settingsBtn.classList.add("open");
      settingsSub.classList.add("open");
      settingsBtn.setAttribute("aria-expanded", "true");
    }
  }

  loadInboxBadge();
  loadTrackerBadge();
}

async function loadInboxBadge() {
  const badge = document.getElementById("inboxBadge");
  if (!badge) return;
  try {
    const d = await fetch("/api/workflow/counts").then((r) => r.json());
    const n = d.new ?? 0;
    badge.textContent = n;
    badge.style.display = "";
  } catch (_) {
    /* ignore */
  }
}

async function loadTrackerBadge() {
  const badge = document.getElementById("trackerBadge");
  if (!badge) return;
  try {
    const d = await fetch("/api/applications/counts").then((r) => r.json());
    const n = d.total ?? 0;
    badge.textContent = n;
    badge.style.display = "";
  } catch (_) {
    /* ignore */
  }
}

document.addEventListener("DOMContentLoaded", initShell);
