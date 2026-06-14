from app.ui.layout import page

DOCUMENTS_BODY = """
<div class="o_page_body">
  <h1>Dokumenty</h1>
  <p class="o_page_intro">Prześlij pliki CV, LinkedIn, dyplomy, referencje i materiały aplikacyjne. Maks. 10 MB na plik.</p>
  <div class="o_doc_grid" id="docGrid">
    <p class="o_muted">Ładowanie…</p>
  </div>
</div>
"""


def documents_page_html() -> str:
    return page(
        "Dokumenty",
        "documents",
        DOCUMENTS_BODY,
        breadcrumbs=[("Ustawienia", None), ("Dokumenty", None)],
        page_scripts=["/static/js/documents.js"],
    )
