# BC-250 LLM — baseline wydajności i energii (2026-06-12)

## Winning config (post-tuning, Vulkan 9596)

Serwer po formacie + `build-llama-vulkan.sh --coopmat2` (pin `18ef86ece`).

| Metryka | Wynik | Gate |
|---------|-------|------|
| Gate A `esc_ratio` @ 128 tok | **0.0** | PASS |
| Gate B `tg128` (24/40 CU) | **41.57** tok/s | PASS vs baseline |
| Gate C `quality_score` | **100.0** | PASS |
| `undef matmul cm2` | **0** | OK |

**Produkcja:** `llama-server-bielik.service` (Vulkan `-ngl 999`), `LLM_UNIT = llama-server-bielik`.

### Unit (`deploy/bc250/systemd/llama-server-bielik.service`)

| Parametr | Wartość |
|----------|---------|
| `-c` | 4096 |
| `--batch-size` / `--ubatch-size` | 128 / 64 |
| `--threads` | 6 |
| `--fit-target` | 512 |
| `RADV_DEBUG` | `nohiz` |
| `GGML_VK_FORCE_MAX_ALLOCATION_SIZE` | 2000000000 |
| CU profile | **24/40** (stock dispatch) |

### Eksperymenty (harness: `scripts/bc250_llm_gate.sh`)

| ID | Zmiana | Gate A | Gate B tg128 | Werdykt |
|----|--------|--------|--------------|---------|
| exp-001 | baseline po formacie | PASS | 41.42 | baseline |
| exp-010 | 40/40 CU `enable all` | **FAIL** (0.53) | — | rollback — ESC wraca przy 40 CU |
| exp-011 | governor max 2000 MHz | PASS | 41.39 | rollback — brak zysku |
| exp-012 | batch 128/64 | PASS | 41.46 | **keep** |
| exp-014 | ctx 4096 | PASS | 41.56 | **keep** |
| exp-016 | fit-target 512 | PASS | 41.57 | **keep** |
| exp-013,015,017,018 | threads/RADV/flash/vk alloc | PASS | ≤41.55 | rollback |

**Uwaga:** Cel docs ~55–60 tok/s wymaga **40 CU**, ale na tym boardzie po formacie `enable all` psuje Gate A (degeneracja ESC). Pozostajemy na **24/40 CU** — jakość > prędkość.

## Harness (repo)

```bash
./scripts/bc250_exp_snapshot.sh exp-NNN
# … jedna zmiana na serwerze …
./scripts/bc250_llm_gate.sh exp-NNN AB
# FAIL → BC250_ROLLBACK_TO=exp-NNN ./scripts/bc250_exp_rollback.sh exp-NNN
```

Logi: `data/llm_benchmark/gates.jsonl`

Gate A: `scripts/debug_llm_degradation.py` / `bc250_llm_gate.py` — prompt `{"overall_fit":`, PASS gdy `esc_ratio < 0.01`.

Gate B: `llama-bench -ngl 99 -p 128 -n 128 -r 3` na serwerze — PASS gdy `tg128 >= baseline`.

Gate C: `python scripts/benchmark_llm_models.py --model minitron-q4 --no-restore` — PASS gdy `quality_score >= 90`.

## CU vs jakość (2026-06-12, świeży serwer)

| Profil CU | esc_ratio @ 128 | tg128 |
|-----------|-----------------|-------|
| 24/40 (stock) | **0.0** | ~41 |
| 40/40 (`enable all`) | **0.53** | nie mierzono (rollback) |

Po formacie ESC na Vulkan **naprawione** przy 24 CU; 40 CU na tym egzemplarzu **nie** jest bezpieczne.

## Instalacja binariów (build 9596+)

`llama-server` wymaga bibliotek impl z jednego buildu:

```bash
bash deploy/bc250/build-llama-vulkan.sh --coopmat2
```

Weryfikacja: `nm -D libggml-vulkan.so | grep -c ' U matmul.*cm2'` → **0**.

## Checklist BC-250

| Krok | Status |
|------|--------|
| Fedora 43, kernel 7.0.12 | OK |
| Mesa 25.3.6+, glslc, spirv-tools | OK |
| `cyan-skillfish-governor-smu` | OK |
| `bc250-cu-live-manager` + stock 24 CU table | `/usr/local/bin/bc250-cu-live-manager` |
| Vulkan env + drirc + TTM | `deploy/bc250/setup-checklist.sh` |
| CPU unit (awaryjny) | `llama-server-bielik-cpu.service` disabled |

## Komendy

```bash
# Gates z dev
python scripts/bc250_llm_gate.py --exp exp-XXX --gate AB --baseline-tg 41.42

# Benchmark aplikacji
python scripts/benchmark_llm_models.py --model minitron-q4 --no-restore

# Wake / sleep
curl -X POST http://192.168.0.112:8099/wake
curl http://192.168.0.112:8099/status
```

**Zakaz:** `git pull` w `/workspace/llama.cpp` bez Gate A+B+C.
