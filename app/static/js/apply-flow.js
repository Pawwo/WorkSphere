/** Shared async apply → application page redirect */
async function startApplyAsync({ url, text, proceed, compile_pdf }) {
  const j = await apiFetch("/api/apply/async", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: url || null,
      text: text || null,
      proceed: !!proceed,
      compile_pdf: compile_pdf !== false,
    }),
  });
  let dest =
    "/applications/" + j.application_id + "?task=" + encodeURIComponent(j.task_id);
  if (!proceed) dest += "&hint=evaluate_done";
  window.location.href = dest;
}
