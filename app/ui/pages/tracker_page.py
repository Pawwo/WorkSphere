import json

from app.models.pipeline import HIRING_STAGES
from app.ui.components.control_panel import render_control_panel
from app.ui.i18n.pl import LABELS
from app.ui.layout import page

HIRING_FILTER_OPTIONS = "\n".join(
    ['        <option value="">wszystkie</option>']
    + [
        f'        <option value="{stage}">{LABELS["hiring_stage"][stage].lower()}</option>'
        for stage in HIRING_STAGES
    ]
)

TRACKER_BODY = render_control_panel(
    tabs_html="""
    <div class="o_tabs o_view_switcher" id="viewTabs">
      <button type="button" class="o_tab active" data-view="list">Lista</button>
      <button type="button" class="o_tab" data-view="kanban">Kanban</button>
    </div>""",
    filters_html=f"""
    <label>Etap rekrutacji
      <select id="fHiring">
{HIRING_FILTER_OPTIONS}
      </select>
    </label>
    <button type="button" class="btn btn-secondary btn-sm" id="reload">Odśwież</button>""",
) + """
<p class="o_summary" id="summary"></p>
<div id="listView" class="o_table_wrap">
  <table class="jobs" id="tracker"><thead><tr>
    <th>Data</th><th>Firma</th><th>Rola</th><th>Etap</th><th>Pipeline</th><th>Dopasowanie</th><th></th>
  </tr></thead><tbody></tbody></table>
</div>
<div id="kanbanView" class="o_kanban hidden"></div>
<script>window.HIRING_STAGES = __HIRING_STAGES_JSON__;</script>
"""


def tracker_page_html() -> str:
    body = TRACKER_BODY.replace("__HIRING_STAGES_JSON__", json.dumps(HIRING_STAGES))
    return page(
        "Aplikacje",
        "tracker",
        body,
        breadcrumbs=[("Aplikacje", None)],
        page_scripts=["/static/js/tracker.js"],
    )
