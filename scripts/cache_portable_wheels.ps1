#Requires -Version 5.1
<#
.SYNOPSIS
  Download wheels once into portable/cache/wheels for offline portable builds.

.DESCRIPTION
  Uses host muravei_env (3.12.10) only. Run on the build machine with network,
  then npm run portable:mini / portable:full can install with --no-index.

  Always caches torch/torchvision CPU wheels (required for Mini/Lite).
  Optional -WithTorchCu128 ALSO caches CUDA cu128 wheels (required for FullKit).
  Both variants may coexist in the same folder; build_portable selects by kit profile.
#>
param(
  [switch]$WithTorchCu128
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$HostPy = Join-Path $Repo "muravei_env\Scripts\python.exe"
$WheelDir = Join-Path $Repo "portable\cache\wheels"
$Req = Join-Path $Repo "backend\requirements.txt"

if (-not (Test-Path -LiteralPath $HostPy)) {
  throw "Missing host muravei_env: $HostPy"
}
if (-not (Test-Path -LiteralPath $Req)) {
  throw "Missing: $Req"
}

New-Item -ItemType Directory -Force -Path $WheelDir | Out-Null
Write-Host "Downloading wheels → $WheelDir" -ForegroundColor Cyan
& $HostPy -m pip download -r $Req -d $WheelDir --prefer-binary
if ($LASTEXITCODE -ne 0) { throw "pip download requirements failed" }

Write-Host "Downloading torch+torchvision CPU wheels (Mini/Lite)..." -ForegroundColor Cyan
& $HostPy -m pip download torch torchvision -d $WheelDir --index-url https://download.pytorch.org/whl/cpu --prefer-binary
if ($LASTEXITCODE -ne 0) { throw "pip download torch CPU failed" }

Write-Host "Downloading onnxruntime-directml (Mini/Lite; replaces onnxruntime-gpu)..." -ForegroundColor Cyan
& $HostPy -m pip download "onnxruntime-directml>=1.16.0" -d $WheelDir --prefer-binary
if ($LASTEXITCODE -ne 0) {
  Write-Host "WARNING: onnxruntime-directml download failed — Mini build may fetch online" -ForegroundColor Yellow
}

if ($WithTorchCu128) {
  Write-Host "Downloading torch+torchvision cu128 wheels (FullKit) — keeping CPU wheels too..." -ForegroundColor Cyan
  & $HostPy -m pip download torch torchvision -d $WheelDir --index-url https://download.pytorch.org/whl/cu128 --prefer-binary
  if ($LASTEXITCODE -ne 0) { throw "pip download torch cu128 failed" }
}

$count = (Get-ChildItem -LiteralPath $WheelDir -File).Count
$torchNames = @(Get-ChildItem -LiteralPath $WheelDir -File -Filter "torch*.whl" | ForEach-Object { $_.Name })
Write-Host "OK: $count files in portable/cache/wheels" -ForegroundColor Green
Write-Host ("Torch family wheels: {0}" -f ($(if ($torchNames.Count) { $torchNames -join ', ' } else { '(none)' })))
