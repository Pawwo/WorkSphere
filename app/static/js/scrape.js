(function () {
  const logEl = document.getElementById("sseLog");
  const log = (m) => {
    logEl.textContent += m + "\n";
  };
  const fill = document.getElementById("sseFill");

  function renderJobTable(jobs) {
    if (!jobs || !jobs.length) {
      document.getElementById("resultsTable").innerHTML =
        "<p class='o_muted'>Brak nowych ofert w tym uruchomieniu.</p>";
      return;
    }
    const high = jobs.filter((j) => j.fit === "high").length;
    const med = jobs.filter((j) => j.fit === "medium").length;
    const low = jobs.filter((j) => j.fit === "low").length;
    let html = `<h2>Nowe dopasowania</h2><p>Znaleziono ${jobs.length} ofert (${high} wysokie, ${med} średnie, ${low} niskie).</p>`;
    html +=
      '<table class="jobs"><thead><tr><th>#</th><th>Fit</th><th>Tytuł</th><th>Firma</th><th>Lokalizacja</th><th>URL</th></tr></thead><tbody>';
    jobs.forEach((j, i) => {
      html += `<tr><td>${i + 1}</td><td class="fit-${j.fit}">${esc(t("fit", j.fit))}</td><td>${esc(j.title)}</td><td>${esc(j.company || "")}</td><td>${esc(j.location || "—")}</td><td><a href="${esc(j.url)}" target="_blank" rel="noopener">Link</a></td></tr>`;
    });
    html += '</tbody></table><p><a href="/inbox" class="btn btn-primary">Przejdź do Inbox</a></p>';
    document.getElementById("resultsTable").innerHTML = html;
  }

  function scrapeOpts(forBatch) {
    const opts = {
      limit: +document.getElementById("limit").value,
      days: +document.getElementById("days").value,
    };
    if (forBatch) {
      const allCats = document.getElementById("allCategories").checked;
      opts.broad = allCats;
      opts.max_categories = allCats ? 99 : 3;
    } else {
      opts.broad = document.getElementById("broad").checked;
    }
    return opts;
  }

  function watchTask(task_id) {
    log("Zadanie: " + task_id);
    watchSseTask(
      task_id,
      (d) => {
        if (d.progress != null) fill.style.width = d.progress + "%";
        if (d.message) log((d.progress != null ? d.progress + "% — " : "") + d.message);
      },
      (d) => {
        if (d.status === "completed") {
          const jobs = d.result?.new_jobs || d.result?.results || [];
          renderJobTable(jobs);
        }
        if (d.status === "failed") log("BŁĄD: " + (d.error || d.message));
      }
    );
  }

  async function loadBatchPreview() {
    const allCats = document.getElementById("allCategories").checked;
    const r = await fetch(
      "/api/scrape/batch/preview?max_categories=" + (allCats ? 99 : 3)
    );
    const d = await r.json();
    const nPortals = (d.portals || []).length;
    const profile = d.portal_profile || "full";
    document.getElementById("batchInfo").textContent = d.count
      ? `${d.count} zapytań × ${nPortals} portali (${profile})`
      : "Brak zapytań — uzupełnij profil (sekcja 9) lub search-queries.md";
    const src = document.getElementById("batchSource");
    if (src)
      src.textContent = d.categories?.length ? "Kategorie: " + d.categories.join(", ") : "";
    document.getElementById("batchQueries").innerHTML = (d.queries || [])
      .map((q) => `<li>${esc(q)}</li>`)
      .join("");
    const batchBtn = document.getElementById("runBatch");
    batchBtn.disabled = !d.count;
    batchBtn.title = d.count ? "" : "Uzupełnij search-queries.md lub profil";
  }

  document.getElementById("allCategories").onchange = loadBatchPreview;

  document.getElementById("refreshQueries").onclick = async () => {
    const btn = document.getElementById("refreshQueries");
    setButtonLoading(btn, true, "Odświeżam…");
    try {
      await apiFetch("/api/setup/regenerate-search-queries", { method: "POST" });
      await loadBatchPreview();
      log("Odświeżono search-queries.md z profilu.");
    } catch (e) {
      log("BŁĄD: " + e.message);
    } finally {
      setButtonLoading(btn, false);
      btn.textContent = "Odśwież z profilu";
    }
  };

  document.getElementById("run").onclick = async () => {
    logEl.textContent = "";
    document.getElementById("resultsTable").innerHTML = "";
    document.getElementById("ssePanel").classList.remove("hidden");
    fill.style.width = "0%";
    const body = { query: document.getElementById("query").value || "developer", ...scrapeOpts(false) };
    const { task_id } = await apiFetch("/api/scrape/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    watchTask(task_id);
  };

  document.getElementById("runBatch").onclick = async () => {
    logEl.textContent = "";
    document.getElementById("resultsTable").innerHTML = "";
    document.getElementById("ssePanel").classList.remove("hidden");
    fill.style.width = "0%";
    const body = scrapeOpts(true);
    const data = await apiFetch("/api/scrape/batch/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    watchTask(data.task_id);
  };

  loadBatchPreview().catch((e) => {
    document.getElementById("batchInfo").textContent = String(e);
  });
})();
