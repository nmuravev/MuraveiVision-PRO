# Известные ограничения и проблемы

Актуальный список. Запланированные работы — [TODO.md](TODO.md).

## Flaky / окружение

- **`ECONNRESET` на `POST /api/active-learning/collect`** при конкурентных воркерах Playwright. Mitigation: `workers: 1` в [playwright.config.ts](../playwright.config.ts) (уже выставлено). При ручном запуске нескольких тест-наборов против одного backend — возможен reset; перезапустите backend.
- **SAHI `pip check` warning**: `sahi 0.12.6` декларирует `opencv-python>=4.12.0.88` (имя non-headless пакета), но установлен `opencv-python-headless`. `cv2` предоставляется headless-сборкой, runtime работает. Benign — можно игнорировать.

## Не поддерживается (осознанно)

- **Intel Arc/XPU** — не тестируется, провайдеры ORT могут отсутствовать. Только CUDA и CPU.
- **Native multi-monitor windows** — только in-app floating panels; нативных окон на отдельные мониторы нет.
- **Полный пор OpenReel WebGPU/effects** — не переносился; MVP использует `<video>` + frame grab + canvas overlay.
- **OCR-only телеметрия** — вне первоначального geo-scope (SRT/CSV только).
- **Cloud/SaaS/full NLE** — вне скоупа; система локальная, air-gap.
- **Кастомное layout-дерево вместо mosaic** — mosaic остаётся ядром; кастом только chrome/float поверх.

## Производительность

- **SAHI** добавляет N инференсов на кадр (по слайсам). По умолчанию выключен; включать только для тяжёлых 4K-кадров БПЛА.

## Совместимость

- **Python**: только 3.12.10 (`muravei_env`). Системный 3.14 несовместим — см. [.cursor/rules/muravei-python-env.mdc](../.cursor/rules/muravei-python-env.mdc).
- **numpy**: pinned `<2` (ultralytics/совместимость). SAHI ставится с `--no-deps`, чтобы не тащить numpy 2.x.

## Сеть / репликация

- **Один инстанс / одна `muravei.db` не проверяет репликацию.** Два `uvicorn` в одном дереве смотрят в один SQLite и имитируют «синк». Нужны две копии проекта (отдельные БД) на разных портах — процедура в [ENGINEER_GUIDE.md](ENGINEER_GUIDE.md#сеть-баз).
- **Кроп цели** (`crop_path`) — строка пути, JPEG по LAN не копируется; на другой базе превью может быть 404. Это v1, не баг репликации id/GPS/`source_video`.
- **TLS** в приложении нет: JWT по HTTP в LAN. HTTPS — только reverse-proxy, если понадобится.

## Документация

- Устаревшие манифесты в `.backup/MuraveiVision/*.md` — **не использовать** (другой каркас).
- [`ARCHITECTURE_FOR_AI.md`](ARCHITECTURE_FOR_AI.md) — stub; читать [ARCHITECTURE.md](ARCHITECTURE.md).
