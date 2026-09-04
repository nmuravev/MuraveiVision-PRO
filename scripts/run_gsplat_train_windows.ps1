# Full gsplat train on Windows: vcvars MSVC 14.44 + CUDA 12.8 + WIN32 lean flags.
# Discovers ready jobs unless -JobId is passed (no hardcoding required).
param(
    [string]$JobId = "",
    [int]$MaxSteps = 30000,
    [switch]$Force,
    [switch]$BootstrapOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$CudaHome = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8"
$PyInc = "C:\Users\MECHREVO\AppData\Local\Programs\Python\Python312\Include"
$Py = Join-Path $RepoRoot "muravei_env\Scripts\python.exe"

if (-not (Test-Path $Vcvars)) { throw "vcvars not found: $Vcvars" }
if (-not (Test-Path $Py)) { throw "python not found: $Py" }

# Strip copy-paste whitespace / line wraps from -JobId (any job, not a specific id).
if ($JobId) {
    $originalJobId = $JobId
    $JobId = ($JobId -replace '\s', '')
    if ($JobId -ne $originalJobId) {
        Write-Warning "JobId sanitized from '$originalJobId' to '$JobId'"
    }
}

$forceArg = if ($Force) { "--force" } else { "" }
$bootArg = if ($BootstrapOnly) { "--bootstrap-only" } else { "" }
$jobArg = if ($JobId) { "--job-id $JobId" } else { "" }

$inner = @"
@echo off
call "$Vcvars" -vcvars_ver=14.44
set "CUDA_HOME=$CudaHome"
set "CUDA_PATH=%CUDA_HOME%"
set "PATH=%CUDA_HOME%\bin;%PATH%"
set "INCLUDE=$PyInc;%INCLUDE%"
set "TORCH_CUDA_ARCH_LIST=12.0"
set "TORCH_NVCC_FLAGS=-allow-unsupported-compiler -DWIN32_LEAN_AND_MEAN -Usmall"
set "NVCC_PREPEND_FLAGS=-allow-unsupported-compiler -DWIN32_LEAN_AND_MEAN -Usmall"
cd /d "$RepoRoot"
set PYTHONPATH=backend
"$Py" scripts\patch_gsplat_windows_jit.py
"$Py" backend\scripts\batch_gsplat_train.py $jobArg --max-steps $MaxSteps $forceArg $bootArg
exit /b %ERRORLEVEL%
"@

$bat = Join-Path $env:TEMP "muravei_gsplat_train.bat"
Set-Content -Path $bat -Value $inner -Encoding ASCII
Write-Host "Running $bat"
cmd /c "`"$bat`""
exit $LASTEXITCODE
