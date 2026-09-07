# Portable bootstrap guide (Windows + Linux/WSL2)

Platforms: **Windows native** and **Linux/WSL2** only. **macOS is unsupported**.

## Distribution policy

- **GitHub releases = changelog only.** Бинарные паки на GitHub **не** публикуются.
- Паки собираются локально (`scripts/build_portable.ps1`) и раздаются **внутренним офлайн-каналом** (облачный диск оператора).
- Локально держать ровно два целых ZIP: `portable/MuraveiVision_PRO_Mini.zip` и `portable/MuraveiVision_PRO_FullKit.zip`.

## Goal

Unpack ZIP → `Запустить.bat` → first-run **self-bootstrap** → UI at `http://127.0.0.1:8000`. Логи → `logs/` (или `MURAVEI_LOG_DIR`).

Scripts: `bootstrap_portable.ps1` / `.sh`, `portable_manifest.json`, `setup_env.ps1`, `smoke_portable.ps1`.

## FullKit contents (slim)

| В комплекте | Не в комплекте |
|-------------|----------------|
| muravei_env + torch CUDA, dist, backend | Ollama VL-модель (на цели: `ollama pull qwen2.5vl:7b`) |
| ollama.exe + lib | SAM / seg веса |
| COLMAP + AliceVision (если собрано) | Дубли весов в `runs/detect` |
| YOLO detect `.pt` (nano/ft) | Медиа в `archive/` |

Ожидаемый размер FullKit после slim: **~5–10 GB**.

## Zero-hardcode (Z1)

Paths repo-relative or `MURAVEI_*`. URLs+sha256 only in `scripts/portable_manifest.json`.

## Offline-first / venv self-heal / tiers

Offline-first: local `wheels/`+`sidecars/` → confirm → network. Broken env → rebuild; incomplete → heal. Tiers 0/1/2 in `config/hardware_tiers.json`.

## Field checklist

1. Распаковать Mini/Full в чистую папку.
2. Опционально: `wheels/` + `sidecars/` рядом.
3. `Запустить.bat`.
4. Self-heal: uninstall пакета → перезапуск → bootstrap доустановит.
5. VLM: `ollama pull qwen2.5vl:7b` при необходимости.

## Smoke

`scripts/smoke_portable.ps1` (Mini); `-Full` только локально.
