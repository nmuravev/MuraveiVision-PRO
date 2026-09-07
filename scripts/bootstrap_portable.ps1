#Requires -Version 5.1
<#
.SYNOPSIS
  Portable first-run bootstrap: detect → venv audit/self-heal → offline-first sidecars → stamp.

.DESCRIPTION
  Z1: paths repo-relative or MURAVEI_* overrides; URLs/sha256 only in scripts/portable_manifest.json
  Z2: broken env → full rebuild (not skip); incomplete → pip heal; torch reconcile
  Z3: wheels/sidecars local first → RU confirm → network + sha256 → clear RU if neither
  Z5: apply mini/full profile to config/local/hardware_profile.json

  Env:
    MURAVEI_BOOTSTRAP_YES=1     skip RU confirm
    MURAVEI_BUILD_PROFILE=mini|full
    MURAVEI_BOOTSTRAP_ONLINE=0  forbid network
    MURAVEI_WHEELS_DIR, MURAVEI_SIDECARS_DIR, MURAVEI_FORCE_TIER, …
#>
param(
  [ValidateSet("mini", "full", "")]
  [string]$Profile = "",
  [switch]$Yes
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Repo

function Write-RuError([string]$Msg) {
  Write-Host "[ОШИБКА] $Msg" -ForegroundColor Red
}
function Write-RuInfo([string]$Msg) {
  Write-Host "[INFO] $Msg" -ForegroundColor Cyan
}
function Write-RuWarn([string]$Msg) {
  Write-Host "[ПРЕДУПРЕЖДЕНИЕ] $Msg" -ForegroundColor Yellow
}

function Confirm-Network([string]$What) {
  if ($Yes -or $env:MURAVEI_BOOTSTRAP_YES -eq "1") { return $true }
  Write-Host ""
  Write-Host "Нужна загрузка: $What" -ForegroundColor Yellow
  Write-Host "Разрешить сеть? (Y/N)" -NoNewline
  $a = Read-Host
  return ($a -match '^[YyДд]')
}

$ManifestPath = Join-Path $Repo "scripts\portable_manifest.json"
if (-not (Test-Path -LiteralPath $ManifestPath)) {
  Write-RuError "Нет scripts\portable_manifest.json"
  exit 1
}
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

if ($Profile) {
  $env:MURAVEI_BUILD_PROFILE = $Profile
} elseif (-not $env:MURAVEI_BUILD_PROFILE) {
  $env:MURAVEI_BUILD_PROFILE = [string]$Manifest.default_profile
  if (-not $env:MURAVEI_BUILD_PROFILE) { $env:MURAVEI_BUILD_PROFILE = "mini" }
}
$BuildProfile = $env:MURAVEI_BUILD_PROFILE.ToLowerInvariant()
Write-RuInfo "Профиль сборки: $BuildProfile"

# Prefer host muravei_env for audit helpers; fall back to any python 3.12
$HostPy = Join-Path $Repo "muravei_env\Scripts\python.exe"
$AuditPy = $null
if (Test-Path -LiteralPath $HostPy) { $AuditPy = $HostPy }
if (-not $AuditPy) {
  $pyCmd = Get-Command py -ErrorAction SilentlyContinue
  if ($pyCmd) {
    try {
      $cand = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
      if ($LASTEXITCODE -eq 0 -and $cand) { $AuditPy = ($cand | Out-String).Trim() }
    } catch { }
  }
}

$env:PYTHONPATH = Join-Path $Repo "backend"
$StampPath = Join-Path $Repo "config\local\bootstrap_complete.json"

function Invoke-PortableModule([string]$Code) {
  if (-not $AuditPy) { throw "Нет Python 3.12 для audit (нужен muravei_env или py -3.12)" }
  $prev = $env:PYTHONPATH
  $env:PYTHONPATH = Join-Path $Repo "backend"
  try {
    $out = & $AuditPy -c $Code 2>&1
    $code = $LASTEXITCODE
    return @{ ExitCode = $code; Output = ($out | Out-String) }
  } finally {
    $env:PYTHONPATH = $prev
  }
}

# Fast path: stamp OK
if ((Test-Path -LiteralPath $StampPath) -and $AuditPy) {
  $chk = Invoke-PortableModule "from services.portable_bootstrap import stamp_matches; import sys; sys.exit(0 if stamp_matches() else 1)"
  if ($chk.ExitCode -eq 0) {
    Write-RuInfo "bootstrap_complete.json актуален — пропуск."
    exit 0
  }
  Write-RuInfo "Stamp устарел — повторный bootstrap."
}

# --- Z2 env audit ---
$SetupEnv = Join-Path $Repo "scripts\setup_env.ps1"
$envStatus = "absent"
$auditJson = $null
if ($AuditPy) {
  $ar = Invoke-PortableModule "from services.portable_bootstrap import audit_env, resolve_build_profile; import json; print(json.dumps(audit_env(resolve_build_profile()), ensure_ascii=False))"
  if ($ar.ExitCode -eq 0 -and $ar.Output) {
    try {
      $auditJson = $ar.Output.Trim() | ConvertFrom-Json
      $envStatus = [string]$auditJson.env_status
    } catch {
      $envStatus = "absent"
    }
  }
}

Write-RuInfo "Env status: $envStatus"

if ($envStatus -eq "broken") {
  Write-RuWarn "Битый muravei_env — удаляю и пересобираю (self-heal, не skip)."
  $envDir = Join-Path $Repo "muravei_env"
  if (Test-Path -LiteralPath $envDir) {
    Remove-Item -LiteralPath $envDir -Recurse -Force -ErrorAction SilentlyContinue
  }
  $envStatus = "absent"
}

if ($envStatus -eq "absent") {
  if (-not (Test-Path -LiteralPath $SetupEnv)) {
    Write-RuError "Нет scripts\setup_env.ps1 — не могу создать muravei_env."
    exit 1
  }
  Write-RuInfo "Создаю muravei_env через setup_env.ps1 ..."
  & powershell -NoProfile -ExecutionPolicy Bypass -File $SetupEnv -ForceRebuild
  if ($LASTEXITCODE -ne 0) {
    Write-RuError "setup_env.ps1 не удался."
    Write-Host "Привезите: wheels/ или dist\muravei_env_pack.zip → распаковать в корень, затем снова Запустить.bat"
    exit 1
  }
  $HostPy = Join-Path $Repo "muravei_env\Scripts\python.exe"
  if (Test-Path -LiteralPath $HostPy) { $AuditPy = $HostPy }
}

# Heal incomplete packages / torch
if ($AuditPy) {
  $hr = Invoke-PortableModule "from services.portable_bootstrap import heal_env; import json; print(json.dumps(heal_env(), ensure_ascii=False))"
  if ($hr.ExitCode -ne 0) {
    Write-RuError "heal_env завершился с ошибкой."
    Write-Host $hr.Output
    exit 1
  }
  try {
    $heal = $hr.Output.Trim() | ConvertFrom-Json
    if (-not $heal.ok) {
      Write-RuError ([string]($heal.error_ru))
      exit 1
    }
    foreach ($m in @($heal.messages)) {
      if ($m) { Write-RuInfo $m }
    }
  } catch {
    Write-RuWarn "Не разобрал ответ heal_env — продолжаю."
  }
}

# --- Detect + tier + profile ---
$tierJson = $null
if ($AuditPy) {
  $tr = Invoke-PortableModule @"
from services.hardware_detect import detect_all, classify_tier, _badge_ru
from services.portable_bootstrap import apply_hardware_profile, resolve_build_profile
import json
snap = detect_all()
tier = snap.get('tier') or classify_tier()
bp = resolve_build_profile()
apply_hardware_profile(bp, tier)
badge = _badge_ru(bp, tier)
mm = None
from services.hardware_detect import _mismatch_message
mm = _mismatch_message(bp, int(tier.get('tier') or 0))
print(json.dumps({'tier': tier, 'badge': badge, 'mismatch': mm, 'build_profile': bp}, ensure_ascii=False))
"@
  if ($tr.ExitCode -eq 0) {
    try { $tierJson = $tr.Output.Trim() | ConvertFrom-Json } catch { }
    if ($tierJson) {
      Write-RuInfo ([string]$tierJson.badge)
      if ($tierJson.mismatch) {
        $lvl = [string]$tierJson.mismatch.level
        $msg = [string]$tierJson.mismatch.message_ru
        if ($lvl -eq "warning") { Write-RuWarn $msg } else { Write-RuInfo $msg }
      }
    }
  }
}

# --- Sidecars offline-first (Z3) ---
function Test-Sha256Hex([string]$s) {
  return ($s -match '^[a-fA-F0-9]{64}$')
}

function Get-FileSha256([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Ensure-Component([string]$Key, [bool]$Required) {
  $comp = $Manifest.components.$Key
  if (-not $comp) { return $true }
  $profiles = @($comp.profiles)
  if ($profiles.Count -gt 0 -and ($profiles -notcontains $BuildProfile)) {
    return $true
  }

  $destRel = [string]$comp.dest_relative
  $dest = Join-Path $Repo ($destRel -replace '/', '\')

  # Presence probes
  $present = $false
  if ($Key -like "colmap*") {
    $present = (Test-Path (Join-Path $dest "COLMAP.bat")) -or (Test-Path (Join-Path $dest "colmap.exe"))
  } elseif ($Key -like "alicevision*") {
    $present = Test-Path (Join-Path $dest "bin\aliceVision_featureExtraction.exe")
  } else {
    $present = Test-Path -LiteralPath $dest
  }
  if ($present) {
    Write-RuInfo "${Key}: уже есть ($destRel)"
    return $true
  }

  $archRel = [string]$comp.archive_relative
  $arch = Join-Path $Repo ($archRel -replace '/', '\')
  $url = [string]$comp.url
  $sha = ([string]$comp.sha256).ToLowerInvariant()

  # Local archive?
  if (-not (Test-Path -LiteralPath $arch)) {
    # also check portable/cache
    $leaf = Split-Path $arch -Leaf
    $cacheAlt = Join-Path $Repo "portable\cache\$leaf"
    if (Test-Path -LiteralPath $cacheAlt) { $arch = $cacheAlt }
  }

  if (Test-Path -LiteralPath $arch) {
    if (Test-Sha256Hex $sha) {
      $got = Get-FileSha256 $arch
      if ($got -ne $sha) {
        Write-RuError "${Key}: sha256 mismatch для локального архива (ожидалось $sha, получено $got)"
        return (-not $Required)
      }
    }
    Write-RuInfo "${Key}: ставлю из локального архива (без сети)"
  } else {
    if (-not $Required) {
      Write-RuInfo "${Key}: нет локально — пропуск (не обязателен для $BuildProfile)"
      return $true
    }
    if (-not (Test-Sha256Hex $sha)) {
      Write-RuError "$Key отсутствует. Привезите sidecar ($destRel) или архив с валидным sha256 в portable_manifest.json. Сеть без pinned sha256 запрещена (Z1)."
      return $false
    }
    if ($env:MURAVEI_BOOTSTRAP_ONLINE -eq "0") {
      Write-RuError "$Key отсутствует и сеть запрещена. Привезите: $archRel или готовый $destRel"
      return $false
    }
    if (-not (Confirm-Network $url)) {
      Write-RuError "Загрузка $Key отменена. Привезите офлайн: $archRel"
      return $false
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $arch -Parent) | Out-Null
    Write-RuInfo "Скачиваю $url ..."
    try {
      Invoke-WebRequest -Uri $url -OutFile $arch -UseBasicParsing
    } catch {
      Write-RuError "Сеть недоступна / скачивание не удалось. Привезите: $archRel"
      return $false
    }
    $got = Get-FileSha256 $arch
    if ($got -ne $sha) {
      Remove-Item -LiteralPath $arch -Force -ErrorAction SilentlyContinue
      Write-RuError "${Key}: sha256 mismatch после скачивания"
      return $false
    }
  }

  # Extract / stage
  $stage = Join-Path $env:TEMP ("muravei_bootstrap_" + $Key)
  if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
  New-Item -ItemType Directory -Force -Path $stage | Out-Null
  Expand-Archive -LiteralPath $arch -DestinationPath $stage -Force

  if ($Key -like "colmap*") {
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    $exe = Get-ChildItem -Path $stage -Recurse -Filter "COLMAP.bat" | Select-Object -First 1
    if (-not $exe) { $exe = Get-ChildItem -Path $stage -Recurse -Filter "colmap.exe" | Select-Object -First 1 }
    if (-not $exe) {
      Write-RuError "В архиве COLMAP нет COLMAP.bat/colmap.exe"
      return $false
    }
    Get-ChildItem -LiteralPath $exe.Directory.FullName | ForEach-Object {
      Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
    }
  } elseif ($Key -like "alicevision*") {
    $bin = Get-ChildItem -Path $stage -Recurse -Directory -Filter "bin" |
      Where-Object { Test-Path (Join-Path $_.FullName "aliceVision_featureExtraction.exe") } |
      Select-Object -First 1
    if (-not $bin) {
      Write-RuError "В архиве AliceVision нет bin/aliceVision_*"
      return $false
    }
    $srcRoot = $bin.Parent.FullName
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($name in @("bin", "lib", "share")) {
      $s = Join-Path $srcRoot $name
      if (Test-Path $s) { Copy-Item -LiteralPath $s -Destination (Join-Path $dest $name) -Recurse -Force }
    }
  }

  Write-RuInfo "${Key}: готов → $destRel"
  return $true
}

$colmapOk = Ensure-Component "colmap_windows_cuda" ($BuildProfile -eq "full")
if (-not $colmapOk -and $BuildProfile -eq "full") {
  Write-RuWarn "COLMAP не установлен — 3D recon будет ограничен."
}

if ($BuildProfile -eq "full") {
  $avOk = Ensure-Component "alicevision_windows" $false
  if (-not $avOk) {
    Write-RuWarn "AliceVision не установлен — Dense/Mesh останутся disabled."
  }
}

# --- Write stamp ---
if (-not $AuditPy) {
  Write-RuError "Нет Python для записи stamp."
  exit 1
}
$sr = Invoke-PortableModule @"
from services.portable_bootstrap import write_stamp, resolve_build_profile
from services.hardware_detect import detect_colmap, detect_alicevision
import json
bp = resolve_build_profile()
comps = {
  'colmap': detect_colmap().get('present'),
  'alicevision': detect_alicevision().get('present'),
}
path = write_stamp(build_profile=bp, messages=['bootstrap_portable.ps1'], component_versions=comps)
print(path.as_posix())
"@
if ($sr.ExitCode -ne 0) {
  Write-RuError "Не удалось записать bootstrap_complete.json"
  Write-Host $sr.Output
  exit 1
}

Write-Host "Bootstrap OK: $($sr.Output.Trim())" -ForegroundColor Green
exit 0
