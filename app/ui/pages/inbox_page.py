from app.ui.components.control_panel import render_control_panel
from app.ui.layout import page

INBOX_BODY = """
<div id="triageBanner" class="o_banner hidden">
  Brak wyników triażu. Kliknij <strong>Uruchom triaż</strong>, aby posortować oferty według profilu.
</div>
<div id="staleTriageBanner" class="o_banner hidden">
  <span id="staleTriageText"></span>
  Kliknij <strong>Uruchom triaż</strong> lub przejdź do zakładki <strong>Do przeglądu</strong>.
</div>
""" + render_control_panel(
    tabs_html="""
    <div class="o_tabs" id="tierTabs">
      <button type="button" class="o_tab active" data-tier="priority">Priorytet</button>
      <button type="button" class="o_tab" data-tier="review">Do przeglądu</button>
      <button type="button" class="o_tab" data-tier="evaluate">Kolejka oceny</button>
      <button type="button" class="o_tab" data-tier="skip">Pominięte</button>
    </div>""",
    view_toggle_html="""
    <div class="o_tabs" id="viewTabs">
      <button type="button" class="o_tab active" data-view="cards">Karty</button>
      <button type="button" class="o_tab" data-view="table">Tabela</button>
    </div>""",
    filters_html="""
    <label>Status
      <select id="fStatus">
        <option value="">wszystkie</option>
        <option value="new" selected>nowe</option>
        <option value="evaluated">ocenione</option>
        <option value="skipped">pominięte</option>
      </select>
    </label>
    <label>Dopasowanie
      <select id="fFit">
        <option value="">wszystkie</option>
        <option value="high">wysokie</option>
        <option value="medium">średnie</option>
        <option value="low">niskie</option>
      </select>
    </label>
    <label>Tier
      <select id="fTier">
        <option value="">wszystkie</option>
        <option value="priority">priorytet</option>
        <option value="review">do przeglądu</option>
        <option value="skip">pomiń</option>
      </select>
    </label>
    <label>Szukaj <input type="search" id="fSearch" placeholder="tytuł, firma…" /></label>
    <button type="button" class="btn btn-secondary btn-sm" id="reload">Odśwież</button>""",
    actions_html="""
    <a href="/apply?intent=add" class="btn btn-secondary btn-sm">Dodaj ofertę</a>""",
) + """
<p class="o_summary" id="summary"></p>
<p class="o_keyboard_hint">Skróty: j/k nawigacja · a aplikuj · s pomiń · <strong>Oceń</strong> → ocena dopasowania, potem na stronie aplikacji kliknij „Generuj CV i list”</p>
<div class="o_list_view" id="jobList"></div>
<div class="o_table_wrap hidden" id="jobTableWrap"></div>

<dialog id="skipReasonDialog" class="o_modal_dialog" aria-labelledby="skipDialogTitle">
  <form id="skipReasonForm" method="dialog" class="o_modal">
    <header class="o_modal_header">
      <h2 id="skipDialogTitle">Powód pominięcia</h2>
      <p id="skipDialogJobTitle" class="o_modal_subtitle"></p>
    </header>
    <div class="o_modal_body">
      <fieldset class="o_radio_group">
        <legend class="o_form_label">Wybierz powód (możesz zaznaczyć kilka)</legend>
        <label class="o_radio_row">
          <input type="checkbox" name="skipCategory" value="wrong_scoring" />
          Błędny scoring
        </label>
        <div id="skipFieldsWrongScoring" class="o_skip_fields hidden">
          <label>Poprawny fit
            <select id="skipCorrectFit">
              <option value="">— wybierz —</option>
              <option value="high">Wysoki</option>
              <option value="medium">Średni</option>
              <option value="low">Niski</option>
            </select>
          </label>
          <label>Poprawny wynik triażu (opcjonalnie)
            <input type="number" id="skipCorrectScore" placeholder="np. 40" />
          </label>
        </div>
        <label class="o_radio_row">
          <input type="checkbox" name="skipCategory" value="english_level" />
          Niewystarczający poziom języka angielskiego
        </label>
        <label class="o_radio_row">
          <input type="checkbox" name="skipCategory" value="missing_skill" />
          Brak umiejętności lub certyfikatu
        </label>
        <div id="skipFieldsMissingSkill" class="o_skip_fields hidden">
          <label>Jaka umiejętność / certyfikat?
            <input type="text" id="skipMissingItem" placeholder="np. AWS Solutions Architect" />
          </label>
        </div>
        <label class="o_radio_row">
          <input type="checkbox" name="skipCategory" value="domain_knowledge" />
          Brak wiedzy domenowej
        </label>
        <div id="skipFieldsDomainKnowledge" class="o_skip_fields hidden">
          <label>Jakiej wiedzy domenowej brakuje?
            <input type="text" id="skipDomainNote" placeholder="np. ubezpieczenia, farmacja, MES" />
          </label>
        </div>
        <label class="o_radio_row">
          <input type="checkbox" name="skipCategory" value="salary_low" />
          Zbyt niskie widełki płacowe
        </label>
        <div id="skipFieldsSalary" class="o_skip_fields hidden">
          <label>Jakie są widełki / oczekiwania?
            <input type="text" id="skipSalaryNote" placeholder="np. 12 000 PLN B2B" />
          </label>
        </div>
        <label class="o_radio_row">
          <input type="checkbox" name="skipCategory" value="other" />
          Inne
        </label>
        <div id="skipFieldsOther" class="o_skip_fields hidden">
          <label>Komentarz
            <textarea id="skipComment" rows="3" placeholder="Opisz powód…"></textarea>
          </label>
        </div>
      </fieldset>
      <p id="skipFormError" class="o_form_error hidden" role="alert"></p>
    </div>
    <footer class="o_modal_footer">
      <button type="button" class="btn btn-secondary" id="skipDialogCancel">Anuluj</button>
      <button type="submit" class="btn btn-primary" id="skipDialogConfirm">Pomiń ofertę</button>
    </footer>
  </form>
</dialog>
"""


def inbox_page_html() -> str:
    top_actions = """
<button type="button" class="btn btn-secondary" id="runTriage">Uruchom triaż</button>
<a href="/scrape" class="btn btn-primary">Nowy scrape</a>
"""
    return page(
        "Inbox",
        "inbox",
        INBOX_BODY,
        breadcrumbs=[("Inbox", None)],
        top_actions=top_actions,
        page_scripts=["/static/js/inbox.js"],
    )
