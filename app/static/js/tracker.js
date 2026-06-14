(function () {
  const KANBAN_STAGES = window.HIRING_STAGES || [
    "draft",
    "ready_to_send",
    "applied",
    "screening",
    "interview",
    "offer",
    "rejected",
    "archived",
  ];
  let apps = [];
  let currentView = "list";

  function renderList() {
    const tbody = document.querySelector("#tracker tbody");
    if (!apps.length) {
      tbody.innerHTML =
        '<tr><td colspan="7" class="o_muted" style="text-align:center;padding:24px">Brak aplikacji</td></tr>';
      return;
    }
    tbody.innerHTML = apps
      .map(
        (a) => `<tr>
      <td>${esc((a.updated_at || "").slice(0, 10))}</td>
      <td>${esc(a.company)}</td>
      <td>${esc(a.role)}</td>
      <td><span class="badge">${esc(t("hiring_stage", a.hiring_stage))}</span></td>
      <td>${esc(t("pipeline_stage", a.pipeline_stage))}</td>
      <td>${esc(t("fit", a.overall_fit) || "—")}</td>
      <td><a href="/applications/${a.id}" class="btn btn-link btn-sm">Otwórz</a></td>
    </tr>`
      )
      .join("");
  }

  function renderKanban() {
    const el = document.getElementById("kanbanView");
    const byStage = {};
    KANBAN_STAGES.forEach((s) => {
      byStage[s] = [];
    });
    apps.forEach((a) => {
      const s = a.hiring_stage || "draft";
      if (byStage[s]) byStage[s].push(a);
      else byStage.draft.push(a);
    });
    el.innerHTML = KANBAN_STAGES.map(
      (stage) => `
      <div class="o_kanban_column" data-stage="${stage}">
        <h4>${esc(t("hiring_stage", stage))} (${byStage[stage].length})</h4>
        ${byStage[stage]
          .map(
            (a) => `
          <div class="o_kanban_card" draggable="true" data-id="${a.id}">
            <h5>${esc(a.company)}</h5>
            <div class="o_muted" style="font-size:12px">${esc(a.role)}</div>
            <div style="margin-top:4px"><span class="badge badge-fit-${a.overall_fit || "medium"}">${esc(t("fit", a.overall_fit) || "—")}</span></div>
            <a href="/applications/${a.id}" class="btn btn-link btn-sm">Szczegóły</a>
          </div>`
          )
          .join("")}
      </div>`
    ).join("");
    el.querySelectorAll(".o_kanban_card").forEach((card) => {
      card.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("application/id", card.dataset.id);
      });
    });
    el.querySelectorAll(".o_kanban_column").forEach((col) => {
      col.addEventListener("dragover", (e) => e.preventDefault());
      col.addEventListener("drop", async (e) => {
        e.preventDefault();
        const id = e.dataTransfer.getData("application/id");
        const stage = col.dataset.stage;
        await fetch("/api/applications/" + id, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ hiring_stage: stage }),
        });
        showToast("Przeniesiono: " + t("hiring_stage", stage));
        loadTracker();
      });
    });
  }

  async function loadTracker() {
    const hiring = document.getElementById("fHiring").value;
    let url = "/api/applications?limit=200";
    if (hiring) url += "&hiring_stage=" + hiring;
    const d = await fetch(url).then((r) => r.json());
    apps = d.applications || [];
    document.getElementById("summary").textContent = apps.length + " aplikacji";
    if (currentView === "list") renderList();
    else renderKanban();
    if (typeof loadTrackerBadge === "function") loadTrackerBadge();
  }

  document.getElementById("viewTabs").onclick = (e) => {
    const tab = e.target.closest(".o_tab");
    if (!tab) return;
    document.querySelectorAll("#viewTabs .o_tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    currentView = tab.dataset.view;
    document.getElementById("listView").classList.toggle("hidden", currentView !== "list");
    document.getElementById("kanbanView").classList.toggle("hidden", currentView !== "kanban");
    if (currentView === "kanban") renderKanban();
    else renderList();
  };

  document.getElementById("reload").onclick = loadTracker;
  document.getElementById("fHiring").onchange = loadTracker;
  loadTracker();
})();
