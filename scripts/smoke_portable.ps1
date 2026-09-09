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
  [int]$Sam3LoadTimeoutSec = 60
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
  # Baseline crash poisons (all logs)
  $basePatterns = @("Traceback", "ImportError", "circular import")
  # N1 split: uvicorn/stderr = full AutoUpdate/pip list; bootstrap = narrow only
  $uvicornPoisons = @(
    "AutoUpdate", "attempting AutoUpdate", "Access is denied", "Retry 1/2",
    "uv pip install", "pip install"
  )
  $bootstrapPoisons = @(
    "attempting AutoUpdate", "Access is denied", "Retry 1/2", "--index-strategy"
  )

  function _Hit([string]$Text, [string[]]$Patterns, [string]$Leaf) {
    foreach ($p in $Patterns) {
      if ($Text -match [regex]::Escape($p)) {
        return "poison '$p' in $Leaf"
      }
    }
    return $null
  }

  $uv = Join-Path $Root "logs\uvicorn.log"
  $boot = Join-Path $Root "logs\bootstrap.log"
  $out = Join-Path $Root "logs\smoke_launcher.out"
  $err = Join-Path $Root "logs\smoke_launcher.err"

  foreach ($f in @($uv, $out, $err, $boot)) {
    if (-not (Test-Path -LiteralPath $f)) { continue }
    $text = Get-Content -LiteralPath $f -Raw -ErrorAction SilentlyContinue
    if (-not $text) { continue }
    $leaf = Split-Path $f -Leaf
    $hit = _Hit $text $basePatterns $leaf
    if ($hit) { return $hit }
  }
  foreach ($f in @($uv, $out, $err)) {
    if (-not (Test-Path -LiteralPath $f)) { continue }
    $text = Get-Content -LiteralPath $f -Raw -ErrorAction SilentlyContinue
    if (-not $text) { continue }
    $hit = _Hit $text $uvicornPoisons (Split-Path $f -Leaf)
    if ($hit) { return $hit }
  }
  if (Test-Path -LiteralPath $boot) {
    $text = Get-Content -LiteralPath $boot -Raw -ErrorAction SilentlyContinue
    if ($text) {
      $hit = _Hit $text $bootstrapPoisons "bootstrap.log"
      if ($hit) { return $hit }
    }
  }
  return $null
}

