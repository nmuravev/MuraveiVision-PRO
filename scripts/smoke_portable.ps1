#Requires -Version 5.1
<#
.SYNOPSIS
  Portable smoke: Mini (CI-required) + Full (local-only, Z4).

.DESCRIPTION
  Mini: unpack ZIP to temp, bootstrap with MURAVEI_BOOTSTRAP_YES=1, hit /api/health + UI.
  Full: same when -Full or when Full ZIP present; CI must NOT fail if Full skipped.

  Report line: CI: Mini OK|FAIL / Local: Full OK|FAIL|skipped
#>
param(
  [string]$MiniZip = "",
  [string]$FullZip = "",
  [switch]$Full,
  [switch]$SkipFull,
  [int]$HealthTimeoutSec = 90
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $MiniZip) { $MiniZip = Join-Path $Repo "portable\MuraveiVision_PRO_Mini.zip" }
if (-not $FullZip) { $FullZip = Join-Path $Repo "portable\MuraveiVision_PRO_FullKit.zip" }

function Write-TableRow([string]$Name, [string]$Status, [string]$Detail) {
  Write-Host ("{0,-8} {1,-10} {2}" -f $Name, $Status, $Detail)
}

function Invoke-KitSmoke([string]$ZipPath, [string]$Label, [int]$Port) {
  if (-not (Test-Path -LiteralPath $ZipPath)) {
    return @{ ok = $false; skipped = $true; detail = "ZIP missing: $ZipPath" }
  }
  $tmp = Join-Path $env:TEMP ("muravei_smoke_" + $Label + "_" + [guid]::NewGuid().ToString("n").Substring(0, 8))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  Write-Host "Unpack $Label → $tmp"
  Expand-Archive -LiteralPath $ZipPath -DestinationPath $tmp -Force
  # find kit root (stage may nest one folder)
  $root = $tmp
  $bat = Get-ChildItem -Path $tmp -Recurse -Filter "Запустить.bat" -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $bat) {
    $bat = Get-ChildItem -Path $tmp -Recurse -Filter "Zayuskat*.bat" -ErrorAction SilentlyContinue | Select-Object -First 1
  }
  # also accept start scripts
  $launch = Get-ChildItem -Path $tmp -Recurse -Filter "*.bat" |
    Where-Object { $_.Name -match 'Запустить|Start|start_backend' } |
    Select-Object -First 1
  if ($bat) { $root = $bat.Directory.FullName; $launch = $bat }
  elseif ($launch) { $root = $launch.Directory.FullName }

  $py = Join-Path $root "muravei_env\Scripts\python.exe"
  if (-not (Test-Path $py)) { $py = Join-Path $root "muravei_env\python.exe" }
  if (-not (Test-Path $py)) {
    return @{ ok = $false; skipped = $false; detail = "python missing in kit" }
  }

  $env:MURAVEI_BOOTSTRAP_YES = "1"
  $env:MURAVEI_BUILD_PROFILE = $(if ($Label -eq "Full") { "full" } else { "mini" })
  $boot = Join-Path $root "scripts\bootstrap_portable.ps1"
  if (Test-Path $boot) {
    Push-Location $root
    try {
      & powershell -NoProfile -ExecutionPolicy Bypass -File $boot
      if ($LASTEXITCODE -ne 0) {
        return @{ ok = $false; skipped = $false; detail = "bootstrap failed" }
      }
    } finally { Pop-Location }
  }

  $job = Start-Job -ScriptBlock {
    param($Py, $Root, $Port)
    Set-Location $Root
    $env:PYTHONPATH = Join-Path $Root "backend"
    & $Py -m uvicorn main:app --app-dir (Join-Path $Root "backend") --host 127.0.0.1 --port $Port
  } -ArgumentList $py, $root, $Port

  $deadline = (Get-Date).AddSeconds($HealthTimeoutSec)
  $healthOk = $false
  $uiOk = $false
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3
      if ($r.StatusCode -eq 200) { $healthOk = $true; break }
    } catch { Start-Sleep -Seconds 2 }
  }
  if ($healthOk) {
    try {
      $u = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 5
      $uiOk = ($u.StatusCode -eq 200) -and (($u.Content -match 'html') -or ($u.Content.Length -gt 50))
    } catch { $uiOk = $false }
  }

  Stop-Job $job -ErrorAction SilentlyContinue
  Remove-Job $job -Force -ErrorAction SilentlyContinue
  # best-effort kill listeners
  try {
    Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
      ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  } catch { }

  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue

  if ($healthOk -and $uiOk) {
    return @{ ok = $true; skipped = $false; detail = "health+ui OK :$Port" }
  }
  if ($healthOk) {
    return @{ ok = $false; skipped = $false; detail = "health OK but UI failed" }
  }
  return @{ ok = $false; skipped = $false; detail = "health timeout" }
}

Write-Host "=== portable smoke ==="
Write-TableRow "Kit" "Status" "Detail"

$mini = Invoke-KitSmoke -ZipPath $MiniZip -Label "Mini" -Port 18080
Write-TableRow "Mini" $(if ($mini.ok) { "OK" } elseif ($mini.skipped) { "SKIP" } else { "FAIL" }) $mini.detail

$fullResult = @{ ok = $false; skipped = $true; detail = "skipped (local-only; use -Full)" }
$runFull = $Full -and -not $SkipFull
if ($runFull) {
  $fullResult = Invoke-KitSmoke -ZipPath $FullZip -Label "Full" -Port 18081
}
Write-TableRow "Full" $(if ($fullResult.ok) { "OK" } elseif ($fullResult.skipped) { "skipped" } else { "FAIL" }) $fullResult.detail

$miniLabel = if ($mini.ok) { "OK" } else { "FAIL" }
$fullLabel = if ($fullResult.skipped) { "skipped" } elseif ($fullResult.ok) { "OK" } else { "FAIL" }
Write-Host ""
Write-Host "CI: Mini $miniLabel / Local: Full $fullLabel"

if (-not $mini.ok) { exit 1 }
# Z4: CI must NOT fail on absent Full
exit 0
