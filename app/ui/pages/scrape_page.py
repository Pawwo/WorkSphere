from app.ui.components.sse_panel import render_sse_panel
from app.ui.layout import page

SCRAPE_BODY = f"""
<div class="o_page_body">
  <p class="o_page_intro">Domyślny profil full: 7 portali (pracuj, praca.pl, JustJoin, NoFluffJobs, TheProtocol, RocketJobs, LinkedIn), oferty z ostatnich 48h. Batch: top 3 kategorie z search-queries.md.</p>

  <section class="o_section_box">
    <h2>Pojedyncze zapytanie</h2>
    <div class="o_form_group">
      <label class="o_form_label">Zapytanie</label>
      <input id="query" placeholder="np. Python developer Warszawa" />
    </div>
    <div class="o_form_row">
      <label>Limit <input id="limit" type="number" value="20" min="1" max="50" style="width:80px" /></label>
      <label>Dni <input id="days" type="number" value="2" min="1" max="90" style="width:80px" /></label>
      <label class="o_form_group_inline"><input type="checkbox" id="broad" /> +LinkedIn (pojedynczy scrape)</label>
      <label class="o_form_group_inline"><input type="checkbox" id="allCategories" /> Wszystkie kategorie zapytań (batch)</label>
    </div>
    <button type="button" class="btn btn-primary" id="run">Scrape jednej roli</button>
  </section>

  <section class="o_section_box">
    <h2>Batch — search-queries.md</h2>
    <p id="batchInfo">Ładowanie zapytań…</p>
    <p id="batchSource" class="o_muted" style="font-size:13px"></p>
    <ul id="batchQueries" style="font-size:13px;max-height:160px;overflow:auto;margin:0;padding-left:1.2rem"></ul>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
      <button type="button" class="btn btn-secondary" id="refreshQueries">Odśwież z profilu</button>
      <button type="button" class="btn btn-primary" id="runBatch">Scrape batch</button>
    </div>
  </section>

  {render_sse_panel()}
  <div id="resultsTable" style="margin-top:16px"></div>
</div>
"""


def scrape_page_html() -> str:
    return page(
        "Scrapowanie",
        "scrape",
        SCRAPE_BODY,
        breadcrumbs=[("Ustawienia", None), ("Scrapowanie", None)],
        page_scripts=["/static/js/scrape.js"],
    )
