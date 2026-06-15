from app.ui.layout import page

TOOLS_BODY = """
<div class="o_page_body">
  <h1>Narzędzia</h1>
  <section class="o_section_box">
    <h2>LLM — endpoint</h2>
    <p class="o_page_intro">Serwer OpenAI-compatible (llama-server, Ollama, OpenRouter lub własny URL). Zapis trafia do <code>config.yaml</code>.</p>
    <div class="o_form_group">
      <label class="o_form_label" for="llmPreset">Serwer LLM</label>
      <select id="llmPreset">
        <option value="">Ładowanie…</option>
      </select>
    </div>
    <div class="o_form_group">
      <label class="o_form_label" for="llmCustomUrl">URL API</label>
      <input id="llmCustomUrl" type="text" placeholder="http://127.0.0.1:8006/v1" />
    </div>
    <div class="o_form_group">
      <label class="o_form_label" for="llmModel">Model</label>
      <input id="llmModel" type="text" placeholder="your-model-name" />
    </div>
    <div class="o_form_group">
      <label class="o_form_label" for="llmApiKey">API Key</label>
      <input id="llmApiKey" type="password" placeholder="Puste = bez zmiany przy zapisie" autocomplete="off" />
      <p class="o_muted" id="llmApiKeyHint" style="font-size:12px;margin-top:4px"></p>
    </div>
    <p id="llmStatus" class="o_muted" style="font-size:13px;margin-top:8px">Status: —</p>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
      <button type="button" class="btn btn-primary" id="llmSave">Zapisz</button>
      <button type="button" class="btn btn-secondary" id="llmTest">Test połączenia</button>
    </div>
  </section>
  <section class="o_section_box">
    <h2>Expand — rozszerz profil</h2>
    <p class="o_page_intro">Skanuje dokumenty i GitHub, proponuje nowe kompetencje.</p>
    <label class="o_form_group_inline"><input type="checkbox" id="includeGithub" checked /> Uwzględnij GitHub</label>
    <label class="o_form_group_inline"><input type="checkbox" id="includeDocuments" checked /> Uwzględnij dokumenty</label>
    <div style="margin-top:12px;display:flex;gap:8px">
      <button type="button" class="btn btn-secondary" id="expandPreview">Podgląd</button>
      <button type="button" class="btn btn-primary" id="expandApply">Zastosuj wszystkie</button>
    </div>
  </section>
  <section class="o_section_box">
    <h2>Upskill — plan rozwoju</h2>
    <select id="upskillMode">
      <option value="aggregate">Zbiorczy (z trackera)</option>
      <option value="targeted">Ukierunkowany (URL/tekst oferty)</option>
    </select>
    <textarea id="upskillText" rows="4" placeholder="URL lub tekst oferty (tryb ukierunkowany)"></textarea>
    <button type="button" class="btn btn-primary" id="upskillRun">Generuj raport</button>
  </section>
  <section class="o_section_box">
    <h2>Reset — wyczyść dane</h2>
    <p class="o_page_intro">
      <strong>profil</strong> — profil, search-queries, seen_jobs ·
      <strong>dokumenty</strong> — uploads, cv, listy ·
      <strong>all</strong> — wszystko + triage + aplikacje SQLite
    </p>
    <select id="resetScope">
      <option value="profile">profil</option>
      <option value="documents">dokumenty</option>
      <option value="all">wszystko</option>
    </select>
    <div style="margin-top:12px;display:flex;gap:8px">
      <button type="button" class="btn btn-secondary" id="resetPreview">Podgląd</button>
      <button type="button" class="btn btn-primary" id="resetExec">Wykonaj (wpisz RESET)</button>
    </div>
  </section>
  <pre id="out"></pre>
</div>
"""


def tools_page_html() -> str:
    return page(
        "Narzędzia",
        "tools",
        TOOLS_BODY,
        breadcrumbs=[("Ustawienia", None), ("Narzędzia", None)],
        page_scripts=["/static/js/tools.js"],
    )
