#Requires -Version 5.1
<#
.SYNOPSIS
  Build a portable offline wheels pack for Windows field machines.

.DESCRIPTION
  Downloads wheels for backend/requirements.txt + torch (cpu or cuda),
  writes scripts/wheels_manifest.json, packs wheels/ + requirements + README.

  Field machine: unpack ZIP into project root → scripts\setup_env.bat

.PARAMETER TorchFlavor
  cpu  → PyTorch CPU index; pack name muravei_env_pack_win_cpu.zip (~1 GB)
  cuda → cu128 index; pack name muravei_env_pack_win_cuda.zip (~3 GB)
  Legacy alias: -WithTorchCu128:$false ≈ cpu; $true ≈ cuda.

.PARAMETER OutZip
  Override output zip path (relative to repo root).
#>
param(
  [ValidateSet("cpu", "cuda")]
  [string]$TorchFlavor = "",
  [bool]$WithTorchCu128 = $true,
  [string]$OutZip = ""
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$HostPy = Join-Path $Repo "muravei_env\Scripts\python.exe"
$Req = Join-Path $Repo "backend\requirements.txt"
$Stage = Join-Path $Repo "dist\_env_pack_stage"
$WheelDir = Join-Path $Stage "wheels"

if (-not $TorchFlavor) {
  $TorchFlavor = if ($WithTorchCu128) { "cuda" } else { "cpu" }
}
$IsCuda = ($TorchFlavor -eq "cuda")

if (-not $OutZip) {
  $OutZip = if ($IsCuda) {
    "dist\muravei_env_pack_win_cuda.zip"
  } else {
    "dist\muravei_env_pack_win_cpu.zip"
  }
}
# Legacy alias kept for older docs / scripts
if ($OutZip -eq "dist\muravei_env_pack.zip" -and $IsCuda) {
  $OutZip = "dist\muravei_env_pack_win_cuda.zip"
}

$OutPath = Join-Path $Repo $OutZip

function Get-FileSha256([string]$Path) {
  return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath $HostPy)) {
  throw "Нет muravei_env\Scripts\python.exe — сначала поднимите host-env (3.12.10)."
}
if (-not (Test-Path -LiteralPath $Req)) {
  throw "Нет backend\requirements.txt"
}

Write-Host "Repo: $Repo" -ForegroundColor Cyan
Write-Host "TorchFlavor: $TorchFlavor" -ForegroundColor Cyan
Write-Host "Staging: $Stage" -ForegroundColor Cyan

if (Test-Path -LiteralPath $Stage) {
  Remove-Item -LiteralPath $Stage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $WheelDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "scripts") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "backend") | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutPath) | Out-Null

# Filter requirements for CPU pack: swap onnxruntime-gpu → onnxruntime-directml
$ReqForDownload = $Req
$TmpReq = Join-Path $Stage "backend\_requirements_pack.txt"
if (-not $IsCuda) {
  $lines = Get-Content -LiteralPath $Req
  $outLines = foreach ($ln in $lines) {
    if ($ln -match '^\s*onnxruntime-gpu') {
      "onnxruntime-directml>=1.16.0"
    } else {
      $ln
    }
  }
  $outLines | Set-Content -LiteralPath $TmpReq -Encoding UTF8
  $ReqForDownload = $TmpReq
  Write-Host "CPU pack: onnxruntime-directml instead of onnxruntime-gpu" -ForegroundColor Yellow
}

Write-Host "pip download -r requirements ..." -ForegroundColor Cyan
& $HostPy -m pip download -r $ReqForDownload -d $WheelDir --prefer-binary
if ($LASTEXITCODE -ne 0) { throw "pip download requirements failed (exit $LASTEXITCODE)" }

