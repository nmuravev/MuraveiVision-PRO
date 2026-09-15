# Stage Depth Anything 3 (DA3) sidecar weights for MuraveiVision PRO FullKit.
# URLs and sha256 hashes are resolved strictly via scripts/portable_manifest.json (Z1 Zero-Hardcode).
param(
    [string]$Variant = "base",
    [string]$OutDir = "",
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# Locate Python in muravei_env or system fallback
$Py = Join-Path $Repo "muravei_env\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
    $Py = "python"
}

$FetchScript = Join-Path $Repo "scripts\fetch_da3_weights.py"
if (-not (Test-Path -LiteralPath $FetchScript)) {
    throw "fetch_da3_weights.py not found at $FetchScript"
}

$ArgsList = @($FetchScript, "--variant", $Variant)
if ($OutDir) {
    $ArgsList += @("--out-dir", $OutDir)
}
if ($VerifyOnly) {
    $ArgsList += "--verify-only"
}

Write-Host "Invoking DA3 staging script with Python: $Py"
& $Py @ArgsList
if ($LASTEXITCODE -ne 0) {
    throw "DA3 staging failed with exit code $LASTEXITCODE"
}
Write-Host "DA3 sidecar staging finished successfully." -ForegroundColor Green
