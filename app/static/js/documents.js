(function () {
  const CATEGORIES = ["cv", "linkedin", "diplomas", "references", "applications"];

  async function loadDocuments() {
    const d = await fetch("/api/documents").then((r) => r.json());
    const cats = d.categories || {};
    const grid = document.getElementById("docGrid");
    grid.innerHTML = CATEGORIES.map((cat) => {
      const files = cats[cat] || [];
      const label = t("doc_category", cat);
      const list = files.length
        ? files.map((f) => `<li>${esc(f)}</li>`).join("")
        : "<li class='o_muted'>Brak plików</li>";
      return `<div class="o_doc_card" data-category="${cat}">
        <h3>${esc(label)}</h3>
        <ul class="o_doc_list">${list}</ul>
        <div class="o_upload_zone" data-upload="${cat}">
          Przeciągnij plik lub kliknij aby wybrać
          <input type="file" hidden data-file="${cat}" />
        </div>
      </div>`;
    }).join("");

    grid.querySelectorAll(".o_upload_zone").forEach((zone) => {
      const cat = zone.dataset.upload;
      const input = zone.querySelector('input[type="file"]');
      zone.onclick = () => input.click();
      zone.addEventListener("dragover", (e) => {
        e.preventDefault();
        zone.classList.add("dragover");
      });
      zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
      zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
        if (e.dataTransfer.files.length) uploadFile(cat, e.dataTransfer.files[0]);
      });
      input.onchange = () => {
        if (input.files.length) uploadFile(cat, input.files[0]);
      };
    });
  }

  async function uploadFile(category, file) {
    const fd = new FormData();
    fd.append("category", category);
    fd.append("file", file);
    try {
      await apiFetch("/api/documents/upload", { method: "POST", body: fd });
      showToast("Przesłano: " + file.name);
      await loadDocuments();
    } catch (err) {
      showToast("Błąd: " + err.message);
    }
  }

  loadDocuments();
})();
