# AliceVision offline fetch (Windows)
# Reads scripts/alicevision_manifest.json — does not invent URLs.
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts/fetch_alicevision.ps1
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ManifestPath = Join-Path $RepoRoot "scripts\alicevision_manifest.json"
if (-not (Test-Path $ManifestPath)) {
    throw "Missing $ManifestPath"
}

$man = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$chosen = $man.chosen
if (-not $chosen -or -not $chosen.url -or -not $chosen.sha256) {
    throw "manifest.chosen.url / sha256 required"
}

$dlDir = Join-Path $RepoRoot "sidecars\alicevision\downloads"
$outDir = Join-Path $RepoRoot "sidecars\alicevision\windows-x64"
New-Item -ItemType Directory -Force -Path $dlDir | Out-Null

$zipName = [IO.Path]::GetFileName([Uri]$chosen.url).LocalPath
if (-not $zipName) { $zipName = "AliceVision-Windows.zip" }
$zipPath = Join-Path $dlDir $zipName

if ((Test-Path $zipPath) -and -not $Force) {
    Write-Host "ZIP already present: $zipPath (use -Force to re-download)"
} else {
    Write-Host "Downloading $($chosen.url) ..."
    Invoke-WebRequest -Uri $chosen.url -OutFile $zipPath -UseBasicParsing
}

$hash = (Get-FileHash -Algorithm SHA256 -Path $zipPath).Hash.ToLowerInvariant()
$expect = ([string]$chosen.sha256).ToLowerInvariant()
if ($hash -ne $expect) {
    throw "SHA256 mismatch: got $hash expected $expect"
}
Write-Host "SHA256 OK: $hash"

if ((Test-Path $outDir) -and -not $Force) {
    $binProbe = Join-Path $outDir "bin\aliceVision_featureExtraction.exe"
    if (Test-Path $binProbe) {
        Write-Host "Already staged at $outDir — skip extract (use -Force to replace)"
        exit 0
    }
}

$stage = Join-Path $dlDir "_extract_stage"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Expand-Archive -Path $zipPath -DestinationPath $stage -Force

# Flatten aliceVision/{bin,lib,share} → windows-x64/{bin,lib,share}
$nested = Get-ChildItem $stage -Directory | Select-Object -First 1
$src = if ($nested -and (Test-Path (Join-Path $nested.FullName "bin"))) { $nested.FullName } `
    elseif (Test-Path (Join-Path $stage "bin")) { $stage } `
    elseif (Test-Path (Join-Path $stage "aliceVision\bin")) { Join-Path $stage "aliceVision" } `
    else { throw "Unexpected archive layout under $stage" }

if (Test-Path $outDir) { Remove-Item -Recurse -Force $outDir }
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
foreach ($name in @("bin", "lib", "share")) {
    $from = Join-Path $src $name
    if (Test-Path $from) {
        Copy-Item -Recurse -Force $from (Join-Path $outDir $name)
    }
}
Write-Host "Staged AliceVision $($chosen.version) → $outDir"
Write-Host "Set ALICEVISION_ROOT to that path before running CLIs."
