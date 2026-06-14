from app.ui.layout import page

PROFILE_BODY = """
<div class="o_page_body">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:16px">
    <h1 style="margin:0">Pliki profilu</h1>
    <a href="/setup" class="btn btn-secondary btn-sm">Edytuj profil</a>
  </div>
  <p class="o_progress_label" id="profileStatus">Ładowanie…</p>
  <div class="o_profile_layout">
    <nav class="o_profile_list" id="fileList" aria-label="Pliki profilu"></nav>
    <div class="o_profile_preview" id="filePreview">
      <p class="o_muted">Wybierz plik z listy po lewej.</p>
    </div>
  </div>
</div>
"""


def profile_page_html() -> str:
    return page(
        "Pliki profilu",
        "profile",
        PROFILE_BODY,
        breadcrumbs=[("Ustawienia", None), ("Pliki profilu", None)],
        page_scripts=["/static/js/profile.js"],
    )
