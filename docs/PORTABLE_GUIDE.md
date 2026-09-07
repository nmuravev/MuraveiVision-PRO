# Portable bootstrap guide (Windows + Linux/WSL2)

Platforms: **Windows native** and **Linux/WSL2** only. **macOS is unsupported** (branch `feature/macos-mps` removed).

## Goal

Unpack ZIP → `Запустить.bat` → first-run **self-bootstrap** (venv audit + offline-first sidecars) → UI at `http://127.0.0.1:8000`.

Scripts:

- [`scripts/bootstrap_portable.ps1`](../scripts/bootstrap_portable.ps1) (+ [`bootstrap_portable.sh`](../scripts/bootstrap_portable.sh) for WSL)
- [`scripts/portable_manifest.json`](../scripts/portable_manifest.json) — **only** place for download URLs + sha256 (Z1)
- [`scripts/setup_env.ps1`](../scripts/setup_env.ps1) — create/rebuild `muravei_env` (`-ForceRebuild` for broken env)
- [`scripts/smoke_portable.ps1`](../scripts/smoke_portable.ps1) — Mini (CI) / Full (local-only)

## Zero-hardcode (Z1)

- Paths: repo-relative **or** env overrides (`MURAVEI_SIDECARS_DIR`, `MURAVEI_WHEELS_DIR`, `MURAVEI_FFMPEG_DIR`, `MURAVEI_PYTHON`, …).
- No machine paths / job UUIDs in logic.
- URLs + sha256: **only** in `scripts/portable_manifest.json`.

## Offline-first ladder (Z3)

1. Local `wheels/` + `sidecars/` next to the kit → use, **no network**.
2. Missing → RU confirm (skipped when `MURAVEI_BOOTSTRAP_YES=1`, as in `Запустить.bat`) → download + sha256 verify.
3. No local and no network → clear RU error listing what to bring (`wheels/`, COLMAP/AliceVision archives).

## Venv audit / self-heal (Z2)

Before backend start, bootstrap:

| State | Action |
|-------|--------|
| Env missing | `setup_env.ps1` create |
| Interpreter dead / bad `pyvenv.cfg` | treat as **absent** → `-ForceRebuild` (never skip because folder exists) |
| Alive but packages missing vs `backend/requirements.txt` | `pip` install offline-first, then network |
| Full + CUDA HW + torch CPU | try CUDA torch from `wheels/` or manifest index |
| Mini + CUDA HW | keep CPU torch + info line |

Fingerprint in `config/local/bootstrap_complete.json` includes `hash(requirements.txt)` + torch variant + `gpu_present` + build profile. Any change → re-bootstrap.

## Hardware tiers (Z5)

Thresholds: [`config/hardware_tiers.json`](../config/hardware_tiers.json). Override: `MURAVEI_FORCE_TIER=0|1|2`.

| Tier | Class (RU) | Rule |
|------|------------|------|
| 2 | полевая станция | CUDA + RAM≥16 + cores≥8 |
| 1 | рабочая станция | no CUDA + (RAM≥16 or cores≥8) |
| 0 | офис | else |

### Which build to pick

| ZIP | Profile | Best for | Honest perf |
|-----|---------|----------|-------------|
| `MuraveiVision_PRO_Mini.zip` | mini | Tier 0–1, AMD/WSL/office | YOLO nano/small budgets; Dense/Mesh **off**; torch CPU |
| `MuraveiVision_PRO_FullKit.zip` | full | Tier 2 field CUDA | Dense/Mesh + AV; torch CUDA; heavier disk (~17–20 GB) |

**Mismatch = inform, never block:** Mini on tier 2 → info «Full разблокирует splat/dense»; Full on tier 0 → warning + CPU caps. Both always start.

Applied defaults: gitignored `config/local/hardware_profile.json` (operator-overridable). UI badge: «Сборка: Mini · класс: офис (tier 0)».

## Field checklist

1. Unpack Mini/Full ZIP to a **clean** folder (not inside another git clone).
2. Optional air-gap: copy `wheels/` and `sidecars/` next to the kit.
3. Run `Запустить.bat`.
4. Self-heal check: `muravei_env\Scripts\pip.exe uninstall -y psutil` → re-run → bootstrap must reinstall, not silently skip.

## Smoke split (Z4)

```powershell
# Mini — required (CI / local)
powershell -ExecutionPolicy Bypass -File scripts\smoke_portable.ps1

# Full — local only (large ZIP)
powershell -ExecutionPolicy Bypass -File scripts\smoke_portable.ps1 -Full
```

Report: `CI: Mini OK / Local: Full OK|skipped`. CI must **not** fail when Full is skipped.

## Related

- [PORTABLE.md](PORTABLE.md) — build matrix / bake details
- [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md) — env pack
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) — macOS unsupported; first-run network if no wheels
