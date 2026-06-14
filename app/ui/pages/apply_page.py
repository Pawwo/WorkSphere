from app.ui.layout import page

APPLY_BODY = """
<div class="o_page_body">
  <p class="o_page_intro" id="applyIntro">Uruchom pipeline: parsowanie → ocena → generowanie CV → PDF → checklist → przygotowanie → tracker</p>
  <div class="o_form_sheet">
    <div class="o_form_group">
      <label class="o_form_label">URL ogłoszenia</label>
      <input id="url" type="url" placeholder="https://..." />
    </div>
    <div class="o_form_group">
      <label class="o_form_label">lub wklej tekst ogłoszenia</label>
      <textarea id="text" rows="6" placeholder="Treść ogłoszenia…"></textarea>
    </div>
    <div class="o_form_row">
      <label class="o_form_group_inline"><input type="checkbox" id="proceed" checked /> Generuj CV i list od razu</label>
      <label class="o_form_group_inline"><input type="checkbox" id="compile" checked /> Kompiluj PDF</label>
    </div>
    <div style="margin-top:1rem;display:flex;gap:8px;flex-wrap:wrap">
      <button type="button" class="btn btn-secondary" id="evalBtn">Tylko ocena</button>
      <button type="button" class="btn btn-primary" id="fullBtn">Uruchom pipeline</button>
    </div>
    <p id="status" class="o_summary"></p>
  </div>
</div>
"""


def apply_page_html() -> str:
    return page(
        "Nowa aplikacja",
        "inbox",
        APPLY_BODY,
        breadcrumbs=[("Inbox", "/inbox"), ("Nowa aplikacja", None)],
        page_scripts=["/static/js/apply.js"],
    )
