from __future__ import annotations


def render_control_panel(
    *,
    tabs_html: str = "",
    filters_html: str = "",
    actions_html: str = "",
    view_toggle_html: str = "",
    extra_class: str = "",
) -> str:
    cls = f"o_control_panel {extra_class}".strip()
    parts = []
    if tabs_html:
        parts.append(f'<div class="o_tabs">{tabs_html}</div>')
    if view_toggle_html:
        parts.append(f'<div class="o_view_switcher o_tabs">{view_toggle_html}</div>')
    if filters_html:
        parts.append(f'<div class="o_filters">{filters_html}</div>')
    if actions_html:
        parts.append(f'<div class="o_control_actions">{actions_html}</div>')
    return f'<div class="{cls}">{"".join(parts)}</div>'
