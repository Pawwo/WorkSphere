(function () {
  const APP_ID = window.__APP_ID__;
  const STAGES = window.PIPELINE_STAGES || [
    "parse",
    "evaluate",
    "proceed",
    "draft",
    "review",
    "pdf",
    "checklist",
    "interview_prep",
    "tracker",
    "done",
  ];
  let appData = null;
  let sse = null;
  let pollTimer = null;
  let preflightCache = null;

  function isPipelineActive(data) {
    if (!data) return false;
    return data.pipeline_status === "running" || data.pipeline_status === "waiting";
  }

  function shouldWakePreflight(data) {
    return !isPipelineActive(data);
  }

  function stageIndex(stage) {
    const i = STAGES.indexOf(stage);
    return i >= 0 ? i : 0;
  }

  function setTaskInUrl(taskId) {
    if (!taskId) return;
    const url = new URL(location.href);
    url.searchParams.set("task", taskId);
    history.replaceState(null, "", url.pathname + url.search);
  }

  function renderStatusbar(data) {
    const cur = data.pipeline_stage || "parse";
    const curIdx = stageIndex(cur);
    const status = data.pipeline_status || "pending";
    document.getElementById("statusbar").innerHTML = STAGES.map((s, i) => {
      let cls = "o_statusbar_item";
      if (i < curIdx || (s === cur && status === "done")) cls += " done";
      else if (s === cur)
        cls += status === "waiting" ? " waiting" : status === "failed" ? " failed" : " current";
      return `<span class="${cls}">${esc(t("pipeline_stage", s))}</span>`;
    }).join("");
  }

  function renderPreflightBanner(preflight, data) {
    const el = document.getElementById("preflightBanner");
    if (!el) return;
    const msgs = [];
    if (data && (data.pipeline_status === "waiting" || data.pipeline_stage === "proceed")) {
      msgs.push("Ocena gotowa — kliknij „Generuj CV i list”, aby przygotować dokumenty.");
    }
    if (preflight) {
      if (!preflight.llm || !preflight.ready_for_draft) {
        const st = preflight.llm && preflight.llm.status;
        if (st === "idle" || st === "starting") {
          const wake = preflight.wake_url ? preflight.wake_url.replace(/\/$/, "") + "/wake" : "http://127.0.0.1:8099/wake";
          msgs.push("LLM budzi się — odśwież za chwilę lub: curl -X POST " + wake);
        } else {
          msgs.push(
            "LLM niedostępny (sprawdź local GPU :8006 / :8099) — bez LLM zostanie użyty baseline CV."
          );
        }
      }
      if (!preflight.ready_for_pdf) {
        msgs.push("Brak lualatex/xelatex — uruchom: bash scripts/install_latex.sh");
      }
    }
    if (data && data.cv_file && !data.pdf_cv) {
      msgs.push("Pliki .tex gotowe — PDF wymaga LaTeX lub ponów kompilację.");
    }
    if (!msgs.length) {
      el.style.display = "none";
      el.innerHTML = "";
      return;
    }
    el.style.display = "block";
    el.innerHTML = msgs.map((m) => `<div>${esc(m)}</div>`).join("");
  }

  function setLiveProgress(message) {
    const el = document.getElementById("liveProgress");
    const wrap = document.getElementById("liveProgressWrap");
    if (!el) return;
    if (!message) {
      el.textContent = "";
      if (wrap) wrap.style.display = "none";
      return;
    }
    if (wrap) wrap.style.display = "block";
    el.textContent = message;
  }

  function clearLiveProgress() {
    setLiveProgress("");
  }

  function updatePipelineRowInOverview() {
    if (!appData) return;
    const panel = document.getElementById("panelOverview");
    if (!panel) return;
    const rows = panel.querySelectorAll(".o_eval_table tr");
    rows.forEach((tr) => {
      const th = tr.querySelector("th");
      if (th && th.textContent === "Pipeline") {
        const td = tr.querySelector("td");
        if (td) {
          td.textContent =
            t("pipeline_stage", appData.pipeline_stage) +
            " / " +
            t("pipeline_status", appData.pipeline_status);
        }
      }
    });
  }

  function applyPipelineEvent(ev) {
    if (!appData) return;
    if (ev.stage && ev.stage !== "error") appData.pipeline_stage = ev.stage;
    if (ev.status === "waiting") appData.pipeline_status = "waiting";
    else if (ev.status === "failed") appData.pipeline_status = "failed";
    else if (ev.status !== "completed") appData.pipeline_status = "running";
    renderStatusbar(appData);
    updatePipelineRowInOverview();
    if (ev.message && (ev.status === "running" || ev.status === "waiting")) {
      const label = ev.stage ? t("pipeline_stage", ev.stage) + ": " : "";
      setLiveProgress(label + ev.message);
    }
  }

  function renderSmartButtons(data) {
    const v = data.verification_pass;
    const vLabel = v === 1 ? "✓" : v === 0 ? "!" : "—";
    const vCls = v === 1 ? "o_stat_success" : v === 0 ? "o_stat_danger" : "";
    const docs = [data.cv_file, data.cover_file, data.pdf_cv, data.pdf_cover].filter(Boolean).length;
    document.getElementById("smartButtons").innerHTML = `
      <button type="button" class="o_stat_button" data-goto="documents"><span class="o_stat_value">${data.cv_file ? 1 : 0}</span>CV</button>
      <button type="button" class="o_stat_button" data-goto="documents"><span class="o_stat_value">${data.cover_file ? 1 : 0}</span>List</button>
      <button type="button" class="o_stat_button" data-goto="documents"><span class="o_stat_value">${docs}</span>Dok.</button>
      <button type="button" class="o_stat_button ${vCls}" data-goto="verify"><span class="o_stat_value">${vLabel}</span>Checklist</button>
      <button type="button" class="o_stat_button" data-goto="prep"><span class="o_stat_value">${data.interview_prep_file ? 1 : 0}</span>Prep</button>`;
    document.getElementById("smartButtons").onclick = (e) => {
      const btn = e.target.closest("[data-goto]");
      if (!btn) return;
      switchTab(btn.dataset.goto);
    };
  }

  function switchTab(name) {
    document.querySelectorAll(".o_notebook_tab").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.tab === name);
    });
    document.querySelectorAll(".o_tab_panel").forEach((p) => p.classList.remove("active"));
    const panel = document.getElementById("tab-" + name);
    if (panel) panel.classList.add("active");
  }

  document.getElementById("notebookTabs").onclick = (e) => {
    const tab = e.target.closest(".o_notebook_tab");
    if (tab) switchTab(tab.dataset.tab);
  };

  function fileLink(path) {
    if (!path) return "";
    const name = path.split("/").pop();
    let kind = "app";
    if (path.startsWith("cv/")) kind = "cv";
    else if (path.startsWith("cover_letters/")) kind = "cover";
    const href =
      kind === "app"
        ? "/api/files/app/" + encodeURIComponent(path)
        : "/api/files/" + kind + "/" + encodeURIComponent(name);
    return `<a href="${href}" target="_blank" rel="noopener">${esc(name)}</a>`;
  }

  function fitTone(fit) {
    if (!fit) return "";
    const f = String(fit).toLowerCase();
    if (f === "strong" || f === "high") return "ok";
    if (f === "moderate" || f === "medium") return "warn";
    return "";
  }

  function scoreBar(score) {
    const n = Number(score);
    if (!Number.isFinite(n)) return "—";
    const pct = Math.max(0, Math.min(100, n));
    return `<div class="o_score_bar"><div style="width:${pct}%"></div></div><span class="o_score_val">${pct}/100</span>`;
  }

  function gotoTabLink(name, label) {
    return `<button type="button" class="btn btn-link btn-sm o_goto_tab" data-goto="${esc(name)}">${esc(label)}</button>`;
  }

  function bindGotoTabs(root) {
    if (!root) return;
    root.querySelectorAll(".o_goto_tab").forEach((btn) => {
      btn.onclick = () => switchTab(btn.dataset.goto);
    });
  }

  function hasLoginWallWarning(data, parsed) {
    const acts = (data.activities || []).some((a) => /login wall/i.test(a.body || ""));
    const shortText = (parsed.raw_text || "").length < 600;
    return acts || shortText;
  }

  function attentionItems(data, r, ver) {
    const items = [];
    const fails = (ver.items || []).filter((i) => !i.pass);
    fails.forEach((f) => {
      items.push({
        text: `Checklist: ${f.label}${f.note ? " — " + f.note : ""}`,
        tab: "verify",
        tabLabel: "Weryfikacja",
      });
    });
    const verdict = (r.reviewer || {}).overall_verdict || data.reviewer_verdict;
    if (verdict && verdict !== "approve") {
      items.push({
        text: `Recenzja: werdykt «${t("reviewer_verdict", verdict) || verdict}»`,
        tab: "review",
        tabLabel: "Recenzja",
      });
    }
    const parsed = r.parsed || {};
    if (hasLoginWallWarning(data, parsed)) {
      items.push({
        text: "Opis ogłoszenia niepełny (login wall / skrócony tekst)",
        tab: "overview",
        tabLabel: "szczegóły",
        expand: true,
      });
    }
    return items;
  }

  function renderKpiCards(data, r, inbox) {
    const ev = r.evaluation || {};
    const ver = r.verification || {};
    const llmFit = data.overall_fit || ev.overall_fit;
    const quickFit = inbox.quick_fit || inbox.fit;
    const verdict = data.reviewer_verdict || (r.reviewer || {}).overall_verdict;
    const vTone = verdict === "approve" ? "ok" : verdict ? "warn" : "";
    const checkLabel =
      ver.passed != null && ver.total != null
        ? `${ver.passed}/${ver.total}`
        : data.verification_pass === 1
          ? "✓"
          : data.verification_pass === 0
            ? "!"
            : "—";
    const checkTone = data.verification_pass === 1 ? "ok" : data.verification_pass === 0 ? "warn" : "";
    return `<div class="o_grid o_kpi_row">
      <div class="o_stat_card"><h3>Dopasowanie LLM</h3><div class="val ${fitTone(llmFit)}">${esc(t("fit", llmFit) || "—")}</div></div>
      <div class="o_stat_card"><h3>Quick fit</h3><div class="val ${fitTone(quickFit)}">${esc(t("fit", quickFit) || "—")}</div></div>
      <div class="o_stat_card"><h3>Recenzja</h3><div class="val ${vTone}">${esc(t("reviewer_verdict", verdict) || "—")}</div></div>
      <div class="o_stat_card"><h3>Checklist</h3><div class="val ${checkTone}">${esc(checkLabel)}</div></div>
    </div>`;
  }

  function renderOverviewPanel(data, r, inbox) {
    const ev = r.evaluation || {};
    const ver = r.verification || {};
    const parsed = r.parsed || {};
    const rec = data.recommendation || ev.recommendation || "—";
    const salary = ev.salary_benchmark || {};
    const attention = attentionItems(data, r, ver);
    const warnLogin = hasLoginWallWarning(data, parsed);
    let html = renderKpiCards(data, r, inbox);
    if (warnLogin) {
      html += `<div class="o_alert o_alert_warn">Ocena i dokumenty mogą opierać się na niepełnym opisie ogłoszenia (login wall LinkedIn).</div>`;
    }
    html += `<div class="o_section_box"><h4 class="o_section_title">Rekomendacja</h4><p>${esc(rec)}</p></div>`;
    if (attention.length) {
      html += `<div class="o_section_box o_section_attention"><h4 class="o_section_title">Wymaga uwagi</h4><ul class="o_attention_list">`;
      attention.forEach((a) => {
        html += `<li>${esc(a.text)} ${gotoTabLink(a.tab, "→ " + a.tabLabel)}</li>`;
      });
      html += `</ul></div>`;
    }
    html += `<table class="o_eval_table">
      <tr><th>Firma / rola</th><td>${esc(data.company)} — ${esc(data.role)}</td></tr>
      <tr><th>Lokalizacja</th><td>${esc(parsed.location || inbox.location || "—")}</td></tr>
      <tr><th>Portal</th><td>${esc(inbox.portal || "—")}</td></tr>
      <tr><th>Język ogłoszenia</th><td>${esc(parsed.language || "—")}</td></tr>
      <tr><th>Tier triażu</th><td>${esc(t("tier", inbox.tier) || "—")}${inbox.triage_reason ? " · " + esc(inbox.triage_reason) : ""}</td></tr>
      <tr><th>Widełki B2B</th><td>${salary.monthly_b2b_min != null ? esc(`${salary.monthly_b2b_min}–${salary.monthly_b2b_max} PLN`) : "—"}${salary.meets_threshold ? " · próg OK" : ""}</td></tr>
      <tr><th>Etap rekrutacji</th><td>${esc(t("hiring_stage", data.hiring_stage))}</td></tr>
      <tr><th>Pipeline</th><td>${esc(t("pipeline_stage", data.pipeline_stage))} / ${esc(t("pipeline_status", data.pipeline_status))}</td></tr>
      <tr><th>Utworzono</th><td>${esc((data.created_at || "").slice(0, 16))}</td></tr>
      <tr><th>Aktualizacja</th><td>${esc((data.updated_at || "").slice(0, 16))}</td></tr>
    </table>`;
    if (parsed.raw_text) {
      const excerpt = parsed.raw_text.length > 400 ? parsed.raw_text.slice(0, 400) + "…" : parsed.raw_text;
      html += `<details class="o_section_box"><summary>Fragment opisu ogłoszenia</summary><pre class="o_excerpt">${esc(excerpt)}</pre></details>`;
    }
    const timeline = (data.activities || []).slice(0, 3);
    if (timeline.length) {
      html += `<div class="o_section_box"><h4 class="o_section_title">Ostatnie zdarzenia</h4>`;
      timeline.forEach((a) => {
        html += `<div class="o_timeline_item">${esc(a.body)}<span class="o_muted"> · ${esc((a.created_at || "").slice(0, 16))}</span></div>`;
      });
      html += `</div>`;
    }
    return html;
  }

  function renderEvaluationPanel(data, ev) {
    if (!ev || !Object.keys(ev).length) return "<p class='o_muted'>Brak danych</p>";
    const r = data.result || {};
    const parsed = r.parsed || {};
    const fit = ev.overall_fit || data.overall_fit;
    const rec = ev.recommendation || data.recommendation || "";
    const sm = ev.skills_match || {};
    const em = ev.experience_match || {};
    const bm = ev.behavioral_match || {};
    const lm = ev.location_match || {};
    const salary = ev.salary_benchmark || {};
    let html = `<div class="o_eval_header">
      <span class="o_badge o_badge_${fitTone(fit) || "muted"}">${esc(t("fit", fit) || "—")}</span>
      ${rec ? `<p class="o_eval_rec">${esc(rec)}</p>` : ""}
    </div>`;
    if (hasLoginWallWarning(data, parsed)) {
      html += `<div class="o_alert o_alert_warn">Ocena na podstawie skróconego opisu ogłoszenia.</div>`;
    }
    html += `<div class="o_grid o_score_grid">
      <div class="o_stat_card"><h3>Umiejętności</h3>${scoreBar(sm.score)}</div>
      <div class="o_stat_card"><h3>Doświadczenie</h3>${scoreBar(em.score)}</div>
      <div class="o_stat_card"><h3>Behawioralne</h3>${scoreBar(bm.score)}</div>
      <div class="o_stat_card"><h3>Lokalizacja</h3><div class="val ${lm.pass ? "ok" : "warn"}">${lm.pass ? "✓" : "✗"}</div></div>
    </div>`;
    if ((sm.matches || []).length || (sm.gaps || []).length) {
      html += `<div class="o_section_box"><h4 class="o_section_title">Umiejętności</h4>
        <p><strong>Dopasowane:</strong> ${(sm.matches || []).map((m) => esc(m)).join(", ") || "—"}</p>
        <p><strong>Luki:</strong> ${(sm.gaps || []).map((g) => esc(g)).join(", ") || "—"}</p></div>`;
    }
    if (em.notes) html += `<div class="o_section_box"><h4 class="o_section_title">Doświadczenie</h4><p>${esc(em.notes)}</p></div>`;
    if (bm.notes) html += `<div class="o_section_box"><h4 class="o_section_title">Behawioralne</h4><p>${esc(bm.notes)}</p></div>`;
    if (lm.notes) html += `<div class="o_section_box"><h4 class="o_section_title">Lokalizacja</h4><p>${esc(lm.notes)}</p></div>`;
    if (salary.monthly_b2b_min != null) {
      html += `<div class="o_section_box"><h4 class="o_section_title">Widełki B2B</h4>
        <p>${esc(String(salary.monthly_b2b_min))}–${esc(String(salary.monthly_b2b_max))} PLN (mediana ${esc(String(salary.monthly_b2b_median || "—"))})</p>
        <p class="o_muted">${salary.meets_threshold ? "Próg spełniony" : "Poniżej progu"} · ${esc(salary.reason || salary.source || "")}</p></div>`;
    }
    return html;
  }

  function pdfStatusFromVer(ver, label) {
    const item = (ver.items || []).find((i) => i.category === "pdf" && (i.label || "").includes(label));
    return item ? (item.pass ? "✓ " + (item.note || "OK") : "✗ " + (item.note || "")) : "—";
  }

  function renderDocumentsPanel(data, r) {
    const ver = r.verification || {};
    const draft = r.draft || {};
    const targets = draft.job_targets || {};
    const decisions = r.tailoring_decisions || draft.tailoring_decisions || [];
    const rows = [];
    if (data.cv_file || data.pdf_cv) {
      rows.push(`<tr><td>CV</td><td>${fileLink(data.cv_file)}</td><td>${fileLink(data.pdf_cv)}</td><td>${esc(pdfStatusFromVer(ver, "CV"))}</td></tr>`);
    }
    if (data.cover_file || data.pdf_cover) {
      rows.push(`<tr><td>List motywacyjny</td><td>${fileLink(data.cover_file)}</td><td>${fileLink(data.pdf_cover)}</td><td>${esc(pdfStatusFromVer(ver, "List"))}</td></tr>`);
    }
    if (!rows.length) {
      return "<p class='o_muted'>Brak dokumentów — uruchom „Generuj CV i list” po ocenie.</p>";
    }
    let html = `<table class="o_eval_table o_docs_table"><thead><tr><th>Dokument</th><th>HTML</th><th>PDF</th><th>Status</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
    if (data.cv_file || data.cover_file) {
      const cvSrc = data.cv_file ? "/api/files/app/" + encodeURIComponent(data.cv_file) : "";
      const coverSrc = data.cover_file ? "/api/files/app/" + encodeURIComponent(data.cover_file) : "";
      html += `<div class="o_doc_preview_tabs">
        <button type="button" class="o_doc_tab active" data-preview="cv">CV</button>
        <button type="button" class="o_doc_tab" data-preview="cover">List</button>
      </div>
      <iframe id="docPreviewFrame" class="o_doc_preview" src="${cvSrc || coverSrc}" title="Podgląd dokumentu"></iframe>`;
    }
    if ((r.pdf_verification || []).length) {
      html += `<p class="o_muted">PDF: ${esc(r.pdf_verification.join(", "))}</p>`;
    }
    if (decisions.length) {
      html += `<div class="o_section_box"><h4 class="o_section_title">Decyzje tailoringu</h4><ul>${decisions.map((d) => `<li>${esc(d)}</li>`).join("")}</ul></div>`;
    }
    const must = targets.must_have_keywords || [];
    const nice = targets.nice_to_have_keywords || [];
    if (must.length || nice.length) {
      html += `<div class="o_section_box"><h4 class="o_section_title">Słowa kluczowe</h4>
        <p>${must.map((k) => `<span class="o_chip must">${esc(k)}</span>`).join(" ")}</p>
        <p>${nice.map((k) => `<span class="o_chip">${esc(k)}</span>`).join(" ")}</p></div>`;
    }
    const norm = targets.normalized_skills || [];
    if (norm.length) {
      html += `<table class="o_eval_table"><thead><tr><th>Wymaganie</th><th>W CV</th></tr></thead><tbody>`;
      norm.forEach((n) => {
        html += `<tr><td>${esc(n.posting_term || "")}</td><td>${esc(n.candidate_term || "")}</td></tr>`;
      });
      html += `</tbody></table>`;
    }
    return html;
  }

  function bindDocPreviewTabs() {
    const frame = document.getElementById("docPreviewFrame");
    if (!frame || !appData) return;
    document.querySelectorAll(".o_doc_tab").forEach((tab) => {
      tab.onclick = () => {
        document.querySelectorAll(".o_doc_tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        const path = tab.dataset.preview === "cover" ? appData.cover_file : appData.cv_file;
        if (path) frame.src = "/api/files/app/" + encodeURIComponent(path);
      };
    });
  }

  function renderDiffCard(edit) {
    const fileLabel = edit.file === "cover" ? "List" : "CV";
    return `<div class="o_diff_card">
      <div class="o_diff_file">${esc(fileLabel)}</div>
      <div class="o_diff_old"><del>${esc(edit.old_string || "")}</del></div>
      <div class="o_diff_new">${esc(edit.new_string || "")}</div>
      ${edit.reason ? `<div class="o_diff_reason">${esc(edit.reason)}</div>` : ""}
    </div>`;
  }

  const NARRATIVE_LABELS = {
    missed_keywords: "Brakujące słowa kluczowe",
    company_angles: "Kąt firmy",
    reframing: "Sugerowana przebudowa CV",
    tone_issues: "Ton i styl",
  };

  function renderReviewPanel(r, data) {
    const rev = r.reviewer || {};
    if (!rev || !Object.keys(rev).length) return "<p class='o_muted'>Brak danych</p>";
    const verdict = rev.overall_verdict || data.reviewer_verdict || "";
    const tone = verdict === "approve" ? "ok" : verdict ? "warn" : "";
    let html = `<div class="o_eval_header">
      <span class="o_badge o_badge_${tone || "muted"}">${esc(t("reviewer_verdict", verdict) || verdict || "—")}</span>
      <p class="o_muted">Edycje z recenzji są stosowane automatycznie w pipeline.</p>
    </div>`;
    const edits = rev.structured_edits || [];
    if (edits.length) {
      html += `<div class="o_section_box"><h4 class="o_section_title">Zastosowane edycje (${edits.length})</h4>${edits.map(renderDiffCard).join("")}</div>`;
    }
    const narrative = rev.narrative || {};
    const narrKeys = Object.keys(NARRATIVE_LABELS).filter((k) => narrative[k]);
    if (narrKeys.length) {
      html += `<div class="o_grid">`;
      narrKeys.forEach((k) => {
        html += `<div class="o_section_box"><h4 class="o_section_title">${esc(NARRATIVE_LABELS[k])}</h4><p>${esc(String(narrative[k]))}</p></div>`;
      });
      html += `</div>`;
    }
    if (rev.company_research_notes) {
      const truncated = rev.company_research_notes.length < 40;
      html += `<div class="o_section_box"><h4 class="o_section_title">Notatki o firmie</h4><p>${esc(rev.company_research_notes)}</p>`;
      if (truncated) html += `<p class="o_muted">Uwaga: notatki mogą być niepełne (obcięte przez LLM).</p>`;
      html += `</div>`;
    }
    if (verdict && verdict !== "approve") {
      html += `<p>${gotoTabLink("verify", "Przejdź do Weryfikacji")}</p>`;
    }
    return html;
  }

  function renderVerifyPanel(ver, data) {
    if (!ver || !Object.keys(ver).length) {
      return `<p class="o_muted">Brak checklisty</p>`;
    }
    const passTone = data.verification_pass === 1 ? "ok" : data.verification_pass === 0 ? "warn" : "";
    const statusLabel = data.verification_pass === 1 ? "GOTOWE DO WYSŁANIA" : data.verification_pass === 0 ? "WYMAGA POPRAWY" : "—";
    const kw = ver.keyword_coverage || {};
    const bulletPct = ver.bullet_quality_ratio != null ? Math.round(ver.bullet_quality_ratio * 100) : null;
    let html = `<div class="o_verify_summary ${passTone ? "o_verify_" + passTone : ""}">
      <strong>${esc(ver.passed != null ? ver.passed + "/" + ver.total + " zaliczonych" : "Checklist")}</strong>
      ${ver.ats_score != null ? ` · ATS ${esc(String(ver.ats_score))}/100` : ""}
      ${kw.coverage_ratio != null ? ` · Pokrycie słów kluczowych ${Math.round(kw.coverage_ratio * 100)}%` : ""}
      ${bulletPct != null ? ` · Jakość bulletów ${bulletPct}%` : ""}
      <span class="o_verify_status">${esc(statusLabel)}</span>
    </div>`;
    const fails = (ver.items || []).filter((i) => !i.pass);
    if (fails.length) {
      html += `<div class="o_section_box o_section_attention"><h4 class="o_section_title">Niezaliczone</h4>`;
      fails.forEach((f) => {
        html += `<div class="o_checklist_item fail">✗ ${esc(t("verify_category", f.category) || f.category)}: ${esc(f.label)}${f.note ? " — " + esc(f.note) : ""}</div>`;
      });
      html += `<p>${gotoTabLink("review", "Zobacz sugestie w Recenzji")}</p></div>`;
    }
    const byCat = {};
    (ver.items || []).forEach((i) => {
      const c = i.category || "other";
      if (!byCat[c]) byCat[c] = [];
      byCat[c].push(i);
    });
    Object.keys(byCat).forEach((cat) => {
      const catFails = byCat[cat].some((i) => !i.pass);
      html += `<details class="o_checklist_group" ${catFails ? "open" : ""}>
        <summary>${esc(t("verify_category", cat) || cat)} (${byCat[cat].filter((i) => i.pass).length}/${byCat[cat].length})</summary>`;
      byCat[cat].forEach((i) => {
        html += `<div class="o_checklist_item ${i.pass ? "pass" : "fail"}">${i.pass ? "✓" : "✗"} ${esc(i.label)}${i.note ? ` <span class="o_muted">— ${esc(i.note)}</span>` : ""}</div>`;
      });
      html += `</details>`;
    });
    if ((kw.hits || []).length || (ver.missing_keywords || []).length) {
      html += `<div class="o_section_box"><h4 class="o_section_title">Słowa kluczowe ATS</h4>
        <p>Trafienia: ${(kw.hits || []).map((h) => esc(h)).join(", ") || "—"}</p>
        <p>Braki: ${(ver.missing_keywords || []).map((h) => esc(h)).join(", ") || "—"}</p></div>`;
    }
    if (data.pipeline_stage === "done") {
      html += `<button type="button" class="btn btn-secondary btn-sm" id="btnRetryChecklist">Ponów checklist</button>`;
    }
    return html;
  }

  let prepAutoAttempted = false;
  let prepAutoRunning = false;

  function renderPrepPanel(data, activities, preflight) {
    if (data.interview_prep_file) {
      return `<p>${fileLink(data.interview_prep_file)}</p>
        <iframe src="/api/files/app/${encodeURIComponent(data.interview_prep_file)}" class="o_doc_preview" title="Przygotowanie do rozmowy"></iframe>`;
    }
    const enabled = preflight && preflight.interview_prep_enabled;
    if (!enabled) {
      return `<div class="o_section_box o_prep_empty">
        <p><strong>Brak materiałów do rozmowy</strong></p>
        <p class="o_muted">Przygotowanie do rozmowy jest wyłączone w konfiguracji (<code>pipeline.interview_prep_enabled</code>).</p>
      </div>`;
    }
    if (data.hiring_stage === "interview") {
      return `<div class="o_section_box o_prep_empty">
        <p><strong>Przygotowanie do rozmowy</strong></p>
        <p class="o_muted">Na etapie Rozmowa materiały generują się automatycznie.</p>
        <p id="prepAutoStatus" class="o_muted">${prepAutoRunning ? "Generuję materiały…" : ""}</p>
      </div>`;
    }
    return `<div class="o_section_box o_prep_empty">
      <p><strong>Brak materiałów do rozmowy</strong></p>
      <p class="o_muted">Automatyczne przygotowanie uruchamia się po przejściu na etap Rozmowa. Możesz też wygenerować materiały ręcznie.</p>
      <button type="button" class="btn btn-primary btn-sm" id="btnGenInterviewPrep">Wygeneruj przygotowanie</button>
    </div>`;
  }

  async function maybeAutoInterviewPrep(data, preflight) {
    if (prepAutoAttempted || prepAutoRunning) return;
    if (!preflight || !preflight.interview_prep_enabled) return;
    if (data.interview_prep_file) return;
    if (data.hiring_stage !== "interview") return;
    prepAutoAttempted = true;
    prepAutoRunning = true;
    const status = document.getElementById("prepAutoStatus");
    if (status) status.textContent = "Generuję materiały…";
    try {
      await apiFetch("/api/applications/" + APP_ID + "/retry/interview_prep", { method: "POST" });
      showToast("Przygotowanie wygenerowane");
      await loadApp();
    } catch (err) {
      if (status) status.textContent = "Nie udało się wygenerować: " + err.message;
      showToast(String(err.message));
      prepAutoAttempted = false;
    } finally {
      prepAutoRunning = false;
    }
  }

  function bindGenInterviewPrep() {
    const btn = document.getElementById("btnGenInterviewPrep");
    if (!btn) return;
    btn.onclick = async () => {
      setButtonLoading(btn, true, "Generuję…");
      try {
        await apiFetch("/api/applications/" + APP_ID + "/retry/interview_prep", { method: "POST" });
        showToast("Przygotowanie wygenerowane");
        await loadApp();
      } catch (err) {
        showToast(String(err.message));
      } finally {
        setButtonLoading(btn, false);
      }
    };
  }

  function bindRetryChecklist() {
    const btn = document.getElementById("btnRetryChecklist");
    if (!btn) return;
    btn.onclick = async () => {
      showToast("Ponawiam checklist…");
      try {
        await apiFetch("/api/applications/" + APP_ID + "/retry/checklist", { method: "POST" });
        await loadApp();
      } catch (err) {
        showToast(String(err.message));
      }
    };
  }

  function renderQuickEdit(data) {
    const stages = window.HIRING_STAGES || [
      "draft",
      "ready_to_send",
      "applied",
      "screening",
      "interview",
      "offer",
      "rejected",
      "archived",
    ];
    const opts = stages
      .map(
        (s) =>
          `<option value="${s}"${data.hiring_stage === s ? " selected" : ""}>${esc(t("hiring_stage", s))}</option>`
      )
      .join("");
    document.getElementById("quickEdit").innerHTML = `
      <div class="o_form_group">
        <label class="o_form_label">Etap rekrutacji</label>
        <select id="hiringStage">${opts}</select>
      </div>
      <div class="o_form_group">
        <label class="o_form_label">Notatki wewnętrzne</label>
        <textarea id="appNotes" rows="2">${esc(data.notes || "")}</textarea>
      </div>
      <button type="button" class="btn btn-secondary btn-sm" id="saveQuick">Zapisz</button>`;
    document.getElementById("saveQuick").onclick = async () => {
      try {
        await apiFetch("/api/applications/" + APP_ID, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            hiring_stage: document.getElementById("hiringStage").value,
            notes: document.getElementById("appNotes").value,
          }),
        });
        showToast("Zapisano");
        await loadApp();
      } catch (err) {
        showToast(String(err.message));
      }
    };
  }

  function renderPanels(data, preflight) {
    const r = data.result || {};
    const ev = r.evaluation || {};
    const inbox = data.inbox_context || {};
    if (!ev.overall_fit && data.overall_fit) {
      ev.overall_fit = data.overall_fit;
      ev.recommendation = data.recommendation;
    }
    const ver = r.verification || {};
    document.getElementById("panelOverview").innerHTML = renderOverviewPanel(data, r, inbox);
    document.getElementById("panelEvaluation").innerHTML = renderEvaluationPanel(data, ev);
    document.getElementById("panelDocuments").innerHTML = renderDocumentsPanel(data, r);
    document.getElementById("panelReview").innerHTML = renderReviewPanel(r, data);
    document.getElementById("panelVerify").innerHTML = renderVerifyPanel(ver, data);
    document.getElementById("panelPrep").innerHTML = renderPrepPanel(data, data.activities, preflight);
    bindGotoTabs(document.getElementById("panelOverview"));
    bindGotoTabs(document.getElementById("panelReview"));
    bindGotoTabs(document.getElementById("panelVerify"));
    bindDocPreviewTabs();
    bindRetryChecklist();
    bindGenInterviewPrep();
    maybeAutoInterviewPrep(data, preflight);
  }

  function renderChatter(activities) {
    document.getElementById("chatterList").innerHTML =
      (activities || [])
        .map(
          (a) =>
            `<div class="o_activity_item"><div>${esc(a.body)}</div>
       <div class="o_activity_meta">${esc(a.author)} · ${esc(a.kind)} · ${esc((a.created_at || "").slice(0, 16))}</div></div>`
        )
        .join("") || '<p class="o_muted">Brak aktywności</p>';
  }

  function lastError(activities) {
    const logs = (activities || []).filter((a) => a.kind === "stage_log" && (a.body || "").startsWith("Błąd:"));
    return logs.length ? logs[logs.length - 1].body : "";
  }

  function renderFooter(data) {
    const footer = document.getElementById("formFooter");
    let html = "";
    if (data.pipeline_status === "waiting" || data.pipeline_stage === "proceed") {
      html +=
        '<button type="button" class="btn btn-primary" id="btnProceed">Generuj CV i list</button>';
    }
    if (data.pipeline_status === "failed") {
      const err = lastError(data.activities);
      if (err) html += `<p class="o_summary o_stat_danger">${esc(err)}</p>`;
      if (data.url) {
        html += `<a href="/apply?url=${encodeURIComponent(data.url)}" class="btn btn-secondary">Uruchom ponownie</a>`;
      }
    }
    if (data.pipeline_stage === "done" || data.pipeline_status === "done") {
      html += '<button type="button" class="btn btn-secondary" id="btnRetryPdf">Ponów PDF</button>';
      html += '<a href="/tracker" class="btn btn-secondary">Tracker</a>';
    }
    const ev = (data.result || {}).evaluation || {};
    const rec = data.recommendation || ev.recommendation || "";
    const offlineEval =
      /LLM niedostępny|uruchom Bielik|Ocena offline|niepoprawnego JSON|niepoprawny JSON/i.test(rec) ||
      /Ocena offline/i.test((ev.skills_match || {}).note || "");
    if (offlineEval) {
      html +=
        '<button type="button" class="btn btn-secondary" id="btnRetryEvaluate">Odśwież ocenę (LLM)</button>';
    }
    if (data.url && /^https?:\/\//i.test(data.url)) {
      html += `<a href="${esc(data.url)}" target="_blank" rel="noopener" class="btn btn-link">Otwórz ogłoszenie</a>`;
    }
    footer.innerHTML = html;
    const proceedBtn = document.getElementById("btnProceed");
    if (proceedBtn)
      proceedBtn.onclick = async () => {
        setButtonLoading(proceedBtn, true, "Generuję…");
        try {
          const j = await apiFetch("/api/applications/" + APP_ID + "/proceed", { method: "POST" });
          setTaskInUrl(j.task_id);
          connectSSE(j.task_id, true);
          startPolling();
        } catch (err) {
          showToast(String(err.message));
          setButtonLoading(proceedBtn, false);
        }
      };
    const retryBtn = document.getElementById("btnRetryPdf");
    if (retryBtn)
      retryBtn.onclick = async () => {
        showToast("Ponawiam PDF…");
        await apiFetch("/api/applications/" + APP_ID + "/retry/pdf", { method: "POST" });
        await loadApp();
      };
    const retryEvalBtn = document.getElementById("btnRetryEvaluate");
    if (retryEvalBtn)
      retryEvalBtn.onclick = async () => {
        setButtonLoading(retryEvalBtn, true, "Oceniam…");
        try {
          await apiFetch("/api/applications/" + APP_ID + "/retry/evaluate", { method: "POST" });
          showToast("Ocena zaktualizowana");
          await loadApp();
        } catch (err) {
          showToast(String(err.message));
        } finally {
          setButtonLoading(retryEvalBtn, false);
        }
      };
  }

  async function loadPreflight(wake) {
    const wakePreflight = wake !== false;
    try {
      const q = wakePreflight ? "" : "?wake=false";
      return await apiFetch("/api/applications/" + APP_ID + "/preflight" + q);
    } catch {
      return null;
    }
  }

  function renderAppHeader(d) {
    document.getElementById("appTitle").textContent = d.company + " — " + d.role;
    document.getElementById("appSubtitle").innerHTML =
      d.url && /^https?:\/\//i.test(d.url)
        ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.url)}</a>`
        : "Aplikacja #" + APP_ID;
  }

  async function loadAppShell(d) {
    if (!d) {
      try {
        d = await apiFetch("/api/applications/" + APP_ID);
      } catch {
        document.getElementById("appTitle").textContent = "Nie znaleziono";
        return null;
      }
    }
    appData = d;
    renderAppHeader(d);
    renderStatusbar(d);
    renderSmartButtons(d);
    renderQuickEdit(d);
    renderFooter(d);
    if (!isPipelineActive(d)) {
      clearLiveProgress();
    }
    return d;
  }

  async function loadAppDetails(forcePreflight) {
    if (!appData) return;
    const wake = forcePreflight === true ? true : shouldWakePreflight(appData);
    if (wake || !preflightCache) {
      preflightCache = await loadPreflight(wake);
    }
    renderPreflightBanner(preflightCache, appData);
    renderPanels(appData, preflightCache);
    renderChatter(appData.activities);
  }

  async function loadApp(options) {
    const opts = options || {};
    const d = await loadAppShell();
    if (!d) return;
    if (opts.details !== false) {
      await loadAppDetails(opts.forcePreflight);
    }
  }

  async function pollPipelineShell() {
    if (!appData) return;
    try {
      const d = await apiFetch("/api/applications/" + APP_ID);
      appData.pipeline_stage = d.pipeline_stage;
      appData.pipeline_status = d.pipeline_status;
      appData.company = d.company;
      appData.role = d.role;
      appData.cv_file = d.cv_file;
      appData.cover_file = d.cover_file;
      appData.pdf_cv = d.pdf_cv;
      appData.pdf_cover = d.pdf_cover;
      appData.verification_pass = d.verification_pass;
      appData.reviewer_verdict = d.reviewer_verdict;
      appData.interview_prep_file = d.interview_prep_file;
      appData.result = d.result;
      appData.activities = d.activities;
      renderAppHeader(d);
      renderStatusbar(appData);
      renderFooter(appData);
      renderSmartButtons(appData);
      updatePipelineRowInOverview();
    } catch {
      /* ignore transient poll errors */
    }
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(() => {
      if (!appData || !isPipelineActive(appData)) {
        clearInterval(pollTimer);
        pollTimer = null;
        return;
      }
      pollPipelineShell();
    }, 2000);
  }

  function connectSSE(taskId, replace) {
    if (!taskId) return;
    if (sse && replace) {
      sse.close();
      sse = null;
    }
    if (sse) return;
    sse = watchSseTask(taskId, {
      onStage: (ev) => {
        applyPipelineEvent(ev);
      },
      onDone: (ev) => {
        sse = null;
        if (appData && ev && ev.status === "failed") appData.pipeline_status = "failed";
        clearLiveProgress();
        loadApp({ forcePreflight: true });
        const proceedBtn = document.getElementById("btnProceed");
        if (proceedBtn) setButtonLoading(proceedBtn, false);
      },
      onError: () => {
        sse = null;
        startPolling();
        pollPipelineShell();
      },
    });
  }

  document.getElementById("addNote").onclick = async () => {
    const body = document.getElementById("noteInput").value.trim();
    if (!body) return;
    await apiFetch("/api/applications/" + APP_ID + "/activities", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "note", body, author: "user" }),
    });
    document.getElementById("noteInput").value = "";
    await loadApp();
  };

  (async () => {
    const qs = new URLSearchParams(location.search);
    const taskId = qs.get("task");

    if (taskId) connectSSE(taskId);

    await loadAppShell();

    if (qs.get("hint") === "evaluate_done") {
      showToast(
        "Ocena gotowa — oferta jest w Inbox. Kliknij „Generuj CV i list”, aby przygotować dokumenty."
      );
      qs.delete("hint");
      history.replaceState(null, "", location.pathname + "?" + qs.toString());
    }

    if (!taskId && appData && appData.task_id && appData.pipeline_status === "running") {
      connectSSE(appData.task_id);
    }

    if (appData && isPipelineActive(appData)) {
      startPolling();
    }

    const scheduleDetails = window.requestIdleCallback || ((fn) => setTimeout(fn, 0));
    scheduleDetails(() => {
      loadAppDetails();
    });
  })();
})();
