(function () {
let schema = null;
let current = 1;
const statusEl = document.getElementById('status');

function log(msg) { statusEl.textContent = typeof msg === 'string' ? msg : JSON.stringify(msg, null, 2); }

async function loadSchema() {
  const r = await fetch('/api/setup/wizard');
  schema = await r.json();
  await loadProgress();
  renderNav();
  renderSection(current);
}

async function loadProgress() {
  try {
    const st = await fetch('/api/setup/status').then(r => r.json());
    const done = (st.sections_done || []).length;
    document.getElementById('progressLabel').textContent = done + '/9 sekcji uzupełnionych';
    document.getElementById('progressFill').style.width = Math.round((done / 9) * 100) + '%';
    window._sectionsDone = st.sections_done || [];
  } catch (_) { /* ignore */ }
}

function renderNav() {
  const nav = document.getElementById('sectionNav');
  const done = window._sectionsDone || [];
  nav.innerHTML = schema.sections.map(s => {
    const cls = ['o_setup_nav_item'];
    if (s.id === current) cls.push('active');
    if (done.includes(s.id)) cls.push('done');
    return `<button type="button" class="${cls.join(' ')}" data-id="${s.id}">${s.id}. ${esc(s.title)}</button>`;
  }).join('');
  nav.querySelectorAll('button').forEach(b => b.onclick = () => { current = +b.dataset.id; renderNav(); renderSection(current); });
}

function renderEducationEntry(i, item) {
  item = item || {};
  return `<fieldset class="entry" data-entry-type="education">
    <legend>Wykształcenie ${i + 1} <button type="button" class="btn btn-secondary btn-sm remove-entry">Usuń</button></legend>
    <label>Stopień / kierunek<input data-key="degree" value="${esc(item.degree)}" placeholder="np. Licencjat, Informatyka" /></label>
    <label>Uczelnia<input data-key="institution" value="${esc(item.institution)}" /></label>
    <div class="row">
      <label>Okres<input data-key="years" value="${esc(item.years || item.period)}" placeholder="2003–2006" /></label>
      <label>Dziedzina (opcj.)<input data-key="field" value="${esc(item.field)}" /></label>
    </div>
    <label>Tematy / praca (opcj.)<input data-key="topics" value="${esc(item.topics)}" /></label>
  </fieldset>`;
}

function renderExperienceEntry(i, item) {
  item = item || {};
  const bullets = Array.isArray(item.bullets) ? item.bullets.join('\\n') : '';
  return `<fieldset class="entry" data-entry-type="experience">
    <legend>Stanowisko ${i + 1} <button type="button" class="btn btn-secondary btn-sm remove-entry">Usuń</button></legend>
    <label>Tytuł<input data-key="title" value="${esc(item.title)}" /></label>
    <label>Firma<input data-key="company" value="${esc(item.company)}" /></label>
    <div class="row">
      <label>Od<input data-key="start" value="${esc(item.start)}" placeholder="08.2025" /></label>
      <label>Do<input data-key="end" value="${esc(item.end || 'present')}" placeholder="obecnie" /></label>
    </div>
    <label>Lokalizacja (opcj.)<input data-key="location" value="${esc(item.location)}" /></label>
    <label>Osiągnięcia (jedna na linię)<textarea data-key="bullets" rows="4">${esc(bullets)}</textarea></label>
  </fieldset>`;
}

function languageOptions(selected) {
  const opts = (schema.language_options || []).map(o =>
    `<option value="${esc(o.value)}"${o.value === selected ? ' selected' : ''}>${esc(o.label)}</option>`
  ).join('');
  return `<option value="">— wybierz —</option>${opts}`;
}

function levelOptions(selected) {
  const opts = (schema.level_options || []).map(o =>
    `<option value="${esc(o.value)}"${o.value === selected ? ' selected' : ''}>${esc(o.label)}</option>`
  ).join('');
  return `<option value="">— wybierz —</option>${opts}`;
}

function renderLanguageEntry(i, item) {
  item = item || {};
  return `<fieldset class="entry" data-entry-type="language">
    <legend>Język ${i + 1} <button type="button" class="btn btn-secondary btn-sm remove-entry">Usuń</button></legend>
    <div class="row">
      <label>Język<select data-key="language">${languageOptions(item.language)}</select></label>
      <label>Poziom<select data-key="level">${levelOptions(item.level)}</select></label>
    </div>
  </fieldset>`;
}

function renderReferenceEntry(i, item) {
  item = item || {};
  return `<fieldset class="entry" data-entry-type="reference">
    <legend>Referencja ${i + 1} <button type="button" class="btn btn-secondary btn-sm remove-entry">Usuń</button></legend>
    <label>Imię i nazwisko<input data-key="name" value="${esc(item.name)}" /></label>
    <div class="row">
      <label>Stanowisko<input data-key="title" value="${esc(item.title)}" /></label>
      <label>Firma<input data-key="company" value="${esc(item.company)}" /></label>
    </div>
    <div class="row">
      <label>Email<input data-key="email" value="${esc(item.email)}" /></label>
      <label>Telefon<input data-key="phone" value="${esc(item.phone)}" /></label>
    </div>
  </fieldset>`;
}

function renderListField(f, val) {
  const items = Array.isArray(val) ? val : [];
  const empty = items.length ? items : [{}];
  let entriesHtml = '';
  let addType = '';
  if (f.type === 'education_list') {
    entriesHtml = empty.map((item, i) => renderEducationEntry(i, item)).join('');
    addType = 'education';
  } else if (f.type === 'experience_list') {
    entriesHtml = empty.map((item, i) => renderExperienceEntry(i, item)).join('');
    addType = 'experience';
  } else if (f.type === 'reference_list') {
    entriesHtml = empty.map((item, i) => renderReferenceEntry(i, item)).join('');
    addType = 'reference';
  } else if (f.type === 'language_list') {
    const min = f.min_items || 3;
    const rows = items.length >= min ? items : [...items, ...Array(Math.max(0, min - items.length)).fill({})];
    entriesHtml = rows.map((item, i) => renderLanguageEntry(i, item)).join('');
    addType = 'language';
  }
  return `<div class="list-field" data-field="${f.name}" data-list-type="${f.type}">
    <label>${f.label}</label>
    <div class="entries">${entriesHtml}</div>
    <button type="button" class="btn btn-secondary add-entry" data-add-type="${addType}">+ Dodaj pozycję</button>
  </div>`;
}

function renderSection(id) {
  const sec = schema.sections.find(s => s.id === id);
  const saved = schema.state['section' + id] || {};
  const form = document.getElementById('wizardForm');
  form.innerHTML = sec.fields.map(f => {
    const val = saved[f.name];
    if (f.type === 'textarea') {
      return `<label>${f.label}<textarea name="${f.name}" rows="3">${esc(val)||''}</textarea></label>`;
    }
    if (f.type === 'string_list') {
      const text = Array.isArray(val) ? val.join('\\n') : (val || '');
      return `<label>${f.label} (jedna pozycja na linię)<textarea name="${f.name}" rows="4">${esc(text)}</textarea></label>`;
    }
    if (f.type === 'education_list' || f.type === 'experience_list' || f.type === 'reference_list' || f.type === 'language_list') {
      if (f.type === 'language_list' && current === 1 && (!val || !val.length)) {
        const warn = document.getElementById('languageWarn');
        if (warn) warn.classList.remove('hidden');
      }
      return (f.type === 'language_list' && current === 1
        ? '<p id="languageWarn" class="o_banner hidden">Uzupełnij min. 3 języki z poziomem — od tego zależy filtrowanie ogłoszeń w inboxie.</p>'
        : '') + renderListField(f, val);
    }
    const ph = f.placeholder || f.default || '';
    const v = val != null && val !== undefined ? val : '';
    return `<label>${f.label}<input name="${f.name}" value="${esc(v)}" placeholder="${esc(ph)}" /></label>`;
  }).join('');
}

function renumberEntries(container) {
  container.querySelectorAll('.entry').forEach((entry, i) => {
    const legend = entry.querySelector('legend');
    if (!legend) return;
    const btn = legend.querySelector('.remove-entry');
    const labels = { education: 'Wykształcenie', experience: 'Stanowisko', reference: 'Referencja', language: 'Język' };
    const type = entry.dataset.entryType || 'education';
    legend.textContent = '';
    legend.append(`${labels[type] || 'Pozycja'} ${i + 1} `);
    if (btn) legend.appendChild(btn);
  });
}

document.getElementById('wizardForm').addEventListener('click', (e) => {
  const addBtn = e.target.closest('.add-entry');
  if (addBtn) {
    const wrap = addBtn.closest('.list-field');
    const entries = wrap.querySelector('.entries');
    const i = entries.querySelectorAll('.entry').length;
    const type = addBtn.dataset.addType;
    const html = type === 'education' ? renderEducationEntry(i, {})
      : type === 'experience' ? renderExperienceEntry(i, {})
      : type === 'language' ? renderLanguageEntry(i, {})
      : renderReferenceEntry(i, {});
    entries.insertAdjacentHTML('beforeend', html);
    return;
  }
  const rmBtn = e.target.closest('.remove-entry');
  if (rmBtn) {
    const entry = rmBtn.closest('.entry');
    const entries = entry.parentElement;
    if (entries.querySelectorAll('.entry').length <= 1) {
      entry.querySelectorAll('[data-key]').forEach(el => { el.value = ''; });
      return;
    }
    entry.remove();
    renumberEntries(entries);
  }
});

function collectEntry(entry) {
  const obj = {};
  entry.querySelectorAll('[data-key]').forEach(el => {
    const key = el.dataset.key;
    const raw = (el.tagName === 'SELECT' ? el.value : el.value || '').trim();
    if (!raw) return;
    if (key === 'bullets') {
      obj.bullets = raw.split('\\n').map(s => s.trim()).filter(Boolean);
    } else {
      obj[key] = raw;
    }
  });
  return obj;
}

function collectListEntries(wrap) {
  const type = wrap.dataset.listType;
  return Array.from(wrap.querySelectorAll('.entry'))
    .map(collectEntry)
    .filter(obj => {
      if (type === 'education_list') return obj.degree && obj.institution;
      if (type === 'experience_list') return obj.title && obj.company;
      if (type === 'reference_list') return obj.name;
      if (type === 'language_list') return obj.language && obj.level;
      return Object.keys(obj).length > 0;
    });
}

function collectData() {
  const sec = schema.sections.find(s => s.id === current);
  const form = document.getElementById('wizardForm');
  const fd = new FormData(form);
  const data = {};
  for (const f of sec.fields) {
    if (f.type === 'education_list' || f.type === 'experience_list' || f.type === 'reference_list' || f.type === 'language_list') {
      const wrap = form.querySelector(`[data-field="${f.name}"]`);
      data[f.name] = wrap ? collectListEntries(wrap) : [];
    } else if (f.type === 'string_list') {
      const raw = fd.get(f.name) || '';
      data[f.name] = String(raw).split('\\n').map(s => s.trim()).filter(Boolean);
    } else {
      data[f.name] = fd.get(f.name);
    }
  }
  return data;
}

async function parseResponse(r) {
  const text = await r.text();
  try { return { ok: r.ok, data: JSON.parse(text) }; }
  catch { return { ok: false, data: { error: text || r.statusText, status: r.status } }; }
}

document.getElementById('saveBtn').onclick = async () => {
  const r = await fetch('/api/setup/wizard/section', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ section: current, data: collectData() })
  });
  const { ok, data } = await parseResponse(r);
  log(ok ? data : { error: data.detail || data.error || data, status: r.status });
  if (ok) await loadSchema();
};

