# TODO — приоритизированный план

Оба мастерплана (`masterplan_field_readiness` A–I, `mosaic_yolo_davinci` Фазы 0–10), **Response Validator** и **Masterplan v3 Фаза 1+2** завершены и подтверждены тестами. Ниже — оставшаяся работа по приоритетам. Ограничения без плана — в [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

> Примечание: предыдущий `REMAINING_WORK.md` ошибочно отмечал Response Validator как нереализованный — **исправлено**: валидатор реализован, протестирован (15 unit-тестов), задокументирован в [API.md](API.md).

## Критические баги

На данный момент открытых критических багов нет.

## Важный функционал (1–2 недели)

Фаза 1 и Фаза 2 мастерплана v3.0 **выполнены** (см. «Закрыто»). Оставшийся важный функционал — Фаза 3 (сеть и продукт):

| # | Задача | Критерий готовности | Проверка |
|---|--------|--------------------|----------|
| 8 | Реальная сетевая репликация целей между базами | цель с Базы-1 появляется на Базе-2 <5с | network E2E |
| 9 | Пресет 4×Live + Event Timeline | 4 live-потока + лента событий | Playwright |

## Улучшения / оптимизация (потом)

| # | Задача | Критерий |
|---|--------|---------|
| 4 | Code-split frontend chunk >500 kB | `vite build` без warning; lazy-импорт тяжёлых панелей |
| 5 | Консолидация `ARCHITECTECTURE.md` и `ARCHITECTURE_FOR_AI.md` | один источник архитектуры + AI-инварианты отдельно |
| 12 | TTL кэша валидатора (поверх автообновления из 1.3) | кэш обновляется автоматически по TTL |

## Фичи будущего (когда остальное готово)

- Полный пор OpenReel WebGPU/effects.
- Native multi-monitor windows.
- OCR-only телеметрия (расширение geo-scope).
- Cloud/SaaS-режим (если потребуется).
- Фаза 4: seg-маски укреплений, change detection двух пролётов, USB offline model manager.

## Закрыто (контекст)

- Мастерпланы A–I, mosaic Фазы 0–10 — DONE.
- SAHI — DONE (`test_sahi_inference.py` PASS). **Баг SAHI исправлен** (`slice_image` kwargs для 0.12.6) — `test_sahi_field.py` PASS на сыром кадре из дрон-видео.
- Response Validator — DONE (15 unit-тестов PASS, интеграция в `_finalize_sync`).
- **Masterplan v3 Фаза 1** — DONE:
  - 1.1 Полевой тест SAHI на сыром 4K-кадре БПЛА — `backend/scripts/test_sahi_field.py`, `logs/sahi_field_test.json`.
  - 1.2 UI-переключатели SAHI/валидатора в AdminPanel + `detect-config` API с полями валидатора — Playwright `test_ui_toggles.test.ts` PASS.
  - 1.3 Автообновление кэша валидатора после `PATCH/DELETE /api/classes/overrides/{id}` — `test_validator_catalog_refresh.py` (6 тестов) PASS.
- **Masterplan v3 Фаза 2** — DONE:
  - 2.1 Единый оркестратор тестов — `scripts/test_orchestrator.py` + `npm run test:all` → `reports/test_report.html`, exit 0.
  - 2.2 Pre-commit hook — `.git/hooks/pre-commit` + `scripts/install-hooks.sh` (unit + compileall гейт).
  - 2.3 Тесты фич Фазы 1 — `tests/test_ui_toggles.test.ts` (Playwright) + `test_validator_catalog_refresh.py` (unit).
- **Masterplan v3 Stage 1 (3.4 / 4.2 / 3.3)** — DONE:
  - 3.4 Hotkeys — `src/hooks/useHotkeys.ts`, undo patch-only, Playwright `test_hotkeys.test.ts`.
  - 4.2 Audio cue — `soundType` beep/alarm/none + volume в RulesPanel.
  - 3.3 KML/GeoJSON/PDF — `backend/services/geo_export.py`, `GET /api/export/kml|geojson`, `GET /api/report/pdf`, dropdown TopBar, `test_geo_export.py`.
