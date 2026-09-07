#Requires -Version 5.1
<#
.SYNOPSIS
  Portable operator-path smoke: unpack → Запустить.bat (same as field).

.DESCRIPTION
  Mini: required (CI + local). Full: local-only (-Full); CI must not fail if skipped.

  Fails on ANY of:
    - Traceback | ImportError | circular import in stderr / logs/bootstrap.log / logs/uvicorn.log
    - Banner version != VERSION file
    - /api/health != 200 within timeout
    - UI HTML missing

  Report: CI: Mini OK|FAIL / Local: Full OK|FAIL|skipped
#>
param(
  [string]$MiniZip = "",
  [string]$FullZip = "",
  [switch]$Full,
  [switch]$SkipFull,
  [int]$HealthTimeoutSec = 120
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $MiniZip) { $MiniZip = Join-Path $Repo "portable\MuraveiVision_PRO_Mini.zip" }
if (-not $FullZip) { $FullZip = Join-Path $Repo "portable\MuraveiVision_PRO_FullKit.zip" }

function Write-TableRow([string]$Name, [string]$Status, [string]$Detail) {
  Write-Host ("{0,-8} {1,-10} {2}" -f $Name, $Status, $Detail)
}

function Stop-PortListeners([int]$Port) {
  try {
    Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
      ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  } catch { }
  Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

function Test-LogPoison([string]$Root) {
  $patterns = @("Traceback", "ImportError", "circular import")
  $targets = @(
    (Join-Path $Root "logs\bootstrap.log"),
    (Join-Path $Root "logs\uvicorn.log"),
    (Join-Path $Root "logs\smoke_launcher.out")
  )
  foreach ($f in $targets) {
    if (-not (Test-Path -LiteralPath $f)) { continue }
    $text = Get-Content -LiteralPath $f -Raw -ErrorAction SilentlyContinue
    if (-not $text) { continue }
    foreach ($p in $patterns) {
      if ($text -match [regex]::Escape($p)) {
        return "poison '$p' in $(Split-Path $f -Leaf)"
      }
    }
  }
  return $null
}

function Invoke-KitSmoke([string]$ZipPath, [string]$Label, [int]$Port) {
  if (-not (Test-Path -LiteralPath $ZipPath)) {
    return @{ ok = $false; skipped = $true; detail = "ZIP missing: $ZipPath"; banner = "" }
  }
  $tmp = Join-Path $env:TEMP ("muravei_smoke_" + $Label + "_" + [guid]::NewGuid().ToString("n").Substring(0, 8))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  Write-Host "Unpack $Label → $tmp"
  Expand-Archive -LiteralPath $ZipPath -DestinationPath $tmp -Force

  $bat = Get-ChildItem -Path $tmp -Recurse -Filter "Запустить.bat" -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $bat) {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    return @{ ok = $false; skipped = $false; detail = "Запустить.bat missing"; banner = "" }
  }
  $root = $bat.Directory.FullName
  $verFile = Join-Path $root "VERSION"
  if (-not (Test-Path -LiteralPath $verFile)) {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    return @{ ok = $false; skipped = $false; detail = "VERSION file missing"; banner = "" }
  }
  $wantVer = (Get-Content -LiteralPath $verFile -Raw).Trim()
  if (-not $wantVer -or $wantVer -eq "unknown") {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    return @{ ok = $false; skipped = $false; detail = "VERSION empty/unknown"; banner = "" }
  }

  Stop-PortListeners -Port $Port
  # Operator path uses :8000 in Запустить.bat — enforce free 8000 (Z1 one entry).
  if ($Port -ne 8000) {
    Write-Host "NOTE: operator Запустить.bat binds :8000 (ignoring alternate `$Port=$Port for launch)"
  }
  Stop-PortListeners -Port 8000

  $env:MURAVEI_BOOTSTRAP_YES = "1"
  $env:MURAVEI_NO_PAUSE = "1"
  $env:MURAVEI_NO_BROWSER = "1"
  $env:MURAVEI_BUILD_PROFILE = $(if ($Label -eq "Full") { "full" } else { "mini" })
  $outLog = Join-Path $root "logs\smoke_launcher.out"
  New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null

  $proc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", "`"$($bat.FullName)`"") `
    -WorkingDirectory $root `
    -PassThru -NoNewWindow `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError (Join-Path $root "logs\smoke_launcher.err")

  $deadline = (Get-Date).AddSeconds($HealthTimeoutSec)
  $healthOk = $false
  $uiOk = $false
  $healthBody = $null
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 3
      if ($r.StatusCode -eq 200) {
        $healthOk = $true
        $healthBody = $r.Content
        break
      }
    } catch { Start-Sleep -Seconds 2 }
  }

  $banner = ""
  if (Test-Path -LiteralPath $outLog) {
    $bannerLine = Select-String -Path $outLog -Pattern "MuraveiVision PRO v" | Select-Object -First 1
    if ($bannerLine) { $banner = $bannerLine.Line.Trim() }
  }

  $poison = Test-LogPoison -Root $root
  $logsOk = (Test-Path (Join-Path $root "logs\bootstrap.log")) -or (Test-Path (Join-Path $root "logs\uvicorn.log"))
  # bootstrap.log may be empty-created by bat; uvicorn.log required after health
  $uvLog = Test-Path (Join-Path $root "logs\uvicorn.log")

  if ($healthOk) {
    try {
      $u = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 5
      $uiOk = ($u.StatusCode -eq 200) -and (($u.Content -match 'html') -or ($u.Content.Length -gt 50))
    } catch { $uiOk = $false }
  }

  $verMatch = $banner -match [regex]::Escape("MuraveiVision PRO v$wantVer")
  # Also accept health JSON version
  $apiVerOk = $true
  if ($healthBody) {
    try {
      $hj = $healthBody | ConvertFrom-Json
      if ($hj.version -and ($hj.version -ne $wantVer)) { $apiVerOk = $false }
    } catch { }
  }

  # teardown
  try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch { }
  Get-Process | Where-Object { $_.MainWindowTitle -match 'MuraveiVision Backend' } |
    Stop-Process -Force -ErrorAction SilentlyContinue
  Stop-PortListeners -Port 8000

  $detailParts = @()
  if (-not $verMatch) { $detailParts += "banner!='$wantVer' (got: $banner)" }
  if (-not $apiVerOk) { $detailParts += "health.version mismatch" }
  if ($poison) { $detailParts += $poison }
  if (-not $uvLog) { $detailParts += "uvicorn.log missing" }
  if (-not $logsOk) { $detailParts += "logs/ missing" }
  if (-not $healthOk) { $detailParts += "health timeout ${HealthTimeoutSec}s" }
  if ($healthOk -and -not $uiOk) { $detailParts += "UI HTML failed" }

  $ok = $verMatch -and $apiVerOk -and (-not $poison) -and $uvLog -and $healthOk -and $uiOk

  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue

  if ($ok) {
    return @{ ok = $true; skipped = $false; detail = "operator OK banner=$banner"; banner = $banner }
  }
  return @{
    ok = $false
    skipped = $false
    detail = ($detailParts -join "; ")
    banner = $banner
  }
}

Write-Host "=== portable operator-path smoke ==="
Write-TableRow "Kit" "Status" "Detail"

$mini = Invoke-KitSmoke -ZipPath $MiniZip -Label "Mini" -Port 8000
Write-TableRow "Mini" $(if ($mini.ok) { "OK" } elseif ($mini.skipped) { "SKIP" } else { "FAIL" }) $mini.detail
if ($mini.banner) { Write-Host "  banner: $($mini.banner)" }

$fullResult = @{ ok = $false; skipped = $true; detail = "skipped (local-only; use -Full)"; banner = "" }
$runFull = $Full -and -not $SkipFull
if ($runFull) {
  $fullResult = Invoke-KitSmoke -ZipPath $FullZip -Label "Full" -Port 8000
}
Write-TableRow "Full" $(if ($fullResult.ok) { "OK" } elseif ($fullResult.skipped) { "skipped" } else { "FAIL" }) $fullResult.detail
if ($fullResult.banner) { Write-Host "  banner: $($fullResult.banner)" }

$miniLabel = if ($mini.ok) { "OK" } else { "FAIL" }
$fullLabel = if ($fullResult.skipped) { "skipped" } elseif ($fullResult.ok) { "OK" } else { "FAIL" }
Write-Host ""
Write-Host "CI: Mini $miniLabel / Local: Full $fullLabel"

if (-not $mini.ok) { exit 1 }
exit 0
