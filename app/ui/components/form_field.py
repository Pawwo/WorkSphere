from __future__ import annotations


def render_form_group(
    label: str,
    input_html: str,
    *,
    hint: str = "",
    required: bool = False,
    inline: bool = False,
) -> str:
    req = ' <span class="o_required">*</span>' if required else ""
    hint_html = f'<span class="o_field_hint">{hint}</span>' if hint else ""
    cls = "o_form_group o_form_group_inline" if inline else "o_form_group"
    return f"""<div class="{cls}">
  <label class="o_form_label">{label}{req}{hint_html}</label>
  <div class="o_form_input">{input_html}</div>
</div>"""
