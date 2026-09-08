# Portable ZIP

## Цель

Полевой комплект Windows: распаковал → `Запустить.bat` → UI на `http://127.0.0.1:8000` **без** установки Node/Python на целевой машине.

Скрипт: [`scripts/build_portable.ps1`](../scripts/build_portable.ps1).

**Python:** только embeddable / `muravei_env` **3.12.10**. Host `C:\Python314` и bare `python` запрещены.

## Hardening (v3.1)

- **Unique staging:** каждый запуск пишет в `portable/stage_<Kit>_<yyyyMMdd_HHmmss>/`; в начале чистятся старые `stage_*`, `*.locked_*` и legacy fixed-name dirs. ZIP-имена стабильны (`MuraveiVision_PRO_Mini.zip` и т.д.).
- **Host-pip bake:** зависимости ставятся через host `muravei_env\Scripts\python.exe -m pip --python <staged_python>` — **не** через staged `python -m pip` (ломается AV / пропадает `cacert.pem`).
- **Offline wheels:** предпочтительно `portable/cache/wheels` (`--no-index --find-links`). Один раз на машине сборки:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\cache_portable_wheels.ps1
  # FullKit + cu128 torch (CPU wheels also kept — do not delete either):
  powershell -ExecutionPolicy Bypass -File scripts\cache_portable_wheels.ps1 -WithTorchCu128
  ```
- **Torch by kit profile** ([`scripts/portable_torch_policy.py`](../scripts/portable_torch_policy.py)): **Mini/Lite → CPU only** (require explicit `+cpu` wheel tag; unmarked PyPI torch is rejected); **FullKit → CUDA cu128** (or `-TorchFlavor cpu`). Cache may hold both `+cpu` and `+cu*` wheels — build filters find-links by profile (never «first found»). Post-stage assert: Mini `torch.version.cuda is None`; FullKit CUDA `is not None`. Mini ZIP band **~3.5–4.5 GB** (warn &gt;4.5, reject &gt;5) with SAM3; FullKit **~7.5–9 GB** (warn &gt;9.5, reject &gt;10). Mini/Lite swap `onnxruntime-gpu` → **`onnxruntime-directml`** (`--no-deps` + re-pin `numpy&lt;2`).
- **Embed python path:** portable kits must use `muravei_env\python.exe` (with `python*._pth`). Do **not** copy `python.exe` into `Scripts\` — without `._pth` it resolves to host/system `sys.prefix`. `Запустить.bat` prefers embed root.
- **CA bundle:** стабильный `portable/cache/cacert.pem` (вне stage site-packages); env `SSL_CERT_FILE` / `PIP_CERT` / …
- **Robocopy fallback:** только если host-pip bake упал, или `MURAVEI_PORTABLE_MIRROR=1`. **Never** set `MURAVEI_PORTABLE_MIRROR=1` for Mini (mirrors host CUDA).
- **Перед сборкой:** остановите host `uvicorn` / portable stage (DLL locks). Если AV держит файлы — перезагрузка ПК, затем повтор.

Все пути в скриптах — относительно корня репо / env. Без абсолютных `D:\…` machine paths. Ollama **не** бандлится (system-optional).

## Матрица комплектов

| Режим | npm / флаг | Содержимое | ZIP |
|-------|------------|------------|-----|
| **Mini** | `npm run portable:mini` (`-Mini`) | full offline stack: tactical `yolo26*.pt` + **sam3.pt** + SAHI ON; torch **CPU** + DirectML; KIT=`mini` | `MuraveiVision_PRO_Mini.zip` (~4 GB) |
| **Full** | `npm run portable:full` (`-FullKit -IncludeAliceVision`) | Mini stack + torch **cu128** + COLMAP/gsplat/AliceVision; KIT=`full`; **без Ollama** | `MuraveiVision_PRO_FullKit.zip` (~8–8.5 GB) |
| **Lite** | `npm run portable` | legacy Portable.zip; same weight/sam3 rules as Mini | `MuraveiVision_PRO_Portable.zip` |

**Mini vs Full = 3D + CUDA + model size ONLY.** Detect weights: copy-only from `assets/models` (ladder l-ft&gt;…&gt;n); never download COCO stock.

**Не входит ни в один ZIP:** Ollama runtime/blobs, `assets/map_tiles`, host `muravei_env` с Python 3.14. Для AI-анализа поставьте Ollama отдельно.

## Сборка Mini (full offline detect + SAM3)

```powershell
npm run portable:mini
# или
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython -Mini
```

## Сборка FullKit (без Ollama)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1 -FetchEmbeddablePython -FullKit -IncludeAliceVision
```

AliceVision Dense/Mesh: `npm run portable:full` передаёт `-IncludeAliceVision`. Mini никогда не бандлит AliceVision.

Подробная таблица содержимого: [PORTABLE_GUIDE.md](PORTABLE_GUIDE.md).

## Что кладётся (оба пака)

- `backend/`, `dist/` (с CSP), embeddable `muravei_env` 3.12.10
- `assets/models/yolo26*.pt` (tactical, copy-only) + **exactly one** `sam3.pt`
- pack-root `VERSION` + `KIT` (`mini`|`full`)
- `assets/smoke_sample/` (CC0 synthetic for functional smoke)
- пустые `archive/`, `cache/`, `logs/`, `reports/`; `runs/detect` stub &lt;50 MB
- **нет** `ollama/`

FullKit additionally: torch cu128, `sidecars/colmap`, `gsplat_examples`, AliceVision when staged.

## Железо

- Windows 10/11 **amd64**
- Рекомендуется **NVIDIA** для realtime CUDA (Full)
- Mini: CPU + DirectML; без GPU «Сканировать»/«Сегментация» работают (SAM3 на CPU медленный)

## Лаунчер `Запустить.bat`

ASCII + CRLF. Banner читает корневой `VERSION`. Backend: **module mode**. Bootstrap Z2 перед стартом. `COLMAP_ROOT` / `ALICEVISION_ROOT` только если sidecar есть. Smoke/CI: `MURAVEI_NO_PAUSE=1` `MURAVEI_NO_BROWSER=1`.

## Проверка комплекта

1. Распаковать на чистую машину / другую папку.
2. `Запустить.bat`.
3. Mini/Full: «Сканировать» + «Сегментация» offline сразу; badge `Сборка: Mini|Full · …`.
4. Smoke: `powershell -File scripts\smoke_portable.ps1` (Mini CI); `-Full` локально → `CI: Mini OK / Local: Full OK|skipped`.
5. Layout Full: `.\muravei_env\Scripts\python.exe backend\scripts\smoke_fullkit_layout.py`

