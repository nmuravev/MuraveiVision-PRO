#Requires -Version 5.1
<#
.SYNOPSIS
  Local CI pipeline — run all gates before rebuild or commit.

.DESCRIPTION
  Orchestrates: unittest → tsc → hardcode scan → import smoke → portable smoke.
  No GitHub Actions. Packs not uploaded. Local only.

  Exit 0 on all green, 1 on any failure.
#>
param(
  [switch]$SkipSmoke,
  [switch]$SkipTsc,
  [switch]$SkipHardcode,
  [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Py = Join-Path $Repo "muravei_env\Scripts\python.exe"
$Pip = Join-Path $Repo "muravei_env\Scripts\pip.exe"
$Failed = $false

function Write-Step([string]$Name) {
  Write-Host "`n=== $Name ===" -ForegroundColor Cyan
}

function Write-Pass([string]$Msg) {
  Write-Host "  PASS: $Msg" -ForegroundColor Green
}

function Write-Fail([string]$Msg) {
  Write-Host "  FAIL: $Msg" -ForegroundColor Red
  $script:Failed = $true
}

# --- Step 1: Python version + pip check ---
Write-Step "Python environment"
$ver = & $Py -c "import sys; print(sys.version)" 2>&1
Write-Host "  Python: $ver"
if ($ver -notmatch "3\.12") { Write-Fail "Python must be 3.12.x (got: $ver)" } else { Write-Pass "Python 3.12" }
$pipCheck = & $Pip check 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "  WARN: pip check issues: $pipCheck" }

# --- Step 2: Backend unittest ---
Write-Step "Backend unittest"
$utCode = @"
import sys, os
sys.path.insert(0, os.path.join(r'$($Repo.Replace("'","''"))', 'backend'))
os.chdir(os.path.join(r'$($Repo.Replace("'","''"))', 'backend'))
sys.path.insert(0, os.path.join(r'$($Repo.Replace("'","''"))', 'backend', 'tests'))
import unittest
suite = unittest.TestLoader().discover(os.path.join(r'$($Repo.Replace("'","''"))', 'backend', 'tests'), pattern='test_*.py')
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"@
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$utOut = & $Py -c $utCode 2>&1
$ErrorActionPreference = $prevEap
$utExit = $LASTEXITCODE
Write-Host ($utOut | Select-Object -Last 5 | Out-String).Trim()
if ($utExit -ne 0) { Write-Fail "unittest exit=$utExit" } else { Write-Pass "unittest" }

# --- Step 3: TypeScript check ---
if (-not $SkipTsc) {
  Write-Step "TypeScript (tsc --noEmit)"
  $tscOut = & npx tsc --noEmit 2>&1
  $tscExit = $LASTEXITCODE
  if ($tscExit -ne 0) {
    Write-Host ($tscOut | Select-Object -Last 15 | Out-String).Trim()
    Write-Fail "tsc exit=$tscExit"
  } else {
    Write-Pass "tsc --noEmit"
  }
} else {
  Write-Host "  SKIPPED" -ForegroundColor Yellow
}

# --- Step 4: Hardcode scan ---
if (-not $SkipHardcode) {
  Write-Step "Hardcode scan (machine paths, fixed UUIDs)"
  $hcPatterns = @(
    @{Pat = "[A-Z]:\\Users\\"; Label = "absolute Windows user path" },
    @{Pat = "/home/[a-z]+/"; Label = "absolute Linux home path" },
    @{Pat = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"; Label = "fixed UUID" }
  )
  $hcFound = @()
  foreach ($hp in $hcPatterns) {
    $pyHits = Select-String -Path (Join-Path $Repo "backend\**\*.py") -Pattern $hp.Pat -ErrorAction SilentlyContinue
    $tsHits = Select-String -Path (Join-Path $Repo "src\**\*.ts"), (Join-Path $Repo "src\**\*.tsx") -Pattern $hp.Pat -ErrorAction SilentlyContinue
    $all = @($pyHits) + @($tsHits)
    foreach ($h in $all) {
      # Skip test files, known patterns, and config modules
      if ($h.Path -match "test_" -or $h.Path -match "__pycache__" -or
          $h.Path -match "ultralytics_airgap\.py$" -or $h.Line -match "sys\.executable" -or
          $h.Line -match "Path\(" -or $h.Line -match "# hardcode") { continue }
      $hcFound += "$($hp.Label): $($h.Path):$($h.LineNumber): $($h.Line.Trim())"
    }
  }
  if ($hcFound.Count -gt 0) {
    $hcFound | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Write-Fail "hardcode scan found $($hcFound.Count) issue(s)"
  } else {
    Write-Pass "hardcode scan clean"
  }
} else {
  Write-Host "  SKIPPED" -ForegroundColor Yellow
}

# --- Step 5: Import smoke ---
Write-Step "Import smoke (ensure_ultralytics_airgap + key modules)"
$importCode = @"
import sys
sys.path.insert(0, r'$($Repo.Replace('\','\\'))\backend')
from services.ultralytics_airgap import ensure_ultralytics_airgap
ensure_ultralytics_airgap()
print('airgap OK')
from services.yolo_engine import get_yolo_engine
from services.sam3_engine import get_sam3_engine
from services.ffmpeg_util import resolve_ffmpeg, resolve_ffprobe
from services.response_validator import get_validator
from services.classes import get_class_catalog
print('imports OK')
import timm, safetensors
print('timm+safetensors OK')
"@
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$impOut = & $Py -c $importCode 2>&1
$ErrorActionPreference = $prevEap
$impStr = ($impOut | ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() } else { "$_" } }) -join "`n"
if ($LASTEXITCODE -ne 0 -or ($impStr -notmatch "imports OK")) {
  Write-Host $impStr
  Write-Fail "import smoke failed"
} else {
  Write-Pass "import smoke (airgap + yolo + sam3 + ffmpeg + timm)"
}

# --- Step 6: Portable smoke (optional, needs pack) ---
if (-not $SkipSmoke) {
  Write-Step "Portable smoke"
  $miniZip = Join-Path $Repo "portable\MuraveiVision_PRO_Mini.zip"
  if (Test-Path -LiteralPath $miniZip) {
    & (Join-Path $Repo "scripts\smoke_portable.ps1") -MiniZip $miniZip
    if ($LASTEXITCODE -ne 0) { Write-Fail "portable smoke Mini" } else { Write-Pass "portable smoke Mini" }
  } else {
    Write-Host "  SKIPPED (no Mini ZIP at $miniZip)" -ForegroundColor Yellow
  }
} else {
  Write-Host "  SKIPPED" -ForegroundColor Yellow
}

# --- Summary ---
Write-Host "`n=== CI Summary ===" -ForegroundColor Cyan
if ($Failed) {
  Write-Host "RESULT: FAIL" -ForegroundColor Red
  exit 1
} else {
  Write-Host "RESULT: PASS" -ForegroundColor Green
  exit 0
}
