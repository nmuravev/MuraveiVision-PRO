#Requires -Version 5.1
<#
.SYNOPSIS
  Download wheels once into portable/cache/wheels for offline portable builds.

.DESCRIPTION
  Uses host muravei_env (3.12.10) only. Run on the build machine with network,
  then npm run portable:mini / portable:full can install with --no-index.

  Optional -WithTorchCu128 also caches torch/torchvision from the cu128 index
  (needed for FullKit when baking via host-pip instead of robocopy mirror).
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

if ($WithTorchCu128) {
  Write-Host "Downloading torch+torchvision cu128 wheels..." -ForegroundColor Cyan
  & $HostPy -m pip download torch torchvision -d $WheelDir --index-url https://download.pytorch.org/whl/cu128 --prefer-binary
  if ($LASTEXITCODE -ne 0) { throw "pip download torch cu128 failed" }
}

$count = (Get-ChildItem -LiteralPath $WheelDir -File).Count
Write-Host "OK: $count files in portable/cache/wheels" -ForegroundColor Green
