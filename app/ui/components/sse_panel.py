from __future__ import annotations


def render_sse_panel() -> str:
    return """<div class="o_sse_panel hidden" id="ssePanel">
  <div class="o_progress"><div class="o_progress_fill" id="sseFill"></div></div>
  <pre class="o_log" id="sseLog"></pre>
</div>"""
