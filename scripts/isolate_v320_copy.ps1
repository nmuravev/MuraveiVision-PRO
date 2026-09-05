#Requires -Version 5.1
<#
.SYNOPSIS
  Recreate a FULLY ISOLATED MuraveiVision-Pro-3.2.0 tree under the repo root.

.DESCRIPTION
  Copies runtime + source into MuraveiVision-Pro-3.2.0\ with no shared v3.1
  archive/runtime. Excludes .git, portable stages/ZIPs, agent junk.
  Creates empty archive/, repairs Windows venv pyvenv.cfg, patches vite
  proxy ports to 8001/3001 inside the COPY only, writes run_3.2.ps1 + ISOLATION.txt.

  Usage (from repo root):
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\isolate_v320_copy.ps1
#>
[CmdletBinding()]
param(
    [string]$SourceRoot = "",
    [string]$DestName = "MuraveiVision-Pro-3.2.0",
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 3001
)

$ErrorActionPreference = "Stop"
if (-not $SourceRoot) {
    $scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    if (-not $scriptDir) { $scriptDir = Join-Path (Get-Location) "scripts" }
    $SourceRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
}
$DestRoot = Join-Path $SourceRoot $DestName

function Invoke-Robo {
    param(
        [string]$Src,
        [string]$Dst,
        [string[]]$ExtraArgs = @()
    )
    if (-not (Test-Path -LiteralPath $Src)) {
        Write-Host "[skip] missing: $Src"
        return
    }
    New-Item -ItemType Directory -Force -Path $Dst | Out-Null
    $args = @($Src, $Dst, "/E", "/COPY:DAT", "/R:2", "/W:2", "/NFL", "/NDL", "/NP", "/MT:8") + $ExtraArgs
    Write-Host "[robocopy] $Src -> $Dst"
    & robocopy @args | Out-Null
    $code = $LASTEXITCODE
    # robocopy: 0-7 success-ish
    if ($code -ge 8) {
        throw "robocopy failed code=$code for $Src"
    }
}

Write-Host "=== isolate_v320_copy ==="
Write-Host "Source: $SourceRoot"
Write-Host "Dest:   $DestRoot"

if (Test-Path -LiteralPath $DestRoot) {
    Write-Host "[warn] Dest exists — incremental sync (will not wipe archive empty dirs after)."
} else {
    New-Item -ItemType Directory -Force -Path $DestRoot | Out-Null
}

# --- Large trees ---
$excludeCommon = @(
    "/XD", "__pycache__", ".git", ".cursor", ".continue", ".vscode",
    "MuraveiVision-Pro-3.2.0", "portable", "node_modules", "muravei_env",
    "sidecars", "archive", ".backup", "openreel-reference", "playwright-report",
    "test-results", "cache", "runs", "reports", "logs"
)

# Root shallow-ish copy of source tree excluding heavy/excluded dirs
Invoke-Robo -Src $SourceRoot -Dst $DestRoot -ExtraArgs (
    $excludeCommon + @(
        "/XF", "*.zip",
        "portable_*.log",
        ".cursorignore",
        "debug-*.log"
    )
)

# Full large directories
Invoke-Robo -Src (Join-Path $SourceRoot "muravei_env") -Dst (Join-Path $DestRoot "muravei_env") -ExtraArgs @(
    "/XD", "__pycache__", ".git"
)
Invoke-Robo -Src (Join-Path $SourceRoot "node_modules") -Dst (Join-Path $DestRoot "node_modules")
Invoke-Robo -Src (Join-Path $SourceRoot "sidecars") -Dst (Join-Path $DestRoot "sidecars") -ExtraArgs @(
    "/XD", "__pycache__", "downloads"
)

# Ensure critical source dirs (in case root exclude missed nesting)
foreach ($d in @("backend", "src", "config", "scripts", "docs", "assets", "dist", "public", "tests")) {
    $s = Join-Path $SourceRoot $d
    if (Test-Path -LiteralPath $s) {
        Invoke-Robo -Src $s -Dst (Join-Path $DestRoot $d) -ExtraArgs @(
            "/XD", "__pycache__", ".git", ".pytest_cache"
        )
    }
}

