from app.ui.layout import page

SETUP_BODY = """
<div class="o_page_body">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:16px">
    <h1 style="margin:0">Profil kandydata</h1>
    <a href="/profile" class="btn btn-secondary btn-sm">Pliki profilu</a>
  </div>
  <div class="o_progress_bar"><div class="o_progress_bar_fill" id="progressFill"></div></div>
  <p class="o_progress_label" id="progressLabel">Ładowanie postępu…</p>

  <section class="o_section_box">
    <h2>Import CV</h2>
    <p class="o_page_intro">Wklej tekst CV — profil zostanie wygenerowany automatycznie.</p>
    <textarea id="cvText" rows="6" placeholder="Wklej treść CV…"></textarea>
    <button type="button" class="btn btn-primary" id="cvImportBtn">Importuj CV</button>
    <div id="cvImportBanner" class="hidden" style="margin-top:12px"></div>
  </section>

  <h2>Kreator profilu — 9 sekcji</h2>
  <div class="o_setup_layout">
    <nav class="o_setup_nav" id="sectionNav" aria-label="Sekcje profilu"></nav>
    <div>
      <form id="wizardForm" class="o_form_sheet"></form>
      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
        <button type="button" class="btn btn-secondary" id="saveBtn">Zapisz sekcję</button>
        <button type="button" class="btn btn-primary" id="finalizeBtn">Finalizuj profil</button>
      </div>
      <pre id="status" style="margin-top:12px"></pre>
    </div>
  </div>
</div>
"""


def setup_page_html() -> str:
    return page(
        "Profil",
        "setup",
        SETUP_BODY,
        breadcrumbs=[("Ustawienia", None), ("Profil", None)],
        page_scripts=["/static/js/setup.js"],
    )
