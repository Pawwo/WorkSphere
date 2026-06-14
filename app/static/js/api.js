/**
 * Shared API surface — implementations live in core.js (loaded first).
 * Use api.fetch(), api.sse(), api.toast() for consistency across pages.
 */
window.api = {
  fetch: apiFetch,
  sse: watchSseTask,
  toast: showToast,
  esc: esc,
  t: t,
};