document.getElementById('finalizeBtn').onclick = async () => {
  const saveR = await fetch('/api/setup/wizard/section', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ section: current, data: collectData() })
  });
  const saveParsed = await parseResponse(saveR);
  if (!saveParsed.ok) {
    log({ error: saveParsed.data.detail || saveParsed.data.error || 'Nie udało się zapisać sekcji', status: saveR.status });
    return;
  }
  const r = await fetch('/api/setup/finalize', { method: 'POST' });
  const text = await r.text();
  let j;
  try { j = JSON.parse(text); }
  catch { log({ error: text || r.statusText, status: r.status }); return; }
  if (r.ok) {
    j = { ...j, note: `Zapisano sekcję ${current} i wygenerowano pliki (w tym search-queries.md).` };
  }
  log(r.ok ? j : { error: j.detail || j, status: r.status });
  if (r.ok) await loadSchema();
};

function showCvImportResult(data) {
  const banner = document.getElementById('cvImportBanner');
  if (!data || !data.summary) {
    banner.classList.add('hidden');
    return;
  }
  const gaps = data.gaps || [];
  const gapHtml = gaps.length
    ? '<ul style="margin:8px 0 0;padding-left:1.2rem">' +
      gaps.map(g => `<li>${esc(g)}</li>`).join('') + '</ul>'
    : '<p style="margin:8px 0 0;color:#198754">Wszystkie wymagane sekcje uzupełnione. Możesz finalizować profil.</p>';
  banner.className = gaps.length ? 'o_banner' : 'o_section_box';
  banner.innerHTML = `<strong>${esc(data.summary)}</strong>${gapHtml}`;
  banner.classList.remove('hidden');
}

document.getElementById('cvImportBtn').onclick = async () => {
  const cv_text = document.getElementById('cvText').value.trim();
  if (!cv_text) { log('Wklej treść CV.'); return; }
  const btn = document.getElementById('cvImportBtn');
  btn.disabled = true;
  btn.textContent = 'Importuję…';
  try {
    const r = await fetch('/api/setup/cv', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ cv_text })
    });
    const { ok, data } = await parseResponse(r);
    if (ok) {
      showCvImportResult(data);
      log(data.summary);
      await loadSchema();
    } else {
      log({ error: data.detail || data.error || data, status: r.status });
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Importuj CV';
  }
};

loadSchema().catch(e => log(String(e)));

})();
