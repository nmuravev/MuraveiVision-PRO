# Stage COLMAP sidecar for MuraveiVision PRO (Windows)
# URL defaults from scripts/portable_manifest.json (Z1).
param(
    [string]$OutDir = (Join-Path $PSScriptRoot "..\sidecars\colmap"),
    [string]$ColmapUrl = "",
    [string]$ExpectedSha256 = ""
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ManifestPath = Join-Path $Repo "scripts\portable_manifest.json"
if (Test-Path -LiteralPath $ManifestPath) {
  $man = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $comp = $man.components.colmap_windows_cuda
  if (-not $ColmapUrl -and $comp -and $comp.url) { $ColmapUrl = [string]$comp.url }
  if (-not $ExpectedSha256 -and $comp -and $comp.sha256) { $ExpectedSha256 = [string]$comp.sha256 }
}
if (-not $ColmapUrl) {
  throw "COLMAP URL missing — set scripts/portable_manifest.json components.colmap_windows_cuda.url"
}
$OutDir = [System.IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$dlDir = Join-Path $Repo "sidecars\colmap\downloads"
New-Item -ItemType Directory -Force -Path $dlDir | Out-Null
$zip = Join-Path $dlDir (Split-Path $ColmapUrl -Leaf)
if (-not (Test-Path -LiteralPath $zip)) {
  Write-Host "Downloading COLMAP -> $zip"
  Invoke-WebRequest -Uri $ColmapUrl -OutFile $zip -UseBasicParsing
}
if ($ExpectedSha256 -match '^[a-fA-F0-9]{64}$') {
  $got = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
  if ($got -ne $ExpectedSha256.ToLowerInvariant()) {
    throw "COLMAP sha256 mismatch: got $got expected $ExpectedSha256"
  }
  Write-Host "SHA256 OK: $got"
} else {
  Write-Host "WARNING: sha256 not pinned in portable_manifest — skip verify" -ForegroundColor Yellow
}

$extract = Join-Path $env:TEMP "colmap_extract"
if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
Expand-Archive -Path $zip -DestinationPath $extract -Force

$exe = Get-ChildItem -Path $extract -Recurse -Filter "COLMAP.bat" | Select-Object -First 1
if (-not $exe) {
    $exe = Get-ChildItem -Path $extract -Recurse -Filter "colmap.exe" | Select-Object -First 1
}
if (-not $exe) { throw "COLMAP.bat/colmap.exe not found in archive" }

if (Test-Path $OutDir) {
    Get-ChildItem -LiteralPath $OutDir | Where-Object { $_.Name -ne "downloads" } | Remove-Item -Recurse -Force
}

$srcDir = $exe.Directory.FullName
Get-ChildItem -LiteralPath $srcDir | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $OutDir -Recurse -Force
}

$found = @('colmap.exe', 'COLMAP.bat') | ForEach-Object {
    Join-Path $OutDir $_
} | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $found) {
    throw "Staging incomplete: colmap.exe/COLMAP.bat not in $OutDir"
}
Write-Host "Verified: $found"

@"
MuraveiVision PRO - COLMAP sidecar
Set: COLMAP_ROOT=$OutDir
"@ | Set-Content -Path (Join-Path $OutDir "README.txt") -Encoding ASCII

Write-Host "OK COLMAP staged at $OutDir"
Write-Host "Set env: `$env:COLMAP_ROOT = `"$OutDir`""
