# CI/CD — WorkSphere

Repozytorium: [github.com/Pawwo/WorkSphere](https://github.com/Pawwo/WorkSphere)

Produkcja: **RPi4** `admin@192.168.0.194`, ścieżka `/home/admin/worksphere`, uruchomienie przez **systemd** `worksphere.service` (FastAPI + venv + Bun). **Bez Dockera** dla aplikacji.

## Architektura

```
Lokalnie:  ./release.sh  →  pytest  →  commit  →  tag vX.Y.Z  →  push main + tag
           ./deploy/rpi4/deploy-ssh.sh  →  SSH  →  remote-deploy.sh  →  restart

GitHub:    push main  →  workflow deploy.yml
           job test (pytest -m "not integration", WORKSPHERE_CI=1)
           job deploy (opcjonalny, gdy vars.SSH_DEPLOY=true + Secrets)
```

**Wersjonowanie:** plik [`VERSION`](../VERSION) (SemVer) + tag Git `vX.Y.Z` + pole `version` w [`app/main.py`](../app/main.py).

## Pliki

| Plik | Rola |
|------|------|
| [`release.sh`](../release.sh) | Testy → bump wersji → commit → tag → push |
| [`rollback.sh`](../rollback.sh) | SSH rollback do tagu na Pi |
| [`scripts/bump_version.sh`](../scripts/bump_version.sh) | patch / minor / major |
| [`deploy/rpi4/deploy-ssh.sh`](../deploy/rpi4/deploy-ssh.sh) | Deploy z maszyny w LAN (rekomendowane) |
| [`deploy/rpi4/remote-deploy.sh`](../deploy/rpi4/remote-deploy.sh) | `git pull` + `install.sh` + restart (na Pi) |
| [`deploy/rpi4/remote-rollback.sh`](../deploy/rpi4/remote-rollback.sh) | Checkout tagu na Pi |
| [`deploy/rpi4/bootstrap-server.sh`](../deploy/rpi4/bootstrap-server.sh) | Jednorazowa migracja rsync → git clone |
| [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) | CI test + opcjonalny deploy SSH |

## Pierwsze uruchomienie

### 1. Lokalnie — kod już w GitHub

```bash
cd /home/pawel/Pulpit/projekty/WorkSphere
git init
git branch -M main
git remote add origin https://github.com/Pawwo/WorkSphere.git
git fetch origin
# jeśli na GitHub jest tylko LICENSE:
git merge origin/main --allow-unrelated-histories -m "merge: LICENSE from GitHub"
git add -A
git commit -m "chore: add WorkSphere application and CI/CD"
git push -u origin main
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

### 2. RPi4 — deploy key (read-only)

Na Pi (`admin@192.168.0.194`):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/worksphere_deploy -N ""
cat ~/.ssh/worksphere_deploy.pub
```

Dodaj klucz publiczny w GitHub → repo **WorkSphere** → Settings → Deploy keys (read-only).

### 3. Bootstrap serwera (jednorazowo)

Z maszyny deweloperskiej (w LAN):

```bash
./deploy/rpi4/bootstrap-server.sh
```

Zachowuje istniejące `~/worksphere/.env` i `~/worksphere/data/`.

### 4. GitHub Actions — testy

Każdy `push` na `main` uruchamia job **test** (pytest offline).

### 5. GitHub Secrets (opcjonalny deploy z GHA)

Settings → Secrets and variables → Actions:

| Secret | Przykład |
|--------|----------|
| `HOST` | `192.168.0.194` |
| `SSH_USER` | `admin` |
| `SSH_PRIVATE_KEY` | klucz prywatny (deploy) |
| `PORT` | `22` |

**Uwaga:** GitHub-hosted runners **nie widzą** prywatnego LAN `192.168.0.x`. Domyślnie deploy z GHA jest **wyłączony**.

Aby włączyć (np. z self-hosted runnerem lub Tailscale): Settings → Variables → `SSH_DEPLOY` = `true`.

Do codziennego deployu używaj lokalnego:

```bash
./deploy/rpi4/deploy-ssh.sh
```

## Codzienny workflow

```bash
# po zmianach w kodzie:
./release.sh          # patch: 1.0.0 → 1.0.1
./release.sh minor    # 1.0.1 → 1.1.0

# deploy na Pi (z LAN):
./deploy/rpi4/deploy-ssh.sh
```

`release.sh` uruchamia **pełny** `pytest` (w tym testy `integration` z LAN do BC-250). GitHub Actions uruchamia `pytest -m "not integration"`.

## Rollback

```bash
./rollback.sh v1.0.0
```

Na Pi: checkout tagu → `install.sh` → `systemctl restart worksphere` → smoke `/health`.

Plik `.deployed-version` na serwerze zapisuje aktualny tag/revizję.

## Odzyskiwanie po awarii

1. Sprawdź logi: `ssh admin@192.168.0.194 'journalctl -u worksphere -n 100'`
2. Rollback: `./rollback.sh v<poprzedni-tag>`
3. Jeśli uszkodzone dane: przywróć backup z `~/worksphere-backup-*` (tworzony przez `bootstrap-server.sh`)
4. Ręczny restart: `sudo systemctl restart worksphere`

## Co nie trafia do Git

- `.env`, `data/` (operacyjne), `.venv/`, `node_modules/`
- `seen_jobs.json`, `app.db`, artefakty apply — patrz [`.gitignore`](../.gitignore)

## Różnice vs generyczna instrukcja CI/CD

| Instrukcja | WorkSphere |
|------------|------------|
| `/opt/app` | `/home/admin/worksphere` |
| `docker compose` | `systemd` + `deploy/rpi4/install.sh` |
| Deploy z GHA zawsze | Testy w GHA; deploy SSH opcjonalny (`SSH_DEPLOY`) lub lokalny `deploy-ssh.sh` |
