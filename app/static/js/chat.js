/* Global sidebar AI assistant */

(function () {
  const THREAD_ID = "default";
  let pendingConfirm = null;
  let sending = false;

  function el(id) {
    return document.getElementById(id);
  }

  function initChat() {
    const toggle = el("oChatToggle");
    const panel = el("oChatPanel");
    const form = el("oChatForm");
    if (!toggle || !panel || !form) return;

    const isMobile = window.matchMedia("(max-width: 991px)").matches;
    const stored = localStorage.getItem("chatOpen");
    const open = stored === "1" || (!isMobile && stored === null);
    setChatOpen(open);

    toggle.addEventListener("click", () => {
      const willOpen = !toggle.classList.contains("open");
      setChatOpen(willOpen);
      localStorage.setItem("chatOpen", willOpen ? "1" : "0");
    });

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      sendMessage();
    });

    const input = el("oChatInput");
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendMessage();
        }
        if (e.key === "Escape") {
          setChatOpen(false);
          localStorage.setItem("chatOpen", "0");
        }
      });
    }

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "o_chat_confirm";
    confirmBtn.textContent = "Potwierdź";
    confirmBtn.id = "oChatConfirm";
    confirmBtn.addEventListener("click", () => confirmPending());

    loadStatus();
    loadMessages();
    loadMemory();
  }

  function setChatOpen(open) {
    const toggle = el("oChatToggle");
    const panel = el("oChatPanel");
    if (!toggle || !panel) return;
    toggle.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      panel.removeAttribute("hidden");
    } else {
      panel.setAttribute("hidden", "");
    }
  }

  function appendMessage(role, content, toolRuns) {
    const box = el("oChatMessages");
    if (!box) return;
    const div = document.createElement("div");
    div.className = "o_chat_msg " + role;
    div.textContent = content;
    if (toolRuns && toolRuns.length) {
      const tools = document.createElement("div");
      tools.className = "o_chat_tools";
      tools.textContent = "Narzędzia: " + toolRuns.map((t) => t.tool || t.name).join(", ");
      div.appendChild(tools);
    }
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function renderMessages(messages) {
    const box = el("oChatMessages");
    if (!box) return;
    box.innerHTML = "";
    (messages || []).forEach((m) => {
      appendMessage(m.role === "user" ? "user" : "assistant", m.content, m.tool_calls);
    });
  }

  function showPending(confirm) {
    pendingConfirm = confirm;
    const wrap = el("oChatPending");
    if (!wrap) return;
    if (!confirm) {
      wrap.setAttribute("hidden", "");
      wrap.innerHTML = "";
      return;
    }
    wrap.removeAttribute("hidden");
    wrap.innerHTML = "";
    const text = document.createElement("span");
    text.className = "o_chat_pending_text";
    text.textContent = confirm.message || "Potwierdź akcję";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "o_chat_confirm";
    btn.textContent = "Potwierdź";
    btn.addEventListener("click", confirmPending);
    wrap.appendChild(text);
    wrap.appendChild(btn);
  }

  async function loadStatus() {
    const statusEl = el("oChatStatus");
    if (!statusEl) return;
    try {
      const d = await api.fetch("/api/assistant/status");
      if (d.llm_ok) {
        statusEl.className = "o_chat_status";
        statusEl.textContent = "LLM: OK · pamięć: " + (d.memory_facts_count || 0);
      } else {
        statusEl.className = "o_chat_status offline";
        statusEl.innerHTML =
          'LLM offline — <a href="/tools">ustawienia</a>';
      }
    } catch {
      statusEl.className = "o_chat_status offline";
      statusEl.textContent = "Asystent niedostępny";
    }
  }

  async function loadMessages() {
    try {
      const d = await api.fetch("/api/assistant/threads/" + THREAD_ID + "/messages");
      renderMessages(d.messages);
    } catch {
      /* ignore */
    }
  }

  async function loadMemory() {
    const memWrap = el("oChatMemory");
    const list = el("oChatMemoryList");
    if (!memWrap || !list) return;
    try {
      const d = await api.fetch("/api/assistant/memory");
      const facts = d.facts || [];
      if (!facts.length) {
        memWrap.setAttribute("hidden", "");
        return;
      }
      memWrap.removeAttribute("hidden");
      list.innerHTML = facts
        .slice(0, 8)
        .map(
          (f) =>
            '<li><span>' +
            esc(f.key) +
            ": " +
            esc((f.content || "").slice(0, 60)) +
            '</span><button type="button" class="o_chat_memory_del" data-id="' +
            f.id +
            '" aria-label="Usuń">×</button></li>'
        )
        .join("");
      list.querySelectorAll(".o_chat_memory_del").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-id");
          try {
            await api.fetch("/api/assistant/memory/" + id, { method: "DELETE" });
            loadMemory();
            loadStatus();
          } catch (err) {
            api.toast(err.message);
          }
        });
      });
    } catch {
      memWrap.setAttribute("hidden", "");
    }
  }

  async function sendMessage(confirmActionId) {
    if (sending) return;
    const input = el("oChatInput");
    const sendBtn = el("oChatSend");
    const content = (input && input.value.trim()) || (confirmActionId ? "Potwierdzam" : "");
    if (!content && !confirmActionId) return;

    sending = true;
    if (sendBtn) sendBtn.disabled = true;
    const statusEl = el("oChatStatus");
    if (statusEl) statusEl.textContent = "Myślę…";
    if (!confirmActionId && input) {
      appendMessage("user", content);
      input.value = "";
    }

    try {
      const body = { content: content };
      if (confirmActionId) body.confirm_action_id = confirmActionId;
      const d = await api.fetch("/api/assistant/threads/" + THREAD_ID + "/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (d.content) {
        appendMessage(
          d.type === "error" || d.ok === false ? "error" : "assistant",
          d.content,
          d.tool_runs
        );
      }
      if (d.pending_confirm) {
        showPending(d.pending_confirm);
      } else {
        showPending(null);
        pendingConfirm = null;
      }
      loadStatus();
      loadMemory();
    } catch (err) {
      appendMessage("error", err.message || "Błąd wysyłania");
      api.toast(err.message);
    } finally {
      sending = false;
      if (sendBtn) sendBtn.disabled = false;
    }
  }

  function confirmPending() {
    if (!pendingConfirm || !pendingConfirm.confirm_action_id) return;
    sendMessage(pendingConfirm.confirm_action_id);
    showPending(null);
    pendingConfirm = null;
  }

  document.addEventListener("DOMContentLoaded", initChat);
})();
