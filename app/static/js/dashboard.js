(function () {
  fetch("/api/dashboard")
    .then((r) => r.json())
    .then((d) => {
      const h = d.health;
      document.getElementById("cards").innerHTML = `
      <div class="o_stat_card"><h3>Status</h3><p class="val ${d.status === "ok" ? "ok" : "warn"}">${d.status === "ok" ? "OK" : "Degradacja"}</p></div>
      <div class="o_stat_card"><h3>Bielik (LLM)</h3><p class="val ${h.llm.ok ? "ok" : "warn"}">${h.llm.ok ? "OK" : "Offline"}</p></div>
      <div class="o_stat_card"><h3>SearXNG</h3><p class="val ${h.searxng.ok ? "ok" : "warn"}">${h.searxng.ok ? "OK" : "Offline"}</p></div>
      <div class="o_stat_card"><h3>Scrapery</h3><p class="val ${h.scrapers.ok ? "ok" : "warn"}">${h.scrapers.ok ? "OK" : "Problem"}</p></div>
      <div class="o_stat_card"><h3>Profil</h3><p class="val">${d.profile.sections_done.length}/9</p></div>
      <div class="o_stat_card"><h3>Oferty</h3><p class="val"><a href="/inbox">${d.seen_jobs_new} nowych</a> / ${d.seen_jobs_total}</p></div>`;

      const scrapes = (d.recent_scrapes || [])
        .slice(0, 5)
        .map(
          (s) =>
            `<li>${esc((s.started_at || s.timestamp || "").slice(0, 16))} — ${esc(s.query || s.mode || "batch")} (${s.new_jobs ?? s.count ?? "?"} nowych)</li>`
        )
        .join("");
      document.getElementById("scrapes").innerHTML = scrapes
        ? `<ul class="o_dashboard_list">${scrapes}</ul>`
        : "<p class='o_muted'>Brak ostatnich scrape</p>";

      const applies = (d.recent_applies || [])
        .slice(0, 5)
        .map(
          (a) =>
            `<li>${esc((a.started_at || a.updated_at || "").slice(0, 16))} — ${esc(a.company || "")} ${esc(a.role || "")}</li>`
        )
        .join("");
      document.getElementById("applies").innerHTML = applies
        ? `<ul class="o_dashboard_list">${applies}</ul>`
        : "<p class='o_muted'>Brak ostatnich aplikacji</p>";
    });

  fetch("/api/jobs?status=new&fit=high")
    .then((r) => r.json())
    .then((d) => {
      const rows = (d.jobs || [])
        .slice(0, 5)
        .map(
          (j) =>
            `<li><span class="fit-high">${esc(t("fit", j.fit))}</span> ${esc(j.title)} — ${esc(j.company)} <a href="${esc(j.url)}" target="_blank" rel="noopener">link</a></li>`
        )
        .join("");
      document.getElementById("jobPreview").innerHTML = rows
        ? `<ul class="o_dashboard_list">${rows}</ul><p><a href="/inbox" class="btn btn-primary btn-sm">Inbox</a></p>`
        : "<p class='o_muted'>Brak nowych ofert wysokiego dopasowania. <a href='/scrape'>Uruchom scrape</a></p>";
    });
})();
