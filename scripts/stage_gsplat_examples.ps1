# BUILD MACHINE ONLY: Requires internet. Runtime sidecars are already committed to the repo.
# Stage gsplat examples (simple_trainer + datasets/utils) for MuraveiVision PRO
param(
    [string]$OutDir = (Join-Path $PSScriptRoot "..\sidecars\gsplat_examples"),
    [string]$GsplatTag = "v1.5.3"
)

$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$OutDir = [System.IO.Path]::GetFullPath($OutDir)
$Py = Join-Path $Root "muravei_env\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    throw "muravei_env python missing: $Py"
}

# Match staged examples to installed gsplat wheel when possible
$installed = & $Py -c "import gsplat; print(gsplat.__version__)" 2>$null
if ($installed) {
    $GsplatTag = "v$installed"
    Write-Host "Using gsplat tag $GsplatTag (installed wheel)"
}

$zipUrl = "https://github.com/nerfstudio-project/gsplat/archive/refs/tags/$GsplatTag.zip"
$zip = Join-Path $env:TEMP "gsplat-$GsplatTag.zip"
$extract = Join-Path $env:TEMP "gsplat_extract_$GsplatTag"

Write-Host "Downloading $zipUrl -> $zip"
Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing

if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
Expand-Archive -Path $zip -DestinationPath $extract -Force

$folderName = "gsplat-$($GsplatTag -replace '^v', '')"
$srcExamples = Join-Path (Join-Path $extract $folderName) "examples"
if (-not (Test-Path $srcExamples)) {
  # tag folder may be gsplat-1.5.3 without v
  $srcExamples = Get-ChildItem -Path $extract -Directory | ForEach-Object {
    Join-Path $_.FullName "examples"
  } | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $srcExamples -or -not (Test-Path (Join-Path $srcExamples "simple_trainer.py"))) {
    throw "simple_trainer.py not found under extracted gsplat examples"
}

if (Test-Path $OutDir) {
    Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Copy-Item -Path (Join-Path $srcExamples "*") -Destination $OutDir -Recurse -Force

$trainer = Join-Path $OutDir "simple_trainer.py"
if (-not (Test-Path $trainer)) {
    throw "Staging failed: $trainer missing"
}

@"
MuraveiVision PRO — gsplat examples sidecar
Source: gsplat $GsplatTag examples/
Trainer: sidecars/gsplat_examples/simple_trainer.py
Also install example deps once on build machine:
  .\muravei_env\Scripts\pip.exe install fused-ssim torchmetrics[image] viser pyyaml pycolmap splines
"@ | Set-Content -Path (Join-Path $OutDir "README.txt") -Encoding UTF8

Write-Host "OK gsplat examples staged at $OutDir"
Write-Host "Trainer: $trainer"