# Empty archive tree (do NOT copy v3.1 media)
$archiveRoot = Join-Path $DestRoot "archive"
foreach ($sub in @("captures", "recon", "analysis", "recordings", "crops")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $archiveRoot $sub) | Out-Null
}
# Clear any accidentally copied archive media from root robocopy
Get-ChildItem -LiteralPath $archiveRoot -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $archiveRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notin @("captures", "recon", "analysis", "recordings", "crops") } |
    ForEach-Object {
        Write-Host "[archive] removing unexpected: $($_.FullName)"
        Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
# Empty known subdirs of leftover files
foreach ($sub in @("captures", "recon", "analysis", "recordings", "crops")) {
    $p = Join-Path $archiveRoot $sub
    Get-ChildItem -LiteralPath $p -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Set-Content -LiteralPath (Join-Path $archiveRoot ".gitkeep") -Value "" -Encoding ascii

# Runtime placeholders
foreach ($d in @("cache", "logs", "reports", "runs")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $DestRoot $d) | Out-Null
}

# --- Venv repair ---
$venvMethod = "copied_muravei_env + pyvenv.cfg path refresh (keep CUDA torch)"
$pyvenv = Join-Path $DestRoot "muravei_env\pyvenv.cfg"
$hostPyHome = $null
$hostPyExe = $null
$srcCfg = Join-Path $SourceRoot "muravei_env\pyvenv.cfg"
if (Test-Path -LiteralPath $srcCfg) {
    foreach ($line in Get-Content -LiteralPath $srcCfg) {
        if ($line -match '^\s*home\s*=\s*(.+)$') {
            $hostPyHome = $Matches[1].Trim()
            $hostPyExe = Join-Path $hostPyHome "python.exe"
        }
        if ($line -match '^\s*executable\s*=\s*(.+)$') {
            $exeCand = $Matches[1].Trim()
            if (-not $hostPyExe -or -not (Test-Path -LiteralPath $hostPyExe)) {
                $hostPyExe = $exeCand
                if (-not $hostPyHome) { $hostPyHome = Split-Path -Parent $hostPyExe }
            }
        }
    }
}
if (-not $hostPyHome -or -not $hostPyExe -or -not (Test-Path -LiteralPath $hostPyExe)) {
    throw "Cannot resolve host Python 3.12 from source muravei_env\pyvenv.cfg (home=). Needed only as venv base interpreter."
}

$cfg = @"
home = $hostPyHome
include-system-site-packages = false
version = 3.12.10
executable = $hostPyExe
command = $hostPyExe -m venv $($DestRoot -replace '\\','/')/muravei_env
"@
Set-Content -LiteralPath $pyvenv -Value $cfg.TrimEnd() -Encoding ascii
Write-Host "[venv] wrote pyvenv.cfg home=$hostPyHome"

$localPy = Join-Path $DestRoot "muravei_env\Scripts\python.exe"
$venvOk = $false
if (Test-Path -LiteralPath $localPy) {
    try {
        $probe = & $localPy -c "import sys; print(sys.prefix); import torch, fastapi; print('OK', torch.__version__)" 2>&1
        Write-Host $probe
        $prefixLine = ($probe | Select-Object -First 1 | Out-String).Trim()
        if ($prefixLine -like "*MuraveiVision-Pro-3.2.0*") {
            $venvOk = $true
            Write-Host "[venv] OK — sys.prefix under isolated root"
        } else {
            Write-Host "[venv] WARN sys.prefix not under isolated root: $prefixLine"
        }
    } catch {
        Write-Host "[venv] probe failed: $_"
    }
}

if (-not $venvOk) {
    Write-Host "[venv] recreating via host 3.12.10 (fallback — may lose CUDA torch pin)"
    $venvMethod = "recreated via host python -m venv + pip install -r backend/requirements.txt"
    $venvDir = Join-Path $DestRoot "muravei_env"
    if (Test-Path -LiteralPath $venvDir) {
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }
    if (-not (Test-Path -LiteralPath $hostPyExe)) {
        throw "Host Python 3.12 not found at $hostPyExe — cannot recreate venv"
    }
    & $hostPyExe -m venv $venvDir
    $pip = Join-Path $DestRoot "muravei_env\Scripts\pip.exe"
    & $pip install --no-cache-dir -r (Join-Path $DestRoot "backend\requirements.txt")
    $probe2 = & $localPy -c "import sys; print(sys.prefix); import fastapi; print('OK')"
    Write-Host $probe2
}

# --- Patch vite.config.ts inside COPY only (8000->8001, 3000->3001) ---
$viteCfg = Join-Path $DestRoot "vite.config.ts"
if (Test-Path -LiteralPath $viteCfg) {
    $txt = Get-Content -LiteralPath $viteCfg -Raw
    $txt = $txt -replace "port:\s*3000", "port: $FrontendPort"
    $txt = $txt -replace "127\.0\.0\.1:8000", "127.0.0.1:$BackendPort"
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($viteCfg, $txt, $utf8)
    Write-Host "[vite] patched proxy/port to FE=$FrontendPort BE=$BackendPort (copy only)"
}

# Ensure dist exists
$distIndex = Join-Path $DestRoot "dist\index.html"
if (-not (Test-Path -LiteralPath $distIndex)) {
    Write-Host "[build] dist missing — npm run build in copy"
    Push-Location $DestRoot
    try {
        npm run build
    } finally {
        Pop-Location
    }
}

# --- Launcher ---
$launcher = @"
# MuraveiVision Pro 3.2.0 — isolated launcher (ports $BackendPort / $FrontendPort)
# Zero absolute machine paths — only `$PSScriptRoot
`$ErrorActionPreference = "Stop"
`$Root = `$PSScriptRoot
Set-Location `$Root

`$BackendPort = if (`$env:MURAVEI_BACKEND_PORT) { [int]`$env:MURAVEI_BACKEND_PORT } else { $BackendPort }
`$FrontendPort = if (`$env:MURAVEI_FRONTEND_PORT) { [int]`$env:MURAVEI_FRONTEND_PORT } else { $FrontendPort }

`$Py = Join-Path `$Root "muravei_env\Scripts\python.exe"
if (-not (Test-Path -LiteralPath `$Py)) {
    Write-Error "Missing `$Py — repair muravei_env first"
}

`$env:COLMAP_ROOT = Join-Path `$Root "sidecars\colmap"
`$avRoot = Join-Path `$Root "sidecars\alicevision\windows-x64"
if (Test-Path -LiteralPath (Join-Path `$avRoot "bin\aliceVision_featureExtraction.exe")) {
    `$env:ALICEVISION_ROOT = `$avRoot
}
`$env:MURAVEI_SESSION_TRACE = "1"
`$env:PYTHONPATH = Join-Path `$Root "backend"

Write-Host "============================================"
Write-Host "  MuraveiVision Pro 3.2.0 (isolated)"
Write-Host "  Root: `$Root"
Write-Host "  Backend:  http://127.0.0.1:`$BackendPort"
Write-Host "  Frontend: http://127.0.0.1:`$FrontendPort"
Write-Host "  COLMAP_ROOT=`$(`$env:COLMAP_ROOT)"
Write-Host "  ALICEVISION_ROOT=`$(`$env:ALICEVISION_ROOT)"
Write-Host "============================================"

`$backendArgs = @(
    "-m", "uvicorn", "main:app",
    "--app-dir", "backend",
    "--host", "127.0.0.1",
    "--port", "`$BackendPort",
    "--log-level", "info"
)
Start-Process -FilePath `$Py -ArgumentList `$backendArgs -WorkingDirectory `$Root -WindowStyle Normal

Start-Sleep -Seconds 2

`$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not `$npm) {
    Write-Error "npm not found on PATH"
}
Start-Process -FilePath "npm" -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "`$FrontendPort", "--strictPort") -WorkingDirectory `$Root -WindowStyle Normal

Write-Host ""
Write-Host "API health: http://127.0.0.1:`$BackendPort/api/health"
Write-Host "UI:         http://127.0.0.1:`$FrontendPort/"
Write-Host "Stop via Task Manager / closing the two windows."
"@
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Join-Path $DestRoot "run_3.2.ps1"), $launcher, $utf8)

# --- ISOLATION.txt ---
$sizeBytes = (Get-ChildItem -LiteralPath $DestRoot -Recurse -Force -ErrorAction SilentlyContinue |
    Measure-Object -Property Length -Sum).Sum
$sizeGB = [math]::Round($sizeBytes / 1GB, 2)

$isolation = @"
MuraveiVision Pro 3.2.0 — FULLY ISOLATED COPY
==============================================
Created: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Source:  $SourceRoot
Dest:    $DestRoot
Size:    ~$sizeGB GB

Ports (env-overridable via MURAVEI_BACKEND_PORT / MURAVEI_FRONTEND_PORT):
  Backend  $BackendPort
  Frontend $FrontendPort

Venv method:
  $venvMethod
  Local python: muravei_env\Scripts\python.exe
  pyvenv.cfg home points at host Python 3.12.10 base install (required by Windows venv);
  sys.prefix / site-packages live under this isolated root only.

Not shared with v3.1:
  - Separate muravei_env, node_modules, sidecars, assets, dist
  - Empty archive/ (captures, recon, analysis, recordings, crops)
  - Own uvicorn cwd = this root
  - COLMAP_ROOT / ALICEVISION_ROOT set relative to `$PSScriptRoot in run_3.2.ps1

Excluded from copy:
  .git/, portable/, MuraveiVision-Pro-3.2.0/, __pycache__, .cursor,
  agent logs, root *.zip, v3.1 archive media

Launcher:
  .\run_3.2.ps1

Recreate:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\isolate_v320_copy.ps1
  (from the parent MuraveiVision-PRO checkout on feature/alicevision-v3.2)
"@
[System.IO.File]::WriteAllText((Join-Path $DestRoot "ISOLATION.txt"), $isolation, $utf8)

Write-Host "=== DONE === size≈$sizeGB GB method=$venvMethod"
Write-Host "Launcher: $(Join-Path $DestRoot 'run_3.2.ps1')"
