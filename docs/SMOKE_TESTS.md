# Smoke-скрипты

Скрипты в [backend/scripts/](../backend/scripts/). Запуск:
```powershell
.\muravei_env\Scripts\python.exe backend\scripts\<имя>.py
```
Каждый пишет JSON-отчёт в `logs/` и возвращает exit-код (`0` = успех). Базовый URL можно переопределить через `MURAVEI_SMOKE_BASE`.

## Инвентарь

| Скрипт | Назначение | Ожидаемый результат |
|--------|-----------|--------------------|
| `smoke_lbs_ft.py` | Force-load finetuned весов, инференс на LBS-ролике по таймстампам | `DONE`, hits_frames>0, пишет `logs/smoke_lbs_ft.json` |
| `smoke_video_s3.py` | Сэмплирование кадров ролика, стандартный YOLO | детекции, `logs/smoke_video_s3.json` |
| `smoke_video_s3_deep.py | Сравнение raw vs filtered детекций по всему клипу | счётчики raw/filtered, `logs/smoke_video_s3_deep.json` |
| `smoke_batch_scan.py` | Короткий batch-scan, проверка persisted детекций (`origin=batch_scan`) | `DONE`, записи в БД |
| `smoke_rec_60s.py` | Запись >60с, проверка что процесс жив и пишет данные | файл >порога, exit 0 |
| `smoke_phase3.py` | Широкий API-приём: health, auth, Phase 3 сервисы | все проверки `ok` |
| `smoke_phase4.py` | Engineer auth, hardware, self-test, failure simulation, Phase 4 API | все проверки `ok` |
| `smoke_geo_telemetry.py` | SRT/CSV парсинг, flight-track, GPS-enrichment, report-карта | трек в БД, GPS заполнены |
| `smoke_flight3d.py` | Загрузка/интерполяция телеметрии, Flight3D API | точки трека, путь API |
| `smoke_recon_layout.py` | Проверка структуры каталогов реконструкции (без GPU/COLMAP) | layout корректен |
| `smoke_fullkit_layout.py` | Python 3.12, Ollama retry, portable stage layout | версия 3.12, layout OK |
| `test_sahi_inference.py` | Сравнение `infer()` vs `infer_sahi()`, проверка SAHI-пути | `PASS` (`sahi=true`) |
| `test_sahi_field.py` | Полевой тест SAHI на сыром кадре из дрон-видео (`archive/video_2026-08-25_09-17-15.mp4`): fast vs SAHI 512×512/0.2 vs 640×640/0.2, per-class counts | `PASS`, пишет `logs/sahi_field_test.json` + `logs/sahi_field_frame.jpg`, печатает вердикт (`SAHI GAIN` / `NO GAIN / NEUTRAL` / `SAHI LOSS`). Observational — не ассертит прирост |

## Категории

- **YOLO/инференс:** `smoke_lbs_ft`, `smoke_video_s3`, `smoke_video_s3_deep`, `test_sahi_inference`, `test_sahi_field`.
- **API/приём:** `smoke_phase3`, `smoke_phase4`, `smoke_batch_scan`.
- **Запись/Live:** `smoke_rec_60s`.
- **Гео/3D:** `smoke_geo_telemetry`, `smoke_flight3d`, `smoke_recon_layout`.
- **Сборка/Portable:** `smoke_fullkit_layout`.

## Запуск всех backend unit + smoke

```powershell
cd backend
..\muravei_env\Scripts\python.exe -m unittest discover -s tests
.\muravei_env\Scripts\python.exe -m compileall . -q
```
Smoke — по необходимости (часть требует роликов в `archive/` или GPU).
