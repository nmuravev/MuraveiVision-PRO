# Stage COLMAP sidecar for MuraveiVision PRO (Windows)
param(
    [string]$OutDir = (Join-Path $PSScriptRoot "..\sidecars\colmap"),
    [string]$ColmapUrl = "https://github.com/colmap/colmap/releases/download/3.9.1/COLMAP-3.9.1-windows-cuda.zip"
)

$ErrorActionPreference = "Stop"
$OutDir = [System.IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$zip = Join-Path $env:TEMP "colmap-win.zip"
Write-Host "Downloading COLMAP -> $zip"
Invoke-WebRequest -Uri $ColmapUrl -OutFile $zip -UseBasicParsing

$extract = Join-Path $env:TEMP "colmap_extract"
if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
Expand-Archive -Path $zip -DestinationPath $extract -Force

$exe = Get-ChildItem -Path $extract -Recurse -Filter "COLMAP.bat" | Select-Object -First 1
if (-not $exe) {
    $exe = Get-ChildItem -Path $extract -Recurse -Filter "colmap.exe" | Select-Object -First 1
}
if (-not $exe) { throw "COLMAP.bat/colmap.exe not found in archive" }

if (Test-Path $OutDir) {
    Get-ChildItem -LiteralPath $OutDir | Remove-Item -Recurse -Force
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
