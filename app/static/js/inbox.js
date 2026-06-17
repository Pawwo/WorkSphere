(function () {
  let currentTier = "priority";
  let currentView = "cards";
  let jobs = [];
  let focusedIdx = 0;
  let pendingSkip = null;
  let sortCol = "first_seen";
  let sortDir = "desc";

  const qs = new URLSearchParams(location.search);
  if (qs.get("view") === "table") currentView = "table";

  const skipDialog = document.getElementById("skipReasonDialog");
  const skipForm = document.getElementById("skipReasonForm");
  const skipFormError = document.getElementById("skipFormError");

  function scoreClass(s) {
    if (s == null) return "none";
    if (s >= 40) return "high";
    if (s >= 15) return "mid";
    return "low";
  }

  function hasExternalUrl(j) {
    return Boolean(j.url && /^https?:\/\//i.test(j.url));
  }

  function jobRef(j) {
    return j.url || j.key || "";
  }

  function tierBadge(tier) {
    const map = { priority: "badge-priority", review: "badge-review", skip: "badge-skip" };
    const label = t("tier", tier) || tier;
    return tier ? `<span class="badge ${map[tier] || ""}">${esc(label)}</span>` : "";
  }

  function fitBadge(f) {
    return `<span class="badge badge-fit-${f}">${esc(t("fit", f))}</span>`;
  }

  function piBadge(j) {
    if (j.pi_score == null && !j.pi_verdict) return "";
    const score = j.pi_score != null ? ` ${j.pi_score}` : "";
    const verdict = j.pi_verdict ? ` ${j.pi_verdict}` : "";
    return `<span class="badge badge-review" title="Pi${j.pi_app ? " · " + j.pi_app : ""}">Pi${score}${verdict}</span>`;
  }

  function statusBadge(s) {
    return `<span class="badge badge-status-${s}">${esc(t("job_status", s))}</span>`;
  }

  function skipSourceBadge(sr) {
    if (!sr || !sr.source) return "";
    const cls = sr.source === "auto_triage" ? "badge-skip-auto" : "badge-skip-manual";
    const label = t("skip_source", sr.source) || sr.source;
    return `<span class="badge ${cls}">${esc(label)}</span>`;
  }

  function formatTriageTokens(raw) {
    if (!raw) return "";
    return raw
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((token) => {
        const base = token.split(":")[0];
        return t("triage_reason_token", base) || t("triage_reason_token", token) || token;
      })
      .join(", ");
  }

  function formatManualReasonItem(item) {
    const catLabel = t("skip_reason", item.category) || item.category;
    const parts = [esc(catLabel)];
    if (item.category === "wrong_scoring") {
      if (item.correct_fit) parts.push(`fit: ${esc(t("fit", item.correct_fit))}`);
      if (item.correct_score != null) parts.push(`wynik: ${item.correct_score}`);
    } else if (item.category === "missing_skill" && item.missing_item) {
      parts.push(esc(item.missing_item));
    } else if (item.category === "domain_knowledge" && item.domain_note) {
      parts.push(esc(item.domain_note));
    } else if (item.category === "salary_low" && item.salary_note) {
      parts.push(esc(item.salary_note));
    } else if (item.category === "other" && item.comment) {
      parts.push(esc(item.comment));
    }
    return parts.join(" · ");
  }

  function manualSkipReasons(sr) {
    if (Array.isArray(sr.reasons) && sr.reasons.length) return sr.reasons;
    if (sr.category && sr.source === "manual") {
      return [
        {
          category: sr.category,
          correct_fit: sr.correct_fit,
          correct_score: sr.correct_score,
          missing_item: sr.missing_item,
          domain_note: sr.domain_note,
          salary_note: sr.salary_note,
          comment: sr.comment,
        },
      ];
    }
    return [];
  }

  function formatSkipReason(j) {
    const sr = j.skip_reason;
    if (!sr) {
      if (j.triage_reason && j.status === "skipped") {
        return `<div class="o_job_reason">${esc(formatTriageTokens(j.triage_reason))}</div>`;
      }
      return "";
    }
    if (sr.source === "manual") {
      const items = manualSkipReasons(sr).map(formatManualReasonItem).filter(Boolean);
      if (!items.length) return "";
      return `<div class="o_job_reason">${skipSourceBadge(sr)} ${items.join(" · ")}</div>`;
    }
    const catLabel = t("skip_reason", sr.category) || sr.category;
    const parts = [esc(catLabel)];
    if (sr.triage_score != null) parts.push(`wynik triażu: ${sr.triage_score}`);
    if (sr.triage_reason) parts.push(esc(formatTriageTokens(sr.triage_reason)));
    return `<div class="o_job_reason">${skipSourceBadge(sr)} ${parts.join(" · ")}</div>`;
  }

  function salaryLine(j) {
    if (!j.salary_b2b_monthly) return "";
    const warn = j.salary_meets_threshold === false ? " ⚠ poniżej progu" : "";
    return ` · ${j.salary_b2b_monthly.toLocaleString("pl-PL")} PLN B2B/mies.${warn}`;
  }

  function parseIsoDay(iso) {
    if (!iso || typeof iso !== "string") return null;
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return null;
    const y = Number(m[1]);
    const mo = Number(m[2]);
    const d = Number(m[3]);
    if (!y || !mo || !d) return null;
    return { y, mo, d, key: y * 10000 + mo * 100 + d };
  }

  function formatFirstSeen(iso) {
    const day = parseIsoDay(iso);
    if (!day) return "—";
    return `${String(day.d).padStart(2, "0")}.${String(day.mo).padStart(2, "0")}.${day.y}`;
  }

  function reasonSortKey(j) {
    const sr = j.skip_reason;
    if (sr) {
      const cat = sr.category || "";
      const tr = sr.triage_reason || "";
      return `${cat} ${tr}`.trim().toLowerCase();
    }
    return String(j.triage_reason || "").trim().toLowerCase();
  }

  function compareNullableNumber(a, b) {
    const na = a == null ? null : Number(a);
    const nb = b == null ? null : Number(b);
    const aMissing = na == null || Number.isNaN(na);
    const bMissing = nb == null || Number.isNaN(nb);
    if (aMissing && bMissing) return 0;
    if (aMissing) return 1;
    if (bMissing) return -1;
    return na - nb;
  }

  function fitRank(f) {
    if (f === "high") return 3;
    if (f === "medium") return 2;
    if (f === "low") return 1;
    return 0;
  }

  function compareJobs(a, b, col) {
    if (col === "row") return a.__row - b.__row;
    if (col === "tier") return String(a.tier || "").localeCompare(String(b.tier || ""), "pl");
    if (col === "triage_score") return compareNullableNumber(a.triage_score, b.triage_score);
    if (col === "quick_fit") return fitRank(a.quick_fit) - fitRank(b.quick_fit);
    if (col === "salary_b2b_monthly") return compareNullableNumber(a.salary_b2b_monthly, b.salary_b2b_monthly);
    if (col === "first_seen") {
      const ka = parseIsoDay(a.first_seen)?.key ?? 0;
      const kb = parseIsoDay(b.first_seen)?.key ?? 0;
      return ka - kb;
    }
    if (col === "title") return String(a.title || "").localeCompare(String(b.title || ""), "pl");
    if (col === "company") return String(a.company || "").localeCompare(String(b.company || ""), "pl");
    if (col === "location") return String(a.location || "").localeCompare(String(b.location || ""), "pl");
    if (col === "status") return String(a.status || "").localeCompare(String(b.status || ""), "pl");
    if (col === "reason") return reasonSortKey(a).localeCompare(reasonSortKey(b), "pl");
    return 0;
  }

  function applyCurrentSort() {
    if (!Array.isArray(jobs) || !jobs.length) return;
    const decorated = jobs.map((j, i) => ({ ...j, __row: i }));
    decorated.sort((a, b) => {
      const dir = sortDir === "desc" ? -1 : 1;
      const cmp = compareJobs(a, b, sortCol);
      if (cmp !== 0) return cmp * dir;
      return (a.__row - b.__row) * dir;
    });
    jobs = decorated.map(({ __row, ...rest }) => rest);
  }

  function emptyState() {
    return `<div class="o_empty_state">
      <h2>Brak ofert</h2>
      <p>Zmień filtry lub uruchom scrape / triaż.</p>
      <p><a href="/scrape" class="btn btn-primary">Scrapowanie</a></p>
    </div>`;
  }

  function renderCards() {
    const list = document.getElementById("jobList");
    if (!jobs.length) {
      list.innerHTML = emptyState();
      return;
    }
    list.innerHTML = jobs
      .map((j, i) => {
        const sc = j.triage_score != null ? j.triage_score : "—";
        const meta = [esc(j.company), j.portal, j.location].filter(Boolean).join(" · ");
        const extra =
          j.deadline || (j.highlights && j.highlights.length)
            ? `<div class="o_job_reason">${esc(j.deadline || "")}${j.highlights ? " " + esc(j.highlights.slice(0, 2).join("; ")) : ""}</div>`
            : "";
        const showTriageReason = j.triage_reason && j.status !== "skipped" && !j.skip_reason;
        const descPreview =
          !hasExternalUrl(j) && j.description
            ? `<div class="o_job_reason o_job_desc">${esc(j.description.slice(0, 240))}${j.description.length > 240 ? "…" : ""}</div>`
            : "";
        const ref = jobRef(j);
        const titleHtml = hasExternalUrl(j)
          ? `<a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a>`
          : esc(j.title);
        const openBtn = hasExternalUrl(j)
          ? `<a href="${esc(j.url)}" target="_blank" rel="noopener" class="btn btn-secondary btn-sm">Otwórz</a>`
          : "";
        return `<article class="o_job_card${i === focusedIdx ? " focused" : ""}" data-idx="${i}" data-url="${esc(ref)}">
        <div class="o_score ${scoreClass(j.triage_score)}">${sc}</div>
        <div>
          <div class="o_badges">${tierBadge(j.tier)} ${fitBadge(j.quick_fit)} ${piBadge(j)} ${statusBadge(j.status)}</div>
          <p class="o_job_title">${titleHtml}</p>
          <div class="o_job_meta">${esc(meta)}${salaryLine(j)}</div>
          ${showTriageReason ? `<div class="o_job_reason">${esc(j.triage_reason)}</div>` : ""}
          ${descPreview}
          ${formatSkipReason(j)}
          ${extra}
        </div>
        <div class="o_job_actions">
          <a href="/apply?url=${encodeURIComponent(ref)}" class="btn btn-primary btn-sm">Aplikuj</a>
          ${openBtn}
          <button type="button" class="btn btn-secondary btn-sm" data-act="skip">Pomiń</button>
          <button type="button" class="btn btn-link btn-sm" data-act="evaluate">Oceń</button>
        </div>
      </article>`;
      })
      .join("");
  }

  function renderTable() {
    const wrap = document.getElementById("jobTableWrap");
    if (!jobs.length) {
      wrap.innerHTML = emptyState();
      return;
    }
    const rows = jobs
      .map(
        (j, i) => `<tr data-idx="${i}">
      <td>${i + 1}</td>
      <td>${tierBadge(j.tier)}</td>
      <td>${j.triage_score != null ? j.triage_score : "—"}</td>
      <td>${fitBadge(j.quick_fit)} ${piBadge(j)}</td>
      <td>${j.salary_b2b_monthly ? j.salary_b2b_monthly.toLocaleString("pl-PL") : "—"}</td>
      <td>${formatFirstSeen(j.first_seen)}</td>
      <td>${hasExternalUrl(j) ? `<a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a>` : esc(j.title)}</td>
      <td>${esc(j.company)}</td>
      <td>${esc(j.location || "—")}</td>
      <td>${statusBadge(j.status)}</td>
      <td class="o_table_reason">${formatSkipReason(j) || (j.triage_reason ? esc(j.triage_reason) : "—")}</td>
      <td>
        <a href="/apply?url=${encodeURIComponent(jobRef(j))}" class="btn btn-link btn-sm">Aplikuj</a>
        <button type="button" class="btn btn-link btn-sm" data-skip="${esc(jobRef(j))}" data-title="${esc(j.title)}">Pomiń</button>
      </td>
    </tr>`
      )
      .join("");
    const arrow = sortDir === "desc" ? "▼" : "▲";
    const th = (label, col) => {
      const active = sortCol === col;
      const cls = `o_sortable${active ? " o_sort_active" : ""}`;
      const suffix = active ? ` <span class="o_sort_arrow" aria-hidden="true">${arrow}</span>` : "";
      return `<th class="${cls}" data-sort="${esc(col)}" role="button" tabindex="0">${esc(label)}${suffix}</th>`;
    };
    wrap.innerHTML = `<table class="jobs"><thead><tr>
      ${th("#", "row")}
      ${th("Tier", "tier")}
      ${th("Score", "triage_score")}
      ${th("Fit", "quick_fit")}
      ${th("B2B/mies.", "salary_b2b_monthly")}
      ${th("Data", "first_seen")}
      ${th("Tytuł", "title")}
      ${th("Firma", "company")}
      ${th("Lokalizacja", "location")}
      ${th("Status", "status")}
      ${th("Powód", "reason")}
      <th>Akcje</th>
    </tr></thead><tbody>${rows}</tbody></table>`;

    const thead = wrap.querySelector("thead");
    if (thead) {
      thead.onclick = (e) => {
        const target = e.target && e.target.nodeType === 1 ? e.target : e.target?.parentElement;
        const thEl = target ? target.closest("th[data-sort]") : null;
        if (!thEl) return;
        const col = thEl.dataset.sort;
        if (!col) return;
        if (sortCol === col) sortDir = sortDir === "asc" ? "desc" : "asc";
        else {
          sortCol = col;
          sortDir = "asc";
        }
        applyCurrentSort();
        renderView();
      };
      thead.onkeydown = (e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        const target = e.target && e.target.nodeType === 1 ? e.target : e.target?.parentElement;
        const thEl = target ? target.closest("th[data-sort]") : null;
        if (!thEl) return;
        e.preventDefault();
        thEl.click();
      };
    }
  }

  function renderView() {
    const list = document.getElementById("jobList");
    const table = document.getElementById("jobTableWrap");
    list.classList.toggle("hidden", currentView !== "cards");
    table.classList.toggle("hidden", currentView !== "table");
    if (currentView === "cards") renderCards();
    else renderTable();
  }

  function selectedSkipCategories() {
    return [...skipForm.querySelectorAll('input[name="skipCategory"]:checked')].map((el) => el.value);
  }

  function updateSkipConditionalFields() {
    const cats = new Set(selectedSkipCategories());
    document.getElementById("skipFieldsWrongScoring").classList.toggle("hidden", !cats.has("wrong_scoring"));
    document.getElementById("skipFieldsMissingSkill").classList.toggle("hidden", !cats.has("missing_skill"));
    document.getElementById("skipFieldsDomainKnowledge").classList.toggle("hidden", !cats.has("domain_knowledge"));
    document.getElementById("skipFieldsSalary").classList.toggle("hidden", !cats.has("salary_low"));
    document.getElementById("skipFieldsOther").classList.toggle("hidden", !cats.has("other"));
    skipFormError.classList.add("hidden");
  }

  function resetSkipForm() {
    skipForm.reset();
    updateSkipConditionalFields();
    skipFormError.classList.add("hidden");
    skipFormError.textContent = "";
  }

  function openSkipWizard(url, title) {
    pendingSkip = { url, title };
    document.getElementById("skipDialogJobTitle").textContent = title || url;
    resetSkipForm();
    skipDialog.showModal();
  }

  function closeSkipWizard() {
    pendingSkip = null;
    skipDialog.close();
    resetSkipForm();
  }

  function collectSkipReason() {
    const cats = selectedSkipCategories();
    if (!cats.length) {
      return { error: "Wybierz co najmniej jeden powód pominięcia." };
    }
    const reasons = [];
    for (const cat of cats) {
      const item = { category: cat };
      if (cat === "wrong_scoring") {
        const fit = document.getElementById("skipCorrectFit").value;
        const scoreRaw = document.getElementById("skipCorrectScore").value.trim();
        const score = scoreRaw === "" ? null : Number(scoreRaw);
        if (!fit && score == null) {
          return { error: "Dla błędnego scoringu podaj poprawny fit lub wynik triażu." };
        }
        if (scoreRaw !== "" && Number.isNaN(score)) {
          return { error: "Wynik triażu musi być liczbą." };
        }
        if (fit) item.correct_fit = fit;
        if (score != null) item.correct_score = score;
      } else if (cat === "missing_skill") {
        const missing = document.getElementById("skipMissingItem").value.trim();
        if (!missing) return { error: "Podaj brakującą umiejętność lub certyfikat." };
        item.missing_item = missing;
      } else if (cat === "domain_knowledge") {
        const note = document.getElementById("skipDomainNote").value.trim();
        if (!note) return { error: "Podaj brakującą wiedzę domenową." };
        item.domain_note = note;
      } else if (cat === "salary_low") {
        const note = document.getElementById("skipSalaryNote").value.trim();
        if (!note) return { error: "Podaj informację o widełkach." };
        item.salary_note = note;
      } else if (cat === "other") {
        const comment = document.getElementById("skipComment").value.trim();
        if (!comment) return { error: "Podaj komentarz dla opcji „Inne”." };
        item.comment = comment;
      }
      reasons.push(item);
    }
    return { payload: { source: "manual", reasons } };
  }

  async function submitSkip() {
    if (!pendingSkip) return;
    const { payload, error } = collectSkipReason();
    if (error) {
      skipFormError.textContent = error;
      skipFormError.classList.remove("hidden");
      return;
    }
    const btn = document.getElementById("skipDialogConfirm");
    setButtonLoading(btn, true, "Pomijam…");
    try {
      await apiFetch("/api/inbox/" + encodeURIComponent(pendingSkip.url), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "skipped", skip_reason: payload }),
      });
      closeSkipWizard();
      showToast("Oferta pominięta");
      loadInbox();
    } catch (err) {
      skipFormError.textContent = String(err.message || err);
      skipFormError.classList.remove("hidden");
    } finally {
      setButtonLoading(btn, false);
      btn.textContent = "Pomiń ofertę";
    }
  }

  async function loadInbox() {
    const status = document.getElementById("fStatus").value;
    const fit = document.getElementById("fFit").value;
    const tierFilter = document.getElementById("fTier").value;
    const q = document.getElementById("fSearch").value.trim();
    let url = `/api/inbox?tier=${currentTier}&`;
    if (status) url += `status=${status}&`;
    if (fit) url += `fit=${fit}&`;
    if (q) url += `q=${encodeURIComponent(q)}&`;
    const d = await fetch(url).then((r) => r.json());
    jobs = d.jobs || [];
    if (tierFilter) jobs = jobs.filter((j) => j.tier === tierFilter);
    applyCurrentSort();
    focusedIdx = 0;
    const c = d.counts || {};
    const untriaged = c.untriaged || 0;
    const reviewLine =
      untriaged > 0
        ? `do przeglądu: ${c.review || 0} (+${untriaged} poza triażem)`
        : `do przeglądu: ${c.review || 0}`;
    document.getElementById("summary").textContent =
      `${jobs.length} ofert · priorytet: ${c.priority || 0}, ${reviewLine}, kolejka: ${c.evaluate_queue || 0}`;
    const banner = document.getElementById("triageBanner");
    if (!d.has_triage) banner.classList.remove("hidden");
    else banner.classList.add("hidden");
    const staleBanner = document.getElementById("staleTriageBanner");
    if (d.triage_stale && untriaged > 0) {
      staleBanner.classList.remove("hidden");
      document.getElementById("staleTriageText").textContent =
        `${untriaged} ofert poza triażem (nowe po ostatnim scrape). `;
    } else {
      staleBanner.classList.add("hidden");
    }
    renderView();
    if (typeof loadInboxBadge === "function") loadInboxBadge();
  }

  skipForm.querySelectorAll('input[name="skipCategory"]').forEach((el) => {
    el.addEventListener("change", updateSkipConditionalFields);
  });
  document.getElementById("skipDialogCancel").onclick = closeSkipWizard;
  skipDialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    closeSkipWizard();
  });
  skipForm.addEventListener("submit", (e) => {
    e.preventDefault();
    submitSkip();
  });

  document.getElementById("tierTabs").onclick = (e) => {
    const tab = e.target.closest(".o_tab");
    if (!tab) return;
    document.querySelectorAll("#tierTabs .o_tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    currentTier = tab.dataset.tier;
    loadInbox();
  };

  document.getElementById("viewTabs").onclick = (e) => {
    const tab = e.target.closest(".o_tab");
    if (!tab) return;
    document.querySelectorAll("#viewTabs .o_tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    currentView = tab.dataset.view;
    renderView();
  };

  document.getElementById("reload").onclick = loadInbox;
  document.getElementById("fStatus").onchange = loadInbox;
  document.getElementById("fFit").onchange = loadInbox;
  document.getElementById("fTier").onchange = loadInbox;
  let searchTimer;
  document.getElementById("fSearch").oninput = () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadInbox, 300);
  };

  document.getElementById("jobList").onclick = async (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const card = btn.closest(".o_job_card");
    const idx = Number(card.dataset.idx);
    const job = jobs[idx];
    const url = jobRef(job || { url: card.dataset.url, key: card.dataset.url });
    if (btn.dataset.act === "skip") {
      openSkipWizard(url, job?.title);
    }
    if (btn.dataset.act === "evaluate") {
      try {
        showToast("Ocena w toku…");
        await startApplyAsync({ url, proceed: false, compile_pdf: true });
      } catch (err) {
        showToast(String(err.message));
      }
    }
  };

  document.getElementById("jobTableWrap").onclick = async (e) => {
    const btn = e.target.closest("button[data-skip]");
    if (!btn) return;
    const row = btn.closest("tr");
    const rowIdx = row ? Number(row.dataset.idx) : -1;
    const job = rowIdx >= 0 ? jobs[rowIdx] : null;
    openSkipWizard(job ? jobRef(job) : btn.dataset.skip, job?.title || btn.dataset.title);
  };

  document.getElementById("runTriage").onclick = async () => {
    const btn = document.getElementById("runTriage");
    setButtonLoading(btn, true, "Triaż…");
    try {
      const { task_id } = await apiFetch("/api/inbox/triage/async", { method: "POST" });
      const d = await new Promise((resolve, reject) => {
        watchSseTask(task_id, {
          onStage(stage) {
            if (stage.message) btn.textContent = stage.message.slice(0, 40);
          },
          onDone(result) {
            if (result.status === "failed") {
              reject(new Error(result.error || result.message || "Triaż nieudany"));
              return;
            }
            resolve(result.result || result);
          },
          onError() {
            reject(new Error("Połączenie z triażem przerwane"));
          },
        });
      });
      const summary = d && typeof d === "object" ? d : {};
      showToast(
        `Triaż: ${summary.priority ?? "—"} priorytet, ${summary.review ?? "—"} do przeglądu`
      );
      loadInbox();
    } catch (e) {
      showToast("Błąd triażu: " + (e.message || e));
    } finally {
      setButtonLoading(btn, false);
      btn.textContent = "Uruchom triaż";
    }
  };

  document.addEventListener("keydown", (e) => {
    if (skipDialog.open) return;
    if (currentView !== "cards") return;
    if (e.target.matches("input, textarea, select")) return;
    if (!jobs.length) return;
    if (e.key === "j") {
      focusedIdx = Math.min(focusedIdx + 1, jobs.length - 1);
      renderCards();
      e.preventDefault();
    }
    if (e.key === "k") {
      focusedIdx = Math.max(focusedIdx - 1, 0);
      renderCards();
      e.preventDefault();
    }
    if (e.key === "a" && jobs[focusedIdx]) {
      window.location.href = "/apply?url=" + encodeURIComponent(jobRef(jobs[focusedIdx]));
      e.preventDefault();
    }
    if (e.key === "s" && jobs[focusedIdx]) {
      openSkipWizard(jobRef(jobs[focusedIdx]), jobs[focusedIdx].title);
      e.preventDefault();
    }
  });

  if (currentView === "table") {
    document.querySelectorAll("#viewTabs .o_tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.view === "table");
    });
  }

  loadInbox();
})();