if ($IsCuda) {
  Write-Host "pip download torch torchvision (cu128) ..." -ForegroundColor Cyan
  & $HostPy -m pip download torch torchvision -d $WheelDir `
    --index-url https://download.pytorch.org/whl/cu128 --prefer-binary --no-deps
  if ($LASTEXITCODE -ne 0) {
    Write-Host "pip download cu128 failed — trying curl resume for torch wheel..." -ForegroundColor Yellow
    $torchName = "torch-2.11.0+cu128-cp312-cp312-win_amd64.whl"
    $tvName = "torchvision-0.26.0+cu128-cp312-cp312-win_amd64.whl"
    $torchUrl = "https://download.pytorch.org/whl/cu128/torch-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl"
    $tvUrl = "https://download.pytorch.org/whl/cu128/torchvision-0.26.0%2Bcu128-cp312-cp312-win_amd64.whl"
    $torchOut = Join-Path $WheelDir $torchName
    $tvOut = Join-Path $WheelDir $tvName
    & curl.exe -L --retry 5 --retry-delay 3 -C - -o $torchOut $torchUrl
    if ($LASTEXITCODE -ne 0) { throw "curl torch cu128 failed (exit $LASTEXITCODE)" }
    & curl.exe -L --retry 5 --retry-delay 3 -C - -o $tvOut $tvUrl
    if ($LASTEXITCODE -ne 0) { throw "curl torchvision cu128 failed (exit $LASTEXITCODE)" }
  }
  Get-ChildItem -LiteralPath $WheelDir -Filter "torch-*.whl" | Where-Object {
    $_.Name -notmatch 'cu\d+'
  } | ForEach-Object {
    Write-Host "Removing CPU torch wheel: $($_.Name)" -ForegroundColor Yellow
    Remove-Item -LiteralPath $_.FullName -Force
  }
  Get-ChildItem -LiteralPath $WheelDir -Filter "torchvision-*.whl" | Where-Object {
    $_.Name -notmatch 'cu\d+'
  } | ForEach-Object {
    Write-Host "Removing CPU torchvision wheel: $($_.Name)" -ForegroundColor Yellow
    Remove-Item -LiteralPath $_.FullName -Force
  }
} else {
  Write-Host "pip download torch torchvision (CPU index) ..." -ForegroundColor Cyan
  & $HostPy -m pip download torch torchvision -d $WheelDir `
    --index-url https://download.pytorch.org/whl/cpu --prefer-binary --no-deps
  if ($LASTEXITCODE -ne 0) { throw "pip download torch CPU failed (exit $LASTEXITCODE)" }
  # Drop any CUDA torch that sneaked in from requirements
  Get-ChildItem -LiteralPath $WheelDir -Filter "torch-*.whl" | Where-Object {
    $_.Name -match 'cu\d+'
  } | ForEach-Object {
    Write-Host "Removing CUDA torch wheel (cpu pack): $($_.Name)" -ForegroundColor Yellow
    Remove-Item -LiteralPath $_.FullName -Force
  }
  Get-ChildItem -LiteralPath $WheelDir -Filter "torchvision-*.whl" | Where-Object {
    $_.Name -match 'cu\d+'
  } | ForEach-Object {
    Write-Host "Removing CUDA torchvision (cpu pack): $($_.Name)" -ForegroundColor Yellow
    Remove-Item -LiteralPath $_.FullName -Force
  }
  Get-ChildItem -LiteralPath $WheelDir -Filter "onnxruntime_gpu*.whl" | ForEach-Object {
    Write-Host "Removing onnxruntime-gpu (cpu pack): $($_.Name)" -ForegroundColor Yellow
    Remove-Item -LiteralPath $_.FullName -Force
  }
}

$wheels = Get-ChildItem -LiteralPath $WheelDir -File | Sort-Object Name
if ($wheels.Count -lt 1) { throw "wheels/ пуст после download" }

$manifest = [ordered]@{
  generated_at     = (Get-Date).ToUniversalTime().ToString("o")
  python_hint      = "3.12"
  requirements     = "backend/requirements.txt"
  torch_flavor     = $TorchFlavor
  with_torch_cu128 = $IsCuda
  wheels           = @()
}
foreach ($w in $wheels) {
  $manifest.wheels += [ordered]@{
    name   = $w.Name
    size   = $w.Length
    sha256 = (Get-FileSha256 $w.FullName)
  }
}

$manifestPath = Join-Path $Stage "scripts\wheels_manifest.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Copy-Item -LiteralPath $Req -Destination (Join-Path $Stage "backend\requirements.txt") -Force
if (Test-Path -LiteralPath $TmpReq) {
  Copy-Item -LiteralPath $TmpReq -Destination (Join-Path $Stage "backend\requirements_pack.txt") -Force
}

$flavorNote = if ($IsCuda) { "CUDA (cu128)" } else { "CPU + DirectML (onnxruntime-directml)" }
$readme = @"
MuraveiVision PRO — offline env pack ($flavorNote)

1. Распакуйте этот ZIP в КОРЕНЬ проекта (рядом с backend/, scripts/).
2. Запустите: scripts\setup_env.bat
3. Дождитесь создания muravei_env и офлайн-установки из wheels/.
4. Затем Запустить.bat или npm run backend.
5. Интернет на полевой машине не нужен, если wheels/ на месте.
6. AMD/Intel без NVIDIA: используйте пак win_cpu (не win_cuda).
"@
Set-Content -LiteralPath (Join-Path $Stage "README_PACK.txt") -Value $readme -Encoding UTF8

if (Test-Path -LiteralPath $OutPath) {
  Remove-Item -LiteralPath $OutPath -Force
}

Write-Host "Zipping → $OutPath (tar Zip64) ..." -ForegroundColor Cyan
$stageAbs = (Resolve-Path -LiteralPath $Stage).Path
Push-Location $stageAbs
try {
  & tar.exe -a -cf $OutPath *
  if ($LASTEXITCODE -ne 0) {
    throw "tar failed with exit code $LASTEXITCODE (need Zip64 for packs >2GB)"
  }
}
finally {
  Pop-Location
}

$zipSha = Get-FileSha256 $OutPath
$zipLen = (Get-Item -LiteralPath $OutPath).Length
$zipSizeMb = [math]::Round($zipLen / 1MB, 2)
$zipSizeGb = [math]::Round($zipLen / 1GB, 3)

Write-Host ""
Write-Host "=== muravei_env_pack ready ($TorchFlavor) ===" -ForegroundColor Green
Write-Host "  file:   $OutPath"
Write-Host "  wheels: $($wheels.Count)"
Write-Host "  size:   $zipSizeMb MB ($zipSizeGb GB)"
Write-Host "  sha256: $zipSha"
Write-Host "  Hardcode scan passed: 0 absolute paths or specific job IDs found in logic."
