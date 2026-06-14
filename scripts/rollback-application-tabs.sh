#!/usr/bin/env bash
# Przywraca pliki UI zakładek aplikacji sprzed refaktoru application-tabs.
# Kopie: .rollback/application-tabs/*.bak
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP="$ROOT/.rollback/application-tabs"

if [[ ! -d "$BACKUP" ]]; then
  echo "Brak katalogu kopii: $BACKUP" >&2
  exit 1
fi

restore() {
  local src="$1" dest="$2"
  if [[ ! -f "$src" ]]; then
    echo "Pominięto (brak kopii): $src" >&2
    return 0
  fi
  cp "$src" "$dest"
  echo "Przywrócono: $dest"
}

restore "$BACKUP/application.js.bak"           "$ROOT/app/static/js/application.js"
restore "$BACKUP/views.css.bak"                "$ROOT/app/static/css/views.css"
restore "$BACKUP/application_service.py.bak"   "$ROOT/app/services/application_service.py"
restore "$BACKUP/applications.py.bak"          "$ROOT/app/models/applications.py"
restore "$BACKUP/pl.py.bak"                    "$ROOT/app/ui/i18n/pl.py"

echo "Rollback zakończony. Odśwież stronę aplikacji w przeglądarce."
