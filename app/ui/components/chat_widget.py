"""Global sidebar chat widget for the AI assistant."""


def render_chat_widget() -> str:
    return """
  <section class="o_sidebar_chat" id="oChatWidget" aria-label="Asystent AI">
    <button type="button" class="o_chat_toggle" id="oChatToggle" aria-expanded="false">
      <span>Asystent</span>
      <span class="chevron" aria-hidden="true">›</span>
    </button>
    <div class="o_chat_panel" id="oChatPanel" hidden>
      <div class="o_chat_status" id="oChatStatus" role="status"></div>
      <div class="o_chat_messages" id="oChatMessages" aria-live="polite"></div>
      <div class="o_chat_pending" id="oChatPending" hidden></div>
      <div class="o_chat_memory" id="oChatMemory" hidden>
        <div class="o_chat_memory_title">Pamięć</div>
        <ul class="o_chat_memory_list" id="oChatMemoryList"></ul>
      </div>
      <form class="o_chat_form" id="oChatForm">
        <textarea
          id="oChatInput"
          class="o_chat_input"
          rows="2"
          placeholder="Zapytaj o inbox, aplikacje, profil…"
          aria-label="Wiadomość do asystenta"
        ></textarea>
        <button type="submit" class="o_chat_send" id="oChatSend">Wyślij</button>
      </form>
    </div>
  </section>"""
