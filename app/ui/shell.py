"""Odoo 20-inspired application shell — sidebar, topbar, content area."""

from __future__ import annotations

from app.ui.i18n.pl import labels_json
from app.ui.components.chat_widget import render_chat_widget

MAIN_NAV = [
    ("inbox", "Inbox", "/inbox", "inboxBadge"),
    ("tracker", "Aplikacje", "/tracker", "trackerBadge"),
]

SETTINGS_NAV = [
    ("setup", "Profil", "/setup"),
    ("documents", "Dokumenty", "/documents"),
    ("scrape", "Scrapowanie", "/scrape"),
    ("tools", "Narzędzia", "/tools"),
    ("dashboard", "System", "/dashboard"),
]

CSS_FILES = [
    "/static/css/tokens.css",
    "/static/css/shell.css",
    "/static/css/components.css",
    "/static/css/views.css",
    "/static/css/extras.css",
]


def _nav_link(key: str, label: str, href: str, active: str, badge_id: str | None) -> str:
    cls = "o_nav_item active" if key == active else "o_nav_item"
    badge = (
        f'<span class="o_nav_badge" id="{badge_id}" style="display:none">0</span>'
        if badge_id
        else ""
    )
    return f'<a href="{href}" class="{cls}">{label}{badge}</a>'


def render_sidebar(active: str) -> str:
    main_links = "".join(_nav_link(k, lbl, href, active, bid) for k, lbl, href, bid in MAIN_NAV)
    settings_links = "".join(
        f'<a href="{href}" class="o_nav_item{" active" if k == active else ""}">{lbl}</a>'
        for k, lbl, href in SETTINGS_NAV
    )
    return f"""
<aside class="o_sidebar" id="oSidebar">
  <div class="o_sidebar_brand">
    WorkSphere
  </div>
  <nav class="o_sidebar_nav" aria-label="Codziennie">
    <div class="o_nav_section_title">Codziennie</div>
    {main_links}
  </nav>
  {render_chat_widget()}
  <button type="button" class="o_settings_toggle" id="oSettingsToggle" aria-expanded="false">
    <span>⚙ Ustawienia</span>
    <span class="chevron" aria-hidden="true">›</span>
  </button>
  <nav class="o_settings_sub" id="oSettingsSub" aria-label="Ustawienia">
    {settings_links}
    <a href="/docs" class="o_nav_item" target="_blank" rel="noopener">API docs</a>
  </nav>
</aside>"""


def render_topbar(breadcrumbs: list[tuple[str, str | None]], actions: str = "") -> str:
    crumbs = []
    for label, href in breadcrumbs:
        if href:
            crumbs.append(f'<a href="{href}">{label}</a>')
        else:
            crumbs.append(f'<span class="current">{label}</span>')
    crumb_html = '<span class="sep">/</span>'.join(crumbs)
    return f"""
<header class="o_topbar">
  <button type="button" class="o_menu_toggle" id="oMenuToggle" aria-label="Menu">☰</button>
  <div class="o_breadcrumb">{crumb_html}</div>
  <div class="o_topbar_actions">{actions}</div>
</header>"""


def _css_links() -> str:
    return "\n".join(f'  <link rel="stylesheet" href="{href}" />' for href in CSS_FILES)


def _script_tags(page_scripts: list[str] | None = None) -> str:
    scripts = [
        f'<script>window.I18N = {labels_json()};</script>',
        '<script src="/static/js/core.js"></script>',
        '<script src="/static/js/api.js"></script>',
        '<script src="/static/js/apply-flow.js"></script>',
        '<script src="/static/js/shell.js"></script>',
        '<script src="/static/js/chat.js"></script>',
    ]
    for src in page_scripts or []:
        scripts.append(f'<script src="{src}"></script>')
    return "\n".join(f"  {s}" for s in scripts)


def render_page(
    title: str,
    active: str,
    body: str,
    *,
    breadcrumbs: list[tuple[str, str | None]] | None = None,
    top_actions: str = "",
    extra_head: str = "",
    page_scripts: list[str] | None = None,
) -> str:
    if breadcrumbs is None:
        breadcrumbs = [(title, None)]
    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} — WorkSphere</title>
{_css_links()}
  {extra_head}
</head>
<body data-active="{active}">
<div class="o_web_client">
  {render_sidebar(active)}
  <div class="o_main">
    {render_topbar(breadcrumbs, top_actions)}
    <main class="o_content">
      {body}
    </main>
  </div>
</div>
{_script_tags(page_scripts)}
</body>
</html>"""
