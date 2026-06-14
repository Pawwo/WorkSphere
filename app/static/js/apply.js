(function () {
  let running = false;

  async function startApply(proceed) {
    if (running) return;
    running = true;
    const status = document.getElementById("status");
    status.textContent = "Uruchamianie pipeline…";
    try {
      const body = {
        url: document.getElementById("url").value || null,
        text: document.getElementById("text").value || null,
        proceed,
        compile_pdf: document.getElementById("compile").checked,
      };
      await startApplyAsync(body);
    } catch (e) {
      status.textContent = "Błąd: " + e.message;
    } finally {
      running = false;
    }
  }

  document.getElementById("evalBtn").onclick = () => startApply(false);
  document.getElementById("fullBtn").onclick = () => startApply(true);

  const qs = new URLSearchParams(location.search);
  if (qs.get("intent") === "add") {
    const intro = document.getElementById("applyIntro");
    if (intro) {
      intro.textContent =
        "Wklej link lub treść ogłoszenia (np. ze strony pracodawcy). Oferta trafi do Inbox i uruchomi się pipeline oceny.";
    }
  }
  if (qs.get("url")) {
    document.getElementById("url").value = qs.get("url");
    document.getElementById("proceed").checked = qs.get("proceed") !== "0";
    if (qs.get("autorun") === "1") startApply(qs.get("proceed") !== "0");
  }
})();