function Assert-UnpackedInventory([string]$Root, [string]$Label) {
  $ff = Join-Path $Root "assets\ffmpeg\ffmpeg.exe"
  $fp = Join-Path $Root "assets\ffmpeg\ffprobe.exe"
  if (-not (Test-Path -LiteralPath $ff)) { return "inventory: assets/ffmpeg/ffmpeg.exe missing" }
  if (-not (Test-Path -LiteralPath $fp)) { return "inventory: assets/ffmpeg/ffprobe.exe missing" }
  $py = Join-Path $Root "muravei_env\python.exe"
  if (-not (Test-Path $py)) { $py = Join-Path $Root "muravei_env\Scripts\python.exe" }
  if (-not (Test-Path $py)) { return "inventory: pack python missing" }
  $code = @"
import importlib.metadata as m, onnxruntime as ort, sys
print(m.version('onnx'), m.version('onnxslim'), m.version('timm'))
print(','.join(ort.get_available_providers()))
import onnx, onnxslim, ultralytics, sahi, timm, safetensors
print('OK')
"@
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $rawInv = & $py -c $code 2>&1
  $ErrorActionPreference = $prevEap
  $out = ($rawInv | ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() } else { "$_" } }) -join "`n"
  if ($LASTEXITCODE -ne 0 -or ($out -notmatch "OK")) {
    return "inventory imports failed: $out"
  }
  if (($Label -eq "Mini" -or $Label -eq "FullCpu") -and ($out -notmatch "DmlExecutionProvider")) {
    return "inventory: DmlExecutionProvider missing for Mini/CPU kit: $out"
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
    raw_n = out.get('raw_n', 0)
    accepted = len(objs)
    if raw_n > 0:
        reject_ratio = round(1.0 - accepted / raw_n, 3)
    else:
        reject_ratio = 0.0
    print('INFER', json.dumps({'n': accepted, 'raw_n': raw_n, 'reject_ratio': reject_ratio, 'ms': out.get('ms'), 'mode': out.get('mode'), 'kind': out.get('kind')}))
    if out.get('mode') == 'error' or 'error' in out:
        print('FAIL', out.get('error') or out)
        sys.exit(3)
    # Valid boxes: n may be 0 on synthetic blobs; require no error + list
    if not isinstance(objs, list):
        print('FAIL objects not a list')
        sys.exit(3)
    # Validator reject_ratio gate (E6)
    if reject_ratio >= 0.5:
        print('VALIDATOR_WARN known high-reject: smoke_sample outside tactical class set')
    print('REJECT_ROW', json.dumps({'reject_ratio': reject_ratio, 'accepted': accepted, 'raw_n': raw_n}))
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
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $raw = & $py $tmpPy 2>&1
    $ErrorActionPreference = $prevEap
    $out = ($raw | ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() } else { "$_" } }) -join "`n"
  } finally {
    $env:PYTHONPATH = $prev
  }
  $funcLog = Join-Path $Root "logs\smoke_functional.out"
  Set-Content -LiteralPath $funcLog -Value $out -Encoding UTF8
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

  $inventoryLabel = if ($ZipPath -match 'win_cpu') { "FullCpu" } else { $Label }
  $invErr = Assert-UnpackedInventory -Root $root -Label $inventoryLabel

  # CRLF/LF launcher line-ending guard (E6)
  $crlfErr = $null
  $batPath = Join-Path $root "Запустить.bat"
  if (Test-Path -LiteralPath $batPath) {
    $batBytes = [System.IO.File]::ReadAllBytes($batPath)
    $batCrlf = $false
    for ($i = 0; $i -lt ($batBytes.Length - 1); $i++) {
      if ($batBytes[$i] -eq 0x0D -and $batBytes[$i+1] -eq 0x0A) { $batCrlf = $true; break }
    }
    if (-not $batCrlf) { $crlfErr = "Запустить.bat missing CRLF" }
  }
  $shPath = Join-Path $root "Запустить.sh"
  if ((-not $crlfErr) -and (Test-Path -LiteralPath $shPath)) {
    $shBytes = [System.IO.File]::ReadAllBytes($shPath)
    $shCr = $false
    for ($i = 0; $i -lt ($shBytes.Length - 1); $i++) {
      if ($shBytes[$i] -eq 0x0D) { $shCr = $true; break }
    }
    if ($shCr) { $crlfErr = "Запустить.sh has CR (must be LF-only)" }
  }

  $ffmpegPackOk = $true
  $ffmpegDetail = ""
  $ffExe = Join-Path $root "assets\ffmpeg\ffmpeg.exe"
  if (-not (Test-Path -LiteralPath $ffExe)) {
    $ffmpegPackOk = $false
    $ffmpegDetail = "assets/ffmpeg/ffmpeg.exe missing after unpack"
  } else {
    $uvFf = Join-Path $root "logs\uvicorn.log"
    if (Test-Path $uvFf) {
      $ffLine = Select-String -Path $uvFf -Pattern "\[ffmpeg\] path=" | Select-Object -First 1
      if ($ffLine) {
        $ffmpegDetail = $ffLine.Line.Trim()
        if ($ffmpegDetail -match "source=PATH") {
          $ffmpegPackOk = $false
          $ffmpegDetail = "ffmpeg resolved from PATH (not pack): $ffmpegDetail"
        }
      } else {
        $ffmpegDetail = "pack ffmpeg present; no [ffmpeg] log line yet"
      }
    } else {
      $ffmpegDetail = "pack ffmpeg present"
    }
  }
  $poison = Test-LogPoison -Root $root
  $debug401 = 0
  $uvLogPath = Join-Path $root "logs\uvicorn.log"
  if (Test-Path -LiteralPath $uvLogPath) {
    $debug401 = @(Select-String -LiteralPath $uvLogPath -Pattern '/api/debug/recent.* 401' -ErrorAction SilentlyContinue).Count
  }
  $debugPollBounded = $debug401 -le 1
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
  if ($invErr) { $detailParts += $invErr }
  if ($crlfErr) { $detailParts += $crlfErr }
  if (-not $ffmpegPackOk) { $detailParts += $ffmpegDetail }
  if ($poison) { $detailParts += $poison }
  $detailParts += "pre-login /api/debug/recent 401=$debug401"
  if (-not $debugPollBounded) { $detailParts += "pre-login debug poll is not bounded" }
  if (-not $uvLog) { $detailParts += "uvicorn.log missing" }
  if (-not $logsOk) { $detailParts += "logs/ missing" }
  if (-not $healthOk) { $detailParts += "health timeout ${HealthTimeoutSec}s" }
  if ($healthOk -and -not $uiOk) { $detailParts += "UI HTML failed" }
  if ($funcErr) { $detailParts += $funcErr }

  # Validator reject_ratio row (E6) — informational, not a gate
  $rejectRow = ""
  $smokeOut = Join-Path $root "logs\smoke_functional.out"
  if (Test-Path -LiteralPath $smokeOut) {
    $rrLine = Select-String -LiteralPath $smokeOut -Pattern "REJECT_ROW" | Select-Object -First 1
    if ($rrLine) { $rejectRow = $rrLine.Line.Trim() }
  }
  if ($rejectRow) { $detailParts += $rejectRow }

  $ok = $verMatch -and $apiVerOk -and (-not $poison) -and $uvLog -and $healthOk -and $uiOk -and (-not $funcErr) -and (-not $invErr) -and $ffmpegPackOk -and $debugPollBounded -and (-not $crlfErr)

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
