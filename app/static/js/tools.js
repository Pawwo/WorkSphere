(function () {
  const out = document.getElementById("out");
  const log = (x) => {
    out.textContent = typeof x === "string" ? x : JSON.stringify(x, null, 2);
  };

  const llmPreset = document.getElementById("llmPreset");
  const llmCustomUrl = document.getElementById("llmCustomUrl");
  const llmModel = document.getElementById("llmModel");
  const llmApiKey = document.getElementById("llmApiKey");
  const llmApiKeyHint = document.getElementById("llmApiKeyHint");
  const llmStatus = document.getElementById("llmStatus");

  let loadedCfg = null;

  function presetById(id) {
    return (loadedCfg?.presets || []).find((p) => p.id === id);
  }

  function syncFieldsFromPreset() {
    const id = llmPreset.value;
    if (id === "custom") return;
    const preset = presetById(id);
    if (!preset) return;
    llmCustomUrl.value = preset.base_url || "";
    if (preset.default_model && (!llmModel.value || llmModel.dataset.auto === "1")) {
      llmModel.value = preset.default_model;
      llmModel.dataset.auto = "1";
    }
  }

  function setLlmStatus(cfg) {
    const c = cfg.config || cfg;
    const h = cfg.health || c.health || {};
    const ok = h.ok ? "OK" : "niedostępny";
    const model = h.model || c.model || "—";
    const wake = c.wake_active ? "wake ON" : "wake OFF";
    llmStatus.textContent = `Aktywny: ${c.base_url || "—"} · model: ${model} · status: ${ok} · ${wake}`;
    if (c.api_key_set && c.api_key_hint) {
      llmApiKeyHint.textContent = `Zapisany klucz: ${c.api_key_hint}`;
    } else {
      llmApiKeyHint.textContent = "Brak zapisanego klucza API";
    }
  }

  async function loadLlmSettings() {
    const r = await fetch("/api/tools/llm");
    const cfg = await r.json();
    loadedCfg = cfg;
    llmPreset.innerHTML = "";
    (cfg.presets || []).forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.label;
      llmPreset.appendChild(opt);
    });
    const custom = document.createElement("option");
    custom.value = "custom";
    custom.textContent = "Inny (własny URL)";
    llmPreset.appendChild(custom);

    llmCustomUrl.value = cfg.base_url || "";
    llmModel.value = cfg.model || "";
    llmModel.dataset.auto = "0";
    llmApiKey.value = "";

    if (cfg.is_custom) {
      llmPreset.value = "custom";
    } else {
      llmPreset.value = cfg.preset_id || "8006";
    }
    setLlmStatus(cfg);
    return cfg;
  }

  llmPreset.addEventListener("change", () => {
    if (llmPreset.value === "custom") return;
    const preset = presetById(llmPreset.value);
    if (preset?.default_model) {
      llmModel.value = preset.default_model;
      llmModel.dataset.auto = "1";
    }
    syncFieldsFromPreset();
  });

  llmModel.addEventListener("input", () => {
    llmModel.dataset.auto = "0";
  });

  document.getElementById("llmSave").onclick = async () => {
    const btn = document.getElementById("llmSave");
    const url = llmCustomUrl.value.trim();
    if (!url) {
      log("Podaj URL API (pole URL).");
      return;
    }
    const body = {
      base_url: url,
      model: llmModel.value.trim() || undefined,
      api_key: llmApiKey.value.trim() || undefined,
    };
    setButtonLoading(btn, true, "Zapisuję…");
    try {
      const data = await apiFetch("/api/tools/llm", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      loadedCfg = data;
      llmApiKey.value = "";
      if (data.preset_id && data.preset_id !== "custom") {
        llmPreset.value = data.preset_id;
      } else if (data.is_custom) {
        llmPreset.value = "custom";
      }
      setLlmStatus(data);
      showToast("Zapisano ustawienia LLM");
      log({ saved: true, base_url: data.base_url, ...data });
    } catch (e) {
      log(String(e));
      llmStatus.textContent = "Zapis nie powiódł się";
    } finally {
      setButtonLoading(btn, false);
    }
  };

  document.getElementById("llmTest").onclick = async () => {
    const btn = document.getElementById("llmTest");
    setButtonLoading(btn, true, "Test…");
    llmStatus.textContent = "Testuję połączenie…";
    log("Testuję połączenie…");
    try {
      const r = await fetch("/api/tools/llm/test", { method: "POST" });
      const data = await r.json();
      if (!r.ok) {
        log(data);
        llmStatus.textContent = "Test połączenia nie powiódł się";
        return;
      }
      const startMsg = data.message || "Test połączenia…";
      llmStatus.textContent = startMsg;
      setLlmStatus(data);
      log(data);
    } catch (e) {
      log(String(e));
      llmStatus.textContent = "Błąd testu połączenia";
    } finally {
      setButtonLoading(btn, false);
    }
  };

  loadLlmSettings().catch((e) => log(String(e)));

  document.getElementById("expandPreview").onclick = async () => {
    const body = {
      include_github: document.getElementById("includeGithub").checked,
      include_documents: document.getElementById("includeDocuments").checked,
    };
    const r = await fetch("/api/expand/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    log(await r.json());
  };

  document.getElementById("expandApply").onclick = async () => {
    const body = {
      apply_all: true,
      include_github: document.getElementById("includeGithub").checked,
      include_documents: document.getElementById("includeDocuments").checked,
    };
    const r = await fetch("/api/expand/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    log(await r.json());
  };

  document.getElementById("upskillRun").onclick = async () => {
    const mode = document.getElementById("upskillMode").value;
    const text = document.getElementById("upskillText").value;
    const body =
      mode === "targeted"
        ? {
            mode,
            text: text.includes("http") ? null : text,
            url: text.includes("http") ? text : null,
          }
        : { mode };
    const r = await fetch("/api/upskill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    log(await r.json());
  };

  document.getElementById("resetPreview").onclick = async () => {
    const scope = document.getElementById("resetScope").value;
    const r = await fetch("/api/reset/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope }),
    });
    log(await r.json());
  };

  document.getElementById("resetExec").onclick = async () => {
    const scope = document.getElementById("resetScope").value;
    const confirmation = prompt("Wpisz RESET aby potwierdzić:");
    const r = await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope, confirmation }),
    });
    log(r.ok ? await r.json() : { error: (await r.json()).detail });
  };
})();
