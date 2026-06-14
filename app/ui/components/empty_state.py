from __future__ import annotations


def render_empty_state(
    title: str,
    hint: str = "",
    primary_cta: str = "",
) -> str:
    hint_html = f"<p>{hint}</p>" if hint else ""
    cta_html = f"<p>{primary_cta}</p>" if primary_cta else ""
    return f"""<div class="o_empty_state">
  <h2>{title}</h2>
  {hint_html}
  {cta_html}
</div>"""
