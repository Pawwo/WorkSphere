"""Shared HTML layout — delegates to Odoo-like shell."""

from __future__ import annotations

from app.ui.shell import render_page


def page(
    title: str,
    active: str,
    body: str,
    extra_head: str = "",
    *,
    breadcrumbs: list[tuple[str, str | None]] | None = None,
    top_actions: str = "",
    page_scripts: list[str] | None = None,
) -> str:
    return render_page(
        title,
        active,
        body,
        breadcrumbs=breadcrumbs,
        top_actions=top_actions,
        extra_head=extra_head,
        page_scripts=page_scripts,
    )
