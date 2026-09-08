#Requires -Version 5.1
<#
.SYNOPSIS
  Portable operator-path smoke: unpack → Запустить.bat (same as field).

.DESCRIPTION
  Mini: required (CI + local). Full: local-only (-Full).

  Fails on ANY of:
    - Pack missing yolo26*.pt / exactly-one sam3.pt / KIT / ollama/ present
    - Traceback | ImportError | circular import in stderr / logs
    - Banner version != VERSION file
    - /api/health != 200 within timeout
    - UI HTML missing
    - model state == none after start (Mini)
    - YOLO infer on smoke_sample raises / no objects tensor shape

  Report: CI: Mini OK|FAIL / Local: Full OK|FAIL|skipped
#>
param(
  [string]$MiniZip = "",
  [string]$FullZip = "",
  [switch]$Full,
  [switch]$SkipFull,
  [switch]$LocalSam3Seg,
  [int]$HealthTimeoutSec = 120,
  [int]$Sam3LoadTimeoutSec = 180
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

function Assert-PackLayout([string]$Root) {
  $models = Join-Path $Root "assets\models"
  $yolo = @(Get-ChildItem -LiteralPath $models -File -Filter "yolo26*.pt" -EA SilentlyContinue |
    Where-Object { $_.Name -notmatch "seg" -and $_.Length -gt 1024 })
  if ($yolo.Count -lt 1) { return "no yolo26*.pt in assets/models" }
  $sam = @(Get-ChildItem -LiteralPath $models -File -Filter "*sam*" -EA SilentlyContinue)
  if ($sam.Count -ne 1 -or $sam[0].Name -ne "sam3.pt") {
    return "expected exactly one sam3.pt, got: $($sam.Name -join ',')"
  }
  $kit = Join-Path $Root "KIT"
  if (-not (Test-Path -LiteralPath $kit)) { return "KIT missing" }
  $kitVal = (Get-Content -LiteralPath $kit -Raw).Trim().ToLowerInvariant()
  if ($kitVal -notin @("mini", "full")) { return "KIT invalid: $kitVal" }
  if (Test-Path -LiteralPath (Join-Path $Root "ollama")) { return "ollama/ must not be in pack" }
  $names = @($yolo | ForEach-Object { $_.Name })
  $defaultOk = $false
  foreach ($want in @("yolo26l-ft.pt","yolo26m-ft.pt","yolo26s-ft.pt","yolo26n-ft.pt","yolo26n.pt")) {
    if ($names -contains $want) { $defaultOk = $true; break }
  }
  if (-not $defaultOk) { return "config default ladder names missing from pack: $($names -join ',')" }
  return $null
}

function Invoke-FunctionalDetect([string]$Root, [string]$Token) {
  $sample = Join-Path $Root "assets\smoke_sample\frame_person_car.jpg"
  if (-not (Test-Path -LiteralPath $sample)) {
    $sample = Join-Path $Repo "assets\smoke_sample\frame_person_car.jpg"
  }
  if (-not (Test-Path -LiteralPath $sample)) { return "smoke_sample missing" }
  $py = Join-Path $Root "muravei_env\python.exe"
  if (-not (Test-Path -LiteralPath $py)) { $py = Join-Path $Root "muravei_env\Scripts\python.exe" }
  if (-not (Test-Path -LiteralPath $py)) { return "pack python missing" }
  $timeoutSec = [int]$Sam3LoadTimeoutSec
  $rootPy = $Root.Replace('\','\\')
  $samplePy = $sample.Replace('\','\\')
  $script = @"
import base64, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(r'$rootPy') / 'backend'))
from services.yolo_engine import get_yolo_engine
eng = get_yolo_engine()
st = eng.status_snapshot()
print('ENGINE', json.dumps({k: st.get(k) for k in ('mode','model','kind','engine_status','init_error_ru')}))
if st.get('engine_status') == 'offline' or st.get('mode') in ('offline','error') or (st.get('kind') == 'none' and not st.get('model')):
    print('FAIL model none/offline')
    sys.exit(2)
raw = Path(r'$samplePy').read_bytes()
import asyncio
async def main():
    out = await eng.infer(raw, confidence=0.25, frame_idx=0, time_sec=0.0)
    objs = out.get('objects') or []
    print('INFER', json.dumps({'n': len(objs), 'ms': out.get('ms'), 'mode': out.get('mode'), 'kind': out.get('kind')}))
    if out.get('mode') == 'error' or 'error' in out:
        print('FAIL', out.get('error') or out)
        sys.exit(3)
    # Valid boxes: n may be 0 on synthetic blobs; require no error + list
    if not isinstance(objs, list):
        print('FAIL objects not a list')
        sys.exit(3)
asyncio.run(main())
from services.sam3_engine import get_sam3_engine
sam = get_sam3_engine()
sst = sam.status()
print('SAM3_STATUS', json.dumps(sst))
if not sst.get('ready'):
    print('FAIL sam3 not ready')
    sys.exit(4)
t0 = time.time()
try:
    path = sam.load_model(None)
    elapsed = round(time.time() - t0, 1)
    print('SAM3_LOAD_OK', path.name, 'sec', elapsed)
except Exception as exc:
    print('FAIL sam3 load', exc)
    sys.exit(5)
if (time.time() - t0) > float($timeoutSec):
    print('FAIL sam3 load timeout')
    sys.exit(6)
"@
  $tmpPy = Join-Path $Root "logs\_smoke_functional.py"
  New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null
  Set-Content -LiteralPath $tmpPy -Value $script -Encoding UTF8
  $prev = $env:PYTHONPATH
  $env:PYTHONPATH = Join-Path $Root "backend"
  try {
    $out = & $py $tmpPy 2>&1 | Out-String
  } finally {
    $env:PYTHONPATH = $prev
  }
  Write-Host $out
  if ($LASTEXITCODE -ne 0) { return "functional detect/sam3 failed exit=$LASTEXITCODE" }
  if ($out -notmatch "ENGINE") { return "no ENGINE status line" }
  if ($out -match "FAIL model none") { return "model state none after start" }
  if ($out -notmatch "SAM3_LOAD_OK") { return "SAM3 load failed" }
  return $null
}

function Invoke-KitSmoke([string]$ZipPath, [string]$Label, [int]$Port) {
  if (-not (Test-Path -LiteralPath $ZipPath)) {
    return @{ ok = $false; skipped = $true; detail = "ZIP missing: $ZipPath"; banner = ""; kit = "" }
  }
  $tmp = Join-Path $env:TEMP ("muravei_smoke_" + $Label + "_" + [guid]::NewGuid().ToString("n").Substring(0, 8))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  Write-Host "Unpack $Label → $tmp"
  Expand-Archive -LiteralPath $ZipPath -DestinationPath $tmp -Force

  $bat = Get-ChildItem -Path $tmp -Recurse -Filter "Запустить.bat" -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $bat) {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    return @{ ok = $false; skipped = $false; detail = "Запустить.bat missing"; banner = ""; kit = "" }
  }
  $root = $bat.Directory.FullName
  $layoutErr = Assert-PackLayout -Root $root
  if ($layoutErr) {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    return @{ ok = $false; skipped = $false; detail = "pack layout: $layoutErr"; banner = ""; kit = "" }
  }
  $kitVal = (Get-Content -LiteralPath (Join-Path $root "KIT") -Raw).Trim()

  $verFile = Join-Path $root "VERSION"
  if (-not (Test-Path -LiteralPath $verFile)) {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    return @{ ok = $false; skipped = $false; detail = "VERSION file missing"; banner = ""; kit = $kitVal }
  }
  $wantVer = (Get-Content -LiteralPath $verFile -Raw).Trim()
  if (-not $wantVer -or $wantVer -eq "unknown") {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    return @{ ok = $false; skipped = $false; detail = "VERSION empty/unknown"; banner = ""; kit = $kitVal }
  }

  # Copy smoke sample into pack if build omitted it
  $smokeDst = Join-Path $root "assets\smoke_sample"
  $smokeSrc = Join-Path $Repo "assets\smoke_sample"
  if ((Test-Path $smokeSrc) -and -not (Test-Path (Join-Path $smokeDst "frame_person_car.jpg"))) {
    New-Item -ItemType Directory -Force -Path $smokeDst | Out-Null
    Copy-Item -LiteralPath (Join-Path $smokeSrc "*") -Destination $smokeDst -Force
  }

  Stop-PortListeners -Port $Port
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
  $uvLog = Test-Path (Join-Path $root "logs\uvicorn.log")

  if ($healthOk) {
    try {
      $u = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 5
      $uiOk = ($u.StatusCode -eq 200) -and (($u.Content -match 'html') -or ($u.Content.Length -gt 50))
    } catch { $uiOk = $false }
  }

  $verMatch = $banner -match [regex]::Escape("MuraveiVision PRO v$wantVer")
  $apiVerOk = $true
  if ($healthBody) {
    try {
      $hj = $healthBody | ConvertFrom-Json
      if ($hj.version -and ($hj.version -ne $wantVer)) { $apiVerOk = $false }
    } catch { }
  }

  $funcErr = $null
  $badgeOk = $true
  if ($healthOk -and $Label -eq "Mini") {
    $funcErr = Invoke-FunctionalDetect -Root $root -Token ""
    # Badge string via hardware (may need auth — skip soft if 401)
    try {
      $hw = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/system/version" -UseBasicParsing -TimeoutSec 5
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
  if ($funcErr) { $detailParts += $funcErr }

  $ok = $verMatch -and $apiVerOk -and (-not $poison) -and $uvLog -and $healthOk -and $uiOk -and (-not $funcErr)

  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue

  if ($ok) {
    return @{ ok = $true; skipped = $false; detail = "operator+functional OK kit=$kitVal banner=$banner"; banner = $banner; kit = $kitVal }
  }
  return @{
    ok = $false
    skipped = $false
    detail = ($detailParts -join "; ")
    banner = $banner
    kit = $kitVal
  }
}

Write-Host "=== portable operator-path + functional smoke ==="
Write-TableRow "Kit" "Status" "Detail"

$mini = Invoke-KitSmoke -ZipPath $MiniZip -Label "Mini" -Port 8000
Write-TableRow "Mini" $(if ($mini.ok) { "OK" } elseif ($mini.skipped) { "SKIP" } else { "FAIL" }) $mini.detail
if ($mini.banner) { Write-Host "  banner: $($mini.banner)" }
if ($mini.kit) { Write-Host "  KIT: $($mini.kit)" }

$fullResult = @{ ok = $false; skipped = $true; detail = "skipped (local-only; use -Full)"; banner = ""; kit = "" }
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
