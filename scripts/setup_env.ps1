#Requires -Version 5.1
<#
.SYNOPSIS
  Create muravei_env from system Python 3.12 and install deps (offline wheels preferred).

.DESCRIPTION
  Idempotent: if muravei_env\Scripts\python.exe exists → exit 0.
  Prefer wheels/ at repo root (from muravei_env_pack.zip). Else PyPI if online.
#>
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Repo

$VenvPy = Join-Path $Repo "muravei_env\Scripts\python.exe"
$Req = Join-Path $Repo "backend\requirements.txt"
$WheelDir = Join-Path $Repo "wheels"

function Write-RuError([string]$Msg) {
  Write-Host "[ОШИБКА] $Msg" -ForegroundColor Red
}

function Find-Python312 {
  # Prefer py launcher for 3.12
  $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    try {
      $ver = & py -3.12 -c "import sys; print('%d.%d'%sys.version_info[:2])" 2>$null
      if ($LASTEXITCODE -eq 0 -and (($ver | Out-String).Trim() -match '^3\.12')) {
        return ((& py -3.12 -c "import sys; print(sys.executable)" | Out-String).Trim())
      }
    } catch { }
  }

  $candidates = @()
  foreach ($cmd in @("python3", "python")) {
    $exe = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($exe) { $candidates += $exe.Source }
  }
  foreach ($root in @(${env:LOCALAPPDATA}, ${env:ProgramFiles}, ${env:ProgramFiles(x86)})) {
    if (-not $root) { continue }
    $p = Join-Path $root "Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $p) { $candidates += $p }
    $p2 = Join-Path $root "Python312\python.exe"
    if (Test-Path -LiteralPath $p2) { $candidates += $p2 }
  }

  foreach ($py in ($candidates | Select-Object -Unique)) {
    try {
      $ver = & $py -c "import sys; print('%d.%d'%sys.version_info[:2])" 2>$null
      if ($LASTEXITCODE -ne 0) { continue }
      if ((($ver | Out-String).Trim()) -match '^3\.12') { return $py }
    } catch { continue }
  }
  return $null
}

if (Test-Path -LiteralPath $VenvPy) {
  Write-Host "muravei_env уже есть — пропуск установки." -ForegroundColor Green
  exit 0
}

if (-not (Test-Path -LiteralPath $Req)) {
  Write-RuError "Нет backend\requirements.txt в корне проекта."
  exit 1
}

$BasePy = Find-Python312
if (-not $BasePy) {
  Write-RuError "Не найден Python 3.12. Установите Python 3.12.x (рекомендуется 3.12.10), затем снова scripts\setup_env.bat."
  Write-Host "Python 3.14 / системный «python» без 3.12 не подходят для MuraveiVision PRO." -ForegroundColor Yellow
  exit 1
}

Write-Host "Базовый Python: $BasePy" -ForegroundColor Cyan
& $BasePy -c "import sys; print(sys.version)"
if ($LASTEXITCODE -ne 0) {
  Write-RuError "Не удалось запустить базовый Python."
  exit 1
}

Write-Host "Создаю muravei_env ..." -ForegroundColor Cyan
& $BasePy -m venv (Join-Path $Repo "muravei_env")
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPy)) {
  Write-RuError "Не удалось создать muravei_env (venv)."
  exit 1
}

$Pip = Join-Path $Repo "muravei_env\Scripts\pip.exe"
& $VenvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
  Write-RuError "Не удалось обновить pip в muravei_env."
  exit 1
}

$hasWheels = (Test-Path -LiteralPath $WheelDir) -and
  (@(Get-ChildItem -LiteralPath $WheelDir -File -ErrorAction SilentlyContinue).Count -gt 0)

if ($hasWheels) {
  Write-Host "Офлайн-установка из wheels/ ..." -ForegroundColor Cyan
  & $VenvPy -m pip install --no-index --find-links=$WheelDir -r $Req
  if ($LASTEXITCODE -ne 0) {
    Write-RuError "Офлайн pip install из wheels/ не удался. Проверьте, что пак распакован в корень и wheels/ полный."
    exit 1
  }
  # Torch may be in wheels (cu128) but not listed in requirements — try optional install
  $torchWhl = Get-ChildItem -LiteralPath $WheelDir -Filter "torch-*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($torchWhl) {
    Write-Host "Ставлю torch/torchvision из wheels/ (если есть) ..." -ForegroundColor Cyan
    & $VenvPy -m pip install --no-index --find-links=$WheelDir torch torchvision
    if ($LASTEXITCODE -ne 0) {
      Write-Host "[ПРЕДУПРЕЖДЕНИЕ] torch из wheels не установился — YOLO/CUDA могут быть недоступны." -ForegroundColor Yellow
    }
  }
} else {
  # Probe internet
  $online = $false
  try {
    $r = Invoke-WebRequest -Uri "https://pypi.org/simple/pip/" -UseBasicParsing -TimeoutSec 8
    if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { $online = $true }
  } catch { $online = $false }

  if (-not $online) {
    Write-RuError "нет wheels/ и нет интернета — распакуйте muravei_env_pack.zip в корень проекта."
    exit 1
  }

  Write-Host "wheels/ нет — установка из PyPI (нужен интернет) ..." -ForegroundColor Yellow
  & $VenvPy -m pip install --no-cache-dir -r $Req
  if ($LASTEXITCODE -ne 0) {
    Write-RuError "pip install из PyPI не удался."
    exit 1
  }
}

Write-Host "Проверка импортов ..." -ForegroundColor Cyan
& $VenvPy -c "import torch, fastapi, ultralytics; print('ok', torch.__version__, fastapi.__version__)"
if ($LASTEXITCODE -ne 0) {
  Write-RuError "Проверка import torch, fastapi, ultralytics не прошла."
  exit 1
}

# Soft checks
try {
  & $VenvPy -c "import torch; print('cuda', torch.cuda.is_available())"
} catch {
  Write-Host "[ПРЕДУПРЕЖДЕНИЕ] проверка CUDA не удалась (не блокирует)." -ForegroundColor Yellow
}
try {
  & $VenvPy -c "import gsplat" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[ПРЕДУПРЕЖДЕНИЕ] gsplat не установлен — Splat 3D недоступен (не блокирует)." -ForegroundColor Yellow
  }
} catch {
  Write-Host "[ПРЕДУПРЕЖДЕНИЕ] gsplat не установлен — Splat 3D недоступен (не блокирует)." -ForegroundColor Yellow
}

Write-Host "Готово: muravei_env установлен." -ForegroundColor Green
exit 0
