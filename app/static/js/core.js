/* Core UI helpers */

window.I18N = window.I18N || {};

function esc(s) {
  if (s == null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

function t(category, key) {
  if (!key) return "—";
  const cat = window.I18N[category];
  return cat && cat[key] ? cat[key] : key;
}

function showToast(msg, duration) {
  duration = duration || 3000;
  let el = document.getElementById("oToast");
  if (!el) {
    el = document.createElement("div");
    el.id = "oToast";
    el.className = "o_toast";
    el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove("show"), duration);
}

async function apiFetch(url, options) {
  const r = await fetch(url, options);
  const text = await r.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { error: text || r.statusText };
  }
  if (!r.ok) {
    const msg = data.detail || data.error || r.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

function setButtonLoading(btn, loading, label) {
  if (!btn) return;
  if (loading) {
    btn.dataset.origText = btn.textContent;
    btn.disabled = true;
    btn.textContent = label || "…";
    btn.classList.add("o_loading");
  } else {
    btn.disabled = false;
    btn.textContent = btn.dataset.origText || btn.textContent;
    btn.classList.remove("o_loading");
  }
}

function watchSseTask(taskId, onEvent, onDone) {
  let opts = {};
  if (onEvent && typeof onEvent === "object" && !onEvent.call) {
    opts = onEvent;
  } else {
    opts = { onEvent, onDone };
  }
  const es = new EventSource("/api/tasks/" + taskId + "/stream");
  es.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data);
      if (opts.onStage && d.stage) opts.onStage(d);
      if (opts.onEvent) opts.onEvent(d);
      if (d.status === "completed" || d.status === "failed") {
        es.close();
        if (opts.onDone) opts.onDone(d);
      }
    } catch (_) {
      /* ignore */
    }
  };
  es.onerror = () => {
    es.close();
    if (opts.onError) opts.onError();
  };
  return es;
}
