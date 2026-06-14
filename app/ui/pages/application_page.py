import json

from app.models.pipeline import HIRING_STAGES, PIPELINE_STAGES
from app.ui.layout import page

APPLICATION_BODY = """
<div class="o_form_view" id="appForm">
  <div class="o_form_header">
    <h1 id="appTitle">Ładowanie…</h1>
    <div class="o_subtitle" id="appSubtitle"></div>
    <div id="preflightBanner" class="o_summary" style="display:none;margin-top:8px"></div>
  </div>
  <div class="o_smart_buttons" id="smartButtons"></div>
  <div class="o_statusbar" id="statusbar"></div>
  <div id="liveProgressWrap" class="o_live_progress_wrap" style="display:none">
    <div id="liveProgress" class="o_summary o_muted"></div>
  </div>
  <div class="o_quick_edit" id="quickEdit"></div>
  <div class="o_form_body">
    <div class="o_form_main">
      <div class="o_notebook_tabs" id="notebookTabs">
        <button type="button" class="o_notebook_tab active" data-tab="overview">Przegląd</button>
        <button type="button" class="o_notebook_tab" data-tab="evaluation">Ocena</button>
        <button type="button" class="o_notebook_tab" data-tab="documents">Dokumenty</button>
        <button type="button" class="o_notebook_tab" data-tab="review">Recenzja</button>
        <button type="button" class="o_notebook_tab" data-tab="verify">Weryfikacja</button>
        <button type="button" class="o_notebook_tab" data-tab="prep">Przygotowanie</button>
      </div>
      <div class="o_tab_panel active" id="tab-overview"><div id="panelOverview"></div></div>
      <div class="o_tab_panel" id="tab-evaluation"><div id="panelEvaluation"></div></div>
      <div class="o_tab_panel" id="tab-documents"><div id="panelDocuments"></div></div>
      <div class="o_tab_panel" id="tab-review"><div id="panelReview"></div></div>
      <div class="o_tab_panel" id="tab-verify"><div id="panelVerify"></div></div>
      <div class="o_tab_panel" id="tab-prep"><div id="panelPrep"></div></div>
    </div>
    <aside class="o_chatter">
      <h3>Aktywność</h3>
      <div id="chatterList"></div>
      <div style="margin-top:12px">
        <textarea id="noteInput" rows="3" placeholder="Dodaj notatkę…"></textarea>
        <button type="button" class="btn btn-secondary btn-sm" id="addNote" style="margin-top:6px">Dodaj</button>
      </div>
    </aside>
  </div>
  <div class="o_form_footer" id="formFooter"></div>
</div>
<script>window.__APP_ID__ = __APP_ID_PLACEHOLDER__; window.PIPELINE_STAGES = __PIPELINE_STAGES_JSON__; window.HIRING_STAGES = __HIRING_STAGES_JSON__;</script>
"""


def application_page_html(app_id: int) -> str:
    body = APPLICATION_BODY.replace("__APP_ID_PLACEHOLDER__", str(app_id)).replace(
        "__PIPELINE_STAGES_JSON__", json.dumps(PIPELINE_STAGES)
    ).replace(
        "__HIRING_STAGES_JSON__", json.dumps(HIRING_STAGES)
    )
    return page(
        "Aplikacja",
        "tracker",
        body,
        breadcrumbs=[("Aplikacje", "/tracker"), (f"#{app_id}", None)],
        page_scripts=["/static/js/application.js"],
    )
