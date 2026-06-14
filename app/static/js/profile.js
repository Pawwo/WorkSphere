(function () {
  let files = [];
  let currentFile = null;

  async function loadFileList() {
    const d = await fetch("/api/profile").then((r) => r.json());
    files = d.files || [];
    const st = d.status || {};
    const done = (st.sections_done || []).length;
    document.getElementById("profileStatus").textContent =
      st.complete ? "Profil sfinalizowany" : done + "/9 sekcji — " + (st.complete ? "kompletny" : "w trakcie");

    const nav = document.getElementById("fileList");
    nav.innerHTML = files
      .map(
        (f) =>
          `<a href="#" class="o_profile_file${f === currentFile ? " active" : ""}" data-file="${esc(f)}">${esc(f)}</a>`
      )
      .join("");
    nav.querySelectorAll(".o_profile_file").forEach((a) => {
      a.onclick = (e) => {
        e.preventDefault();
        loadPreview(a.dataset.file);
      };
    });
    if (files.length && !currentFile) loadPreview(files[0]);
  }

  async function loadPreview(filename) {
    currentFile = filename;
    document.querySelectorAll(".o_profile_file").forEach((a) => {
      a.classList.toggle("active", a.dataset.file === filename);
    });
    const preview = document.getElementById("filePreview");
    preview.innerHTML = "<p class='o_muted'>Ładowanie…</p>";
    try {
      const d = await fetch("/api/profile/" + encodeURIComponent(filename)).then((r) => r.json());
      preview.innerHTML = `<h2 style="margin-top:0;font-size:16px">${esc(filename)}</h2><pre>${esc(d.content || "")}</pre>`;
    } catch (err) {
      preview.innerHTML = "<p class='o_muted'>Plik nie istnieje — sfinalizuj profil w Setup.</p>";
    }
  }

  loadFileList();
})();
