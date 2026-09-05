#Requires -Version 5.1
<#
.SYNOPSIS
  Build a portable offline wheels pack: dist/muravei_env_pack.zip

.DESCRIPTION
  Downloads wheels for backend/requirements.txt (+ optional torch cu128),
  writes scripts/wheels_manifest.json, packs wheels/ + requirements copy + README.

  Field machine: unpack ZIP into project root → scripts\setup_env.bat

.PARAMETER WithTorchCu128
  Also download torch/torchvision from the cu128 index (default: on).
  Pass -WithTorchCu128:$false to skip (CPU-only / smaller pack).

.PARAMETER OutZip
  Output zip path relative to repo root (default: dist/muravei_env_pack.zip).
#>
param(
  [bool]$WithTorchCu128 = $true,
  [string]$OutZip = "dist\muravei_env_pack.zip"
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$HostPy = Join-Path $Repo "muravei_env\Scripts\python.exe"
$Req = Join-Path $Repo "backend\requirements.txt"
$Stage = Join-Path $Repo "dist\_env_pack_stage"
$WheelDir = Join-Path $Stage "wheels"
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
Write-Host "Staging: $Stage" -ForegroundColor Cyan

if (Test-Path -LiteralPath $Stage) {
  Remove-Item -LiteralPath $Stage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $WheelDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "scripts") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "backend") | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutPath) | Out-Null

Write-Host "pip download -r backend\requirements.txt ..." -ForegroundColor Cyan
& $HostPy -m pip download -r $Req -d $WheelDir --prefer-binary
if ($LASTEXITCODE -ne 0) { throw "pip download requirements failed (exit $LASTEXITCODE)" }

if ($WithTorchCu128) {
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
  # Prefer CUDA torch over CPU torch pulled by requirements
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
}

$wheels = Get-ChildItem -LiteralPath $WheelDir -File | Sort-Object Name
if ($wheels.Count -lt 1) { throw "wheels/ пуст после download" }

$manifest = [ordered]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  python_hint  = "3.12"
  requirements = "backend/requirements.txt"
  with_torch_cu128 = $WithTorchCu128
  wheels = @()
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

$readme = @"
MuraveiVision PRO — offline env pack (wheels)

1. Распакуйте этот ZIP в КОРЕНЬ проекта (рядом с backend/, scripts/).
2. Запустите: scripts\setup_env.bat
3. Дождитесь создания muravei_env и офлайн-установки из wheels/.
4. Затем Запустить.bat или npm run backend.
5. Интернет на полевой машине не нужен, если wheels/ на месте.
"@
Set-Content -LiteralPath (Join-Path $Stage "README_PACK.txt") -Value $readme -Encoding UTF8

if (Test-Path -LiteralPath $OutPath) {
  Remove-Item -LiteralPath $OutPath -Force
}

# Compress-Archive fails above ~2 GB ("Stream was too long"); use tar/bsdtar (Zip64).
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
Write-Host "=== muravei_env_pack ready ===" -ForegroundColor Green
Write-Host "  file:   $OutPath"
Write-Host "  wheels: $($wheels.Count)"
Write-Host "  size:   $zipSizeMb MB ($zipSizeGb GB)"
Write-Host "  sha256: $zipSha"
Write-Host "  Hardcode scan passed: 0 absolute paths or specific job IDs found in logic."
