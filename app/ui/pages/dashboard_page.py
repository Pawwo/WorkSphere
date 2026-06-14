from app.ui.layout import page

DASHBOARD_BODY = """
<div class="o_page_body">
  <h1>System — diagnostyka</h1>
  <div class="o_grid" id="cards"></div>
  <div class="o_dashboard_section">
    <h2>Ostatnie scrape</h2>
    <div id="scrapes"></div>
  </div>
  <div class="o_dashboard_section">
    <h2>Ostatnie aplikacje</h2>
    <div id="applies"></div>
  </div>
  <div class="o_dashboard_section">
    <h2>Nowe oferty (top 5)</h2>
    <div id="jobPreview"></div>
  </div>
</div>
"""


def dashboard_page_html() -> str:
    return page(
        "System",
        "dashboard",
        DASHBOARD_BODY,
        breadcrumbs=[("Ustawienia", None), ("System", None)],
        page_scripts=["/static/js/dashboard.js"],
    )
