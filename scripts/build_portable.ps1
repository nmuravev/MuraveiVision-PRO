#Requires -Version 5.1
<#
.SYNOPSIS
  Сборка MuraveiVision PRO Portable ZIP (Lite, Mini, или Full Field Kit).

.DESCRIPTION
  Lite (по умолчанию):
  - npm run build → dist/
  - Embeddable Python 3.12.10 → stage\muravei_env (+ get-pip + requirements)
  - backend, dist, detect-веса, YAML, Запустить.bat
  - ZIP: portable\MuraveiVision_PRO_Portable.zip

  Mini (-NoDetectWeights):
  - то же без detect .pt / mobileclip (UI/geo/отчёты; YOLO → 503 до USB-import)
  - ZIP: portable\MuraveiVision_PRO_Mini.zip

  FullKit (-FullKit):
  - то же + ollama + qwen2.5vl:7b + torch cu128 (или -TorchFlavor cpu)
  - sidecars\colmap + sidecars\gsplat_examples (3D)
  - ZIP: portable\MuraveiVision_PRO_FullKit.zip (Zip64)
    CPU flavor: MuraveiVision_PRO_FullKit_win_cpu.zip

  Только muravei_env / embed 3.12.10 — никогда host Python 3.14.
  Build-time downloads need network (or offline wheels/); field ZIP is air-gap.

  Staging: unique portable\stage_<Kit>_<timestamp>\ each run; ZIP names stay stable.
  Deps: host muravei_env pip --python <staged> (prefer portable\cache\wheels offline).
  Robocopy host site-packages only as fallback (or MURAVEI_PORTABLE_MIRROR=1).
#>
param(
  [switch]$SkipNpmBuild,
  [switch]$FetchEmbeddablePython,
  [switch]$SkipZip,
  [switch]$FullKit,
  [switch]$NoDetectWeights,
  [switch]$IncludeAliceVision,
  [switch]$NoAliceVision,
  [ValidateSet("cuda", "cpu")]
  [string]$TorchFlavor = "cuda",
  [string]$OllamaZipPath = "",
  [string]$OllamaVersion = "v0.11.4",
  [string]$OllamaModelsRoot = ""
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutRoot = Join-Path $Repo "portable"
$CacheDir = Join-Path $OutRoot "cache"
$PyVer = "3.12.10"
$HostPy = Join-Path $Repo "muravei_env\Scripts\python.exe"
$HostPip = Join-Path $Repo "muravei_env\Scripts\pip.exe"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"

if ($FullKit) {
  $KitTag = if ($TorchFlavor -eq "cpu") { "FullKitCpu" } else { "FullKit" }
  $ZipPath = if ($TorchFlavor -eq "cpu") {
    Join-Path $OutRoot "MuraveiVision_PRO_FullKit_win_cpu.zip"
  } else {
    Join-Path $OutRoot "MuraveiVision_PRO_FullKit.zip"
  }
  $KitKind = if ($TorchFlavor -eq "cpu") { "FULL KIT (CPU / no CUDA torch)" } else { "FULL KIT" }
} elseif ($NoDetectWeights) {
  $KitTag = "Mini"
  $ZipPath = Join-Path $OutRoot "MuraveiVision_PRO_Mini.zip"
  $KitKind = "Mini (no detect weights)"
} else {
  $KitTag = "Lite"
  $ZipPath = Join-Path $OutRoot "MuraveiVision_PRO_Portable.zip"
  $KitKind = "Lite"
}
# Unique stage per run — avoids stale DLL locks on fixed-name dirs
$StageName = "stage_${KitTag}_$Stamp"
$Stage = Join-Path $OutRoot $StageName

Write-Host "== MuraveiVision PRO v3.1 portable $KitKind ==" -ForegroundColor Cyan
Write-Host "Repo:  $Repo"
Write-Host "Stage: $Stage"

function Assert-File([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { throw "Missing: $Path" }
}

function Remove-Pycache([string]$Root) {
  Get-ChildItem -LiteralPath $Root -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
  Get-ChildItem -LiteralPath $Root -Recurse -Filter "*.pyc" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
}

function Write-Zip64([string]$SourceDir, [string]$DestZip) {
  Add-Type -AssemblyName System.IO.Compression
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  if (Test-Path -LiteralPath $DestZip) { Remove-Item -LiteralPath $DestZip -Force }
  # CompressionLevel: 0=Optimal, 1=Fastest, 2=NoCompression
  [System.IO.Compression.ZipFile]::CreateFromDirectory(
    $SourceDir,
    $DestZip,
    [System.IO.Compression.CompressionLevel]::Fastest,
    $false
  )
}

function Resolve-OllamaStoreRoot([string]$Explicit) {
  # Build-machine only (never baked into ZIP). No machine-specific absolute paths.
  $candidates = @()
  if ($Explicit) { $candidates += $Explicit }
  if ($env:OLLAMA_MODELS) { $candidates += $env:OLLAMA_MODELS }
  $candidates += (Join-Path $env:USERPROFILE ".ollama")
  $candidates += (Join-Path $env:USERPROFILE ".ollama\models")
  foreach ($c in $candidates) {
    if (-not $c) { continue }
    if (-not (Test-Path -LiteralPath $c)) { continue }
    $manifest = Join-Path $c "manifests\registry.ollama.ai\library\qwen2.5vl\7b"
    $blobs = Join-Path $c "blobs"
    if ((Test-Path -LiteralPath $manifest) -and (Test-Path -LiteralPath $blobs)) {
      return (Resolve-Path -LiteralPath $c).Path
    }
  }
  return $null
}

function Remove-StalePortableStages([string]$Root) {
  if (-not (Test-Path -LiteralPath $Root)) { return }
  $patterns = @("stage_*", "*.locked_*", "MuraveiVision_PRO_Portable", "MuraveiVision_PRO_Mini", "MuraveiVision_PRO_FullKit")
  foreach ($pat in $patterns) {
    Get-ChildItem -LiteralPath $Root -Directory -Filter $pat -ErrorAction SilentlyContinue | ForEach-Object {
      Write-Host "Cleaning stale stage: $($_.Name)" -ForegroundColor DarkYellow
      try {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
      } catch {
        $bakName = "$($_.Name).locked_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Write-Host "  locked — rename to $bakName ($($_.Exception.Message))" -ForegroundColor Yellow
        try {
          Rename-Item -LiteralPath $_.FullName -NewName $bakName -ErrorAction Stop
        } catch {
          Write-Host "  WARNING: leave in place: $($_.FullName)" -ForegroundColor Yellow
        }
      }
    }
  }
}

function Copy-OllamaModelQwen([string]$StoreRoot, [string]$DestModels) {
  $manifestRel = "manifests\registry.ollama.ai\library\qwen2.5vl\7b"
  $manifestSrc = Join-Path $StoreRoot $manifestRel
  Assert-File $manifestSrc
  $json = Get-Content -LiteralPath $manifestSrc -Raw | ConvertFrom-Json
  $digests = New-Object System.Collections.Generic.List[string]
  if ($json.config.digest) { $digests.Add([string]$json.config.digest) }
  foreach ($layer in $json.layers) {
    if ($layer.digest) { $digests.Add([string]$layer.digest) }
  }
  $destBlobs = Join-Path $DestModels "blobs"
  $destManifestDir = Join-Path $DestModels "manifests\registry.ollama.ai\library\qwen2.5vl"
  New-Item -ItemType Directory -Force -Path $destBlobs | Out-Null
  New-Item -ItemType Directory -Force -Path $destManifestDir | Out-Null
  Copy-Item -LiteralPath $manifestSrc -Destination (Join-Path $destManifestDir "7b") -Force
  $srcBlobs = Join-Path $StoreRoot "blobs"
  $copied = 0
  $bytes = [int64]0
  foreach ($d in $digests) {
    $fileName = ($d -replace "^sha256:", "sha256-")
    $src = Join-Path $srcBlobs $fileName
    if (-not (Test-Path -LiteralPath $src)) {
      throw "Missing blob for $d at $src"
    }
    $dst = Join-Path $destBlobs $fileName
    if (-not (Test-Path -LiteralPath $dst)) {
      Copy-Item -LiteralPath $src -Destination $dst -Force
    }
    $copied++
    $bytes += (Get-Item -LiteralPath $src).Length
  }
  Write-Host ("  qwen2.5vl:7b blobs={0} size={1:N1} GB" -f $copied, ($bytes / 1GB))
}

# --- Host muravei_env torch probe (dev machine only) ---
if (Test-Path -LiteralPath $HostPy) {
  Write-Host "Host muravei_env probe..." -ForegroundColor DarkCyan
  & $HostPy -c "import sys; print('host', sys.version)"
  if ($LASTEXITCODE -ne 0) { throw "Host muravei_env python failed — use 3.12.10 only" }
  & $HostPy -c "import torch; print('host torch', torch.__version__, 'cuda', torch.version.cuda)" 2>$null
} else {
  Write-Host "WARNING: host muravei_env\Scripts\python.exe missing (ok for CI if baking embed)." -ForegroundColor Yellow
}

# --- 1) Frontend ---
if (-not $SkipNpmBuild) {
  Push-Location $Repo
  try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed ($LASTEXITCODE)" }
  } finally {
    Pop-Location
  }
}

Assert-File (Join-Path $Repo "dist\index.html")
Assert-File (Join-Path $Repo "backend\requirements.txt")
Assert-File (Join-Path $Repo "Запустить.bat")

$distHtml = Get-Content -LiteralPath (Join-Path $Repo "dist\index.html") -Raw
if ($distHtml -notmatch "Content-Security-Policy") {
  throw "dist/index.html missing CSP meta — rebuild frontend"
}

# --- Stage (unique timestamped dir; purge stale stages first) ---
New-Item -ItemType Directory -Force -Path $OutRoot | Out-Null
Remove-StalePortableStages $OutRoot
New-Item -ItemType Directory -Path $Stage | Out-Null

Write-Host "Copy backend + dist ..."
Copy-Item -LiteralPath (Join-Path $Repo "backend") -Destination (Join-Path $Stage "backend") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $Repo "dist") -Destination (Join-Path $Stage "dist") -Recurse -Force
Remove-Pycache (Join-Path $Stage "backend")

foreach ($rel in @(
  "archive", "archive\crops", "archive\recordings", "archive\captures",
  "cache", "logs", "reports", "assets\models", "assets\ffmpeg",
  "runs\detect\train\weights"
)) {
  New-Item -ItemType Directory -Force -Path (Join-Path $Stage $rel) | Out-Null
}

Write-Host "Copy detect weights (no seg/yoloe)..."
$weightSources = @(
  (Join-Path $Repo "runs\detect\train\weights"),
  (Join-Path $Repo "assets\models")
)
$destW = Join-Path $Stage "runs\detect\train\weights"
$destA = Join-Path $Stage "assets\models"
if ($NoDetectWeights) {
  Write-Host "  -NoDetectWeights: skip .pt / mobileclip (Mini kit)" -ForegroundColor Yellow
} else {
  foreach ($srcDir in $weightSources) {
    if (-not (Test-Path -LiteralPath $srcDir)) { continue }
    Get-ChildItem -LiteralPath $srcDir -File -Filter "*.pt" -ErrorAction SilentlyContinue |
      Where-Object {
        $n = $_.Name.ToLowerInvariant()
        ($n -notmatch "seg") -and ($n -notmatch "yoloe") -and ($_.Length -gt 1024)
      } |
      ForEach-Object {
        Write-Host ("  {0} ({1:N1} MB)" -f $_.Name, ($_.Length / 1MB))
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $destW $_.Name) -Force
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $destA $_.Name) -Force
      }
  }

  # Prefer yolo26n-ft.pt as best when FullKit
  $ft = Join-Path $destA "yolo26n-ft.pt"
  $bestA = Join-Path $destA "best.pt"
  $y26 = Join-Path $destA "yolo26n.pt"
  if ($FullKit -and (Test-Path -LiteralPath $ft)) {
    Copy-Item $ft $bestA -Force
    Write-Host "  mirrored yolo26n-ft.pt → assets/models/best.pt"
  } elseif ((-not (Test-Path $bestA) -or (Get-Item $bestA).Length -lt 1024) -and (Test-Path $y26)) {
    Copy-Item $y26 $bestA -Force
    Write-Host "  mirrored yolo26n.pt → assets/models/best.pt"
  }

  if ($FullKit -and -not (Test-Path -LiteralPath $ft)) {
    Write-Host "WARNING: yolo26n-ft.pt missing in assets/models — FullKit will ship other detect weights if any." -ForegroundColor Yellow
  }
}

if (Test-Path (Join-Path $Repo "military_classes.yaml")) {
  Copy-Item (Join-Path $Repo "military_classes.yaml") $Stage -Force
}

if (-not $NoDetectWeights) {
  $clipCandidates = @(
    (Join-Path $Repo "mobileclip2_b.ts"),
    (Join-Path $Repo "assets\models\mobileclip2_b.ts")
  )
  foreach ($clip in $clipCandidates) {
    if (-not (Test-Path $clip)) { continue }
    $sz = (Get-Item $clip).Length / 1MB
    if ($sz -lt 280 -or $FullKit) {
      Write-Host ("Copy mobileclip2_b.ts ({0:N0} MB)" -f $sz)
      Copy-Item $clip (Join-Path $Stage "mobileclip2_b.ts") -Force
      Copy-Item $clip (Join-Path $destA "mobileclip2_b.ts") -Force
    } else {
      Write-Host "Skip oversized mobileclip2_b.ts (use -FullKit to force)"
    }
    break
  }
}

Copy-Item (Join-Path $Repo "Запустить.bat") $Stage -Force
Copy-Item (Join-Path $Repo "README.md") $Stage -Force

foreach ($bad in @(
  (Join-Path $Stage "muravei.db"),
  (Join-Path $Stage "backend\muravei.db")
)) {
  if (Test-Path $bad) { Remove-Item $bad -Force }
}
Get-ChildItem (Join-Path $Stage "logs") -Filter "*.log" -ErrorAction SilentlyContinue | Remove-Item -Force

# --- Embeddable Python as muravei_env ---
if ($FetchEmbeddablePython) {
  $zipName = "python-$PyVer-embed-amd64.zip"
  $url = "https://www.python.org/ftp/python/$PyVer/$zipName"
  New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
  $tmpZip = Join-Path $CacheDir $zipName
  $PyHome = Join-Path $Stage "muravei_env"

  Write-Host "Downloading embeddable Python $PyVer ..." -ForegroundColor Yellow
  if (-not (Test-Path -LiteralPath $tmpZip)) {
    Invoke-WebRequest -Uri $url -OutFile $tmpZip
  } else {
    Write-Host "Using cached $tmpZip"
  }

  New-Item -ItemType Directory -Force -Path $PyHome | Out-Null
  Expand-Archive -LiteralPath $tmpZip -DestinationPath $PyHome -Force

  $pthFile = Get-ChildItem -LiteralPath $PyHome -Filter "python*._pth" | Select-Object -First 1
  if (-not $pthFile) { throw "python*._pth not found" }
  $lines = Get-Content -LiteralPath $pthFile.FullName
  $out = New-Object System.Collections.Generic.List[string]
  $hasSite = $false
  $hasLib = $false
  foreach ($line in $lines) {
    if ($line -match '^\s*#\s*import\s+site\s*$') {
      $out.Add("import site"); $hasSite = $true
    } elseif ($line -match '^\s*import\s+site\s*$') {
      $out.Add("import site"); $hasSite = $true
    } else {
      $out.Add($line)
      if ($line -match 'Lib\\site-packages') { $hasLib = $true }
    }
  }
  if (-not $hasSite) { $out.Add("import site") }
  if (-not $hasLib) { $out.Add("Lib\site-packages") }
  Set-Content -LiteralPath $pthFile.FullName -Value $out -Encoding ASCII

  $getPip = Join-Path $CacheDir "get-pip.py"
  Write-Host "get-pip + requirements (долго)..." -ForegroundColor Yellow
  if (-not (Test-Path -LiteralPath $getPip)) {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
  }
  $pyExe = Join-Path $PyHome "python.exe"
  & $pyExe $getPip --no-warn-script-location
  if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }

  $scriptsPy = Join-Path $PyHome "Scripts\python.exe"
  if (-not (Test-Path $scriptsPy)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $PyHome "Scripts") | Out-Null
    Copy-Item $pyExe $scriptsPy -Force
  }

  # Harden TLS for embeddable pip: vendor cacert can vanish during pip self-upgrade
  # (OSError: Could not find a suitable TLS CA certificate bundle).
  # Always pin env vars to a *stable* host certifi path — never the staged vendor
  # file, which pip may delete mid-install while SSL_CERT_FILE still points at it.
  function Ensure-PipCaBundle([string]$PyHomePath) {
    $vendorPem = Join-Path $PyHomePath "Lib\site-packages\pip\_vendor\certifi\cacert.pem"
    $cachePem = Join-Path $CacheDir "cacert.pem"
    $hostCandidates = @(
      (Join-Path $Repo "muravei_env\Lib\site-packages\certifi\cacert.pem"),
      (Join-Path $Repo "muravei_env\Lib\site-packages\pip\_vendor\certifi\cacert.pem")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    $source = $null
    if ($hostCandidates.Count -gt 0) { $source = $hostCandidates[0] }
    elseif ($env:SSL_CERT_FILE -and (Test-Path -LiteralPath $env:SSL_CERT_FILE)) { $source = $env:SSL_CERT_FILE }
    elseif ($env:REQUESTS_CA_BUNDLE -and (Test-Path -LiteralPath $env:REQUESTS_CA_BUNDLE)) { $source = $env:REQUESTS_CA_BUNDLE }

    # Prefer cache copy (outside stage, survives Remove-Item of stage + pip vendor churn)
    if ($source) {
      New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
      Copy-Item -LiteralPath $source -Destination $cachePem -Force
    }
    $stable = if (Test-Path -LiteralPath $cachePem) { $cachePem } else { $source }

    if ($stable -and -not (Test-Path -LiteralPath $vendorPem)) {
      $destDir = Split-Path -Parent $vendorPem
      New-Item -ItemType Directory -Force -Path $destDir | Out-Null
      Copy-Item -LiteralPath $stable -Destination $vendorPem -Force
      Write-Host "Restored pip vendor CA bundle from $stable"
    }
    if ($stable) {
      $env:SSL_CERT_FILE = $stable
      $env:REQUESTS_CA_BUNDLE = $stable
      $env:PIP_CERT = $stable
      $env:CURL_CA_BUNDLE = $stable
      Write-Host "PIP TLS bundle (stable): $stable"
    } else {
      Write-Host "WARNING: no CA bundle found; pip may fail TLS" -ForegroundColor Yellow
    }
  }
  Ensure-PipCaBundle $PyHome

  # Drive installs with host pip into the embed interpreter. Staged `python -m pip`
  # frequently self-corrupts mid-run on Windows (vendor modules / cacert vanish).
  if (-not (Test-Path -LiteralPath $HostPy)) {
    throw "Host muravei_env python required to bake portable deps: $HostPy"
  }
  Write-Host "Baking deps via host pip --python (embed target)..." -ForegroundColor Yellow
  # Note: --python must come BEFORE the subcommand name
  & $HostPy -m pip --python $pyExe install --upgrade pip setuptools wheel --no-warn-script-location
  $bakeEc = $LASTEXITCODE
  if ($bakeEc -ne 0) { throw "pip upgrade failed" }
  Ensure-PipCaBundle $PyHome
  $reqFile = Join-Path $Repo "backend\requirements.txt"
  $wheelDir = Join-Path $CacheDir "wheels"
  $hasWheels = (Test-Path -LiteralPath $wheelDir) -and (
    $null -ne (Get-ChildItem -LiteralPath $wheelDir -File -ErrorAction SilentlyContinue | Select-Object -First 1)
  )
  if ($hasWheels) {
    Write-Host "Using local wheel cache: $wheelDir" -ForegroundColor Yellow
    $bakeArgs = @("--python", $pyExe, "install", "--no-index", "--find-links", $wheelDir, "--prefer-binary", "--no-warn-script-location", "-r", $reqFile)
  } else {
    Write-Host "No portable/cache/wheels — online install (run scripts/cache_portable_wheels.ps1 once)" -ForegroundColor Yellow
    $bakeArgs = @("--python", $pyExe, "install", "--no-cache-dir", "--prefer-binary", "--no-warn-script-location", "-r", $reqFile)
  }
  # Default: host pip --python into embed. Robocopy only if bake fails or MURAVEI_PORTABLE_MIRROR=1.
  # Stop host uvicorn before build if AV/DLL locks persist; restart PC as last resort.
  $mirrorHost = ($env:MURAVEI_PORTABLE_MIRROR -eq "1")
  $bakeEc = 1
  if (-not $mirrorHost) {
    $maxBakeAttempts = 2
    for ($attempt = 1; $attempt -le $maxBakeAttempts; $attempt++) {
      Ensure-PipCaBundle $PyHome
      Get-ChildItem -LiteralPath (Join-Path $PyHome "Lib\site-packages") -Recurse -Filter "*.tmp" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
      Write-Host "Requirements bake attempt $attempt/$maxBakeAttempts ..." -ForegroundColor Yellow
      & $HostPy -m pip @bakeArgs
      $bakeEc = $LASTEXITCODE
      if ($bakeEc -eq 0) { break }
      Write-Host "Bake attempt $attempt failed (exit $bakeEc)" -ForegroundColor Yellow
      Start-Sleep -Seconds 2
    }
    if ($bakeEc -ne 0) {
      Write-Host "Host-pip bake failed — falling back to robocopy host site-packages" -ForegroundColor Yellow
      $mirrorHost = $true
    }
  }
  if ($mirrorHost) {
    Write-Host "Mirroring host site-packages → stage (robocopy) ..." -ForegroundColor Yellow
    $hostSp = Join-Path $Repo "muravei_env\Lib\site-packages"
    $stageSp = Join-Path $PyHome "Lib\site-packages"
    Assert-File $hostSp
    New-Item -ItemType Directory -Force -Path $stageSp | Out-Null
    & robocopy $hostSp $stageSp /E /XD __pycache__ /NFL /NDL /NJH /NJS /R:5 /W:2 | Out-Null
    $rc = $LASTEXITCODE
    # robocopy: bits 0-7 success-ish; 8+ = some copy failures (often locked DLLs if host uvicorn running)
    if ($rc -ge 16) { throw "robocopy host site-packages fatal (exit $rc)" }
    if ($rc -ge 8) {
      Write-Host "WARNING: robocopy exit $rc (some files skipped/locked) — will verify via BAKE_OK" -ForegroundColor Yellow
    } else {
      Write-Host "Host site-packages mirrored (robocopy exit $rc)"
    }
  }

  if ($FullKit -and -not $mirrorHost) {
    if ($TorchFlavor -eq "cpu") {
      Write-Host "FullKit CPU: forcing torch CPU wheels in staged muravei_env..." -ForegroundColor Yellow
      $prevEap = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      & $HostPy -m pip --python $pyExe uninstall -y torch torchvision onnxruntime-gpu 2>&1 | Out-Host
      $ErrorActionPreference = $prevEap
      $torchArgs = @("--python", $pyExe, "install", "--force-reinstall", "--no-warn-script-location", "torch", "torchvision")
      if ($hasWheels) {
        $torchArgs = @("--python", $pyExe, "install", "--no-index", "--find-links", $wheelDir, "--force-reinstall", "--no-warn-script-location", "torch", "torchvision")
        Write-Host "FullKit CPU torch from wheel cache" -ForegroundColor Yellow
      } else {
        $torchArgs += @("--no-cache-dir", "--index-url", "https://download.pytorch.org/whl/cpu")
      }
      & $HostPy -m pip @torchArgs
      if ($LASTEXITCODE -ne 0) { throw "torch CPU install failed" }
      if (-not $hasWheels) {
        & $HostPy -m pip --python $pyExe install --force-reinstall --no-warn-script-location --no-cache-dir "onnxruntime-directml>=1.16.0"
      }
      & $pyExe -c "import torch; assert not torch.version.cuda, 'expected CPU torch'; print('STAGE_TORCH', torch.__version__, 'cpu')"
      if ($LASTEXITCODE -ne 0) { throw "staged torch CPU wheel check failed" }
    } else {
      Write-Host "FullKit: forcing torch+cu128 in staged muravei_env..." -ForegroundColor Yellow
      $prevEap = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      & $HostPy -m pip --python $pyExe uninstall -y torch torchvision 2>&1 | Out-Host
      $ErrorActionPreference = $prevEap
      $torchArgs = @("--python", $pyExe, "install", "--force-reinstall", "--no-warn-script-location", "torch", "torchvision")
      if ($hasWheels) {
        $torchArgs = @("--python", $pyExe, "install", "--no-index", "--find-links", $wheelDir, "--force-reinstall", "--no-warn-script-location", "torch", "torchvision")
        Write-Host "FullKit torch from wheel cache (expect cu128 wheels present)" -ForegroundColor Yellow
      } else {
        $torchArgs += @("--no-cache-dir", "--index-url", "https://download.pytorch.org/whl/cu128")
      }
      & $HostPy -m pip @torchArgs
      $bakeEc = $LASTEXITCODE
      if ($bakeEc -ne 0) { throw "torch cu128 install failed" }
      & $pyExe -c "import torch; assert torch.version.cuda, 'expected CUDA wheel'; print('STAGE_TORCH', torch.__version__, torch.version.cuda)"
      if ($LASTEXITCODE -ne 0) { throw "staged torch CUDA wheel check failed" }
    }
  } elseif ($FullKit -and $mirrorHost) {
    if ($TorchFlavor -eq "cpu") {
      Write-Host "FullKit CPU: host mirror — verifying torch..." -ForegroundColor Yellow
      & $pyExe -c "import torch; print('STAGE_TORCH', torch.__version__, getattr(torch.version,'cuda',None))"
    } else {
      Write-Host "FullKit: host mirror already includes torch — verifying CUDA..." -ForegroundColor Yellow
      & $pyExe -c "import torch; assert torch.version.cuda, 'expected CUDA wheel'; print('STAGE_TORCH', torch.__version__, torch.version.cuda)"
      if ($LASTEXITCODE -ne 0) { throw "staged torch CUDA wheel check failed" }
    }
  }

  & $pyExe -c "import sys,fastapi,uvicorn,ultralytics,cv2,jwt; assert sys.version.startswith('3.12'); print('BAKE_OK', sys.version.split()[0], fastapi.__version__)"
  if ($LASTEXITCODE -ne 0) { throw "BAKE import failed" }
  Write-Host "Embeddable muravei_env ready (3.12)" -ForegroundColor Green
} else {
  Write-Host "WARNING: without -FetchEmbeddablePython field kit needs host Python." -ForegroundColor Yellow
  if (Test-Path $HostPy) {
    Write-Host "NOTE: host muravei_env exists but is NOT copied (use -FetchEmbeddablePython for air-gap ZIP)."
  }
  if ($FullKit) {
    throw "-FullKit requires -FetchEmbeddablePython (bake embed 3.12 + cu128 into stage\muravei_env)"
  }
}

# --- FullKit: Ollama binary + models ---
if ($FullKit) {
  Write-Host "FullKit: bundling Ollama..." -ForegroundColor Yellow
  New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
  $ollamaZip = $OllamaZipPath
  if (-not $ollamaZip) {
    $ollamaZip = Join-Path $CacheDir "ollama-windows-amd64-$OllamaVersion.zip"
  }
  if (-not (Test-Path -LiteralPath $ollamaZip)) {
    $url = "https://github.com/ollama/ollama/releases/download/$OllamaVersion/ollama-windows-amd64.zip"
    Write-Host "Downloading $url ..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $url -OutFile $ollamaZip
  } else {
    Write-Host "Using Ollama zip: $ollamaZip"
  }
  Assert-File $ollamaZip

  $ollamaStage = Join-Path $Stage "ollama"
  New-Item -ItemType Directory -Force -Path $ollamaStage | Out-Null
  Expand-Archive -LiteralPath $ollamaZip -DestinationPath $ollamaStage -Force

  $ollamaExe = Join-Path $ollamaStage "ollama.exe"
  if (-not (Test-Path -LiteralPath $ollamaExe)) {
    $found = Get-ChildItem -LiteralPath $ollamaStage -Recurse -Filter "ollama.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
      # Flatten if nested
      Write-Host "ollama.exe found at $($found.FullName) — keeping tree as extracted"
    } else {
      throw "ollama.exe not found after extract"
    }
  }

  $storeRoot = Resolve-OllamaStoreRoot $OllamaModelsRoot
  if (-not $storeRoot) {
    throw @"
FullKit: model qwen2.5vl:7b not found.

Checked: -OllamaModelsRoot, OLLAMA_MODELS, %USERPROFILE%\.ollama (and .ollama\models).

On the build machine run:
  ollama pull qwen2.5vl:7b

Or pass -OllamaModelsRoot path\to\store (folder with blobs\ + manifests\).
"@
  }
  Write-Host "Ollama store: $storeRoot"

  $destModels = Join-Path $ollamaStage "models"
  Write-Host "Copying ONLY qwen2.5vl:7b into $destModels ..." -ForegroundColor Yellow
  New-Item -ItemType Directory -Force -Path $destModels | Out-Null
  Copy-OllamaModelQwen -StoreRoot $storeRoot -DestModels $destModels
  $checkManifest = Join-Path $destModels "manifests\registry.ollama.ai\library\qwen2.5vl\7b"
  Assert-File $checkManifest

  # PORTABLE_README for Full
  $readmeFull = Join-Path $Repo "scripts\PORTABLE_README_FULL.md"
  if (Test-Path -LiteralPath $readmeFull) {
    Copy-Item $readmeFull (Join-Path $Stage "PORTABLE_README.md") -Force
  }

  # 3D sidecars (COLMAP + gsplat examples)
  Write-Host "FullKit: bundling 3D sidecars..." -ForegroundColor Yellow
  $sidecarDest = Join-Path $Stage "sidecars"
  New-Item -ItemType Directory -Force -Path $sidecarDest | Out-Null
  $colmapSrc = Join-Path $Repo "sidecars\colmap"
  if (Test-Path -LiteralPath $colmapSrc) {
    Copy-Item -LiteralPath $colmapSrc -Destination (Join-Path $sidecarDest "colmap") -Recurse -Force
    Write-Host "  sidecars\colmap copied"
  } else {
    Write-Host "WARNING: sidecars\colmap missing — 3D recon will be unavailable in this ZIP." -ForegroundColor Yellow
  }
  $gsplatSrc = Join-Path $Repo "sidecars\gsplat_examples"
  if (Test-Path -LiteralPath $gsplatSrc) {
    Copy-Item -LiteralPath $gsplatSrc -Destination (Join-Path $sidecarDest "gsplat_examples") -Recurse -Force
    Write-Host "  sidecars\gsplat_examples copied"
  } else {
    Write-Host "WARNING: sidecars\gsplat_examples missing — gsplat train may be unavailable." -ForegroundColor Yellow
  }

  # AliceVision dense/mesh (optional; large). Default ON for FullKit when staged bins exist.
  $avBinProbe = Join-Path $Repo "sidecars\alicevision\windows-x64\bin\aliceVision_featureExtraction.exe"
  $wantAv = $false
  if ($NoAliceVision) {
    $wantAv = $false
  } elseif ($IncludeAliceVision) {
    $wantAv = $true
  } else {
    # Default: include when FullKit and binaries already staged
    $wantAv = (Test-Path -LiteralPath $avBinProbe)
  }
  if ($wantAv) {
    $avSrc = Join-Path $Repo "sidecars\alicevision"
    if (Test-Path -LiteralPath $avBinProbe) {
      $avDest = Join-Path $sidecarDest "alicevision"
      New-Item -ItemType Directory -Force -Path $avDest | Out-Null
      foreach ($name in @("LICENSE.MPL-2.0", "README.txt")) {
        $f = Join-Path $avSrc $name
        if (Test-Path -LiteralPath $f) { Copy-Item -LiteralPath $f -Destination (Join-Path $avDest $name) -Force }
      }
      Copy-Item -LiteralPath (Join-Path $avSrc "windows-x64") -Destination (Join-Path $avDest "windows-x64") -Recurse -Force
      Write-Host "  sidecars\alicevision copied (-IncludeAliceVision / FullKit default when staged)"
    } else {
      Write-Host "WARNING: -IncludeAliceVision requested but windows-x64 bins missing — skip." -ForegroundColor Yellow
    }
  } else {
    Write-Host "  AliceVision sidecar skipped (Mini never bundles; FullKit use -IncludeAliceVision or stage bins)"
  }
}

$kitLabel = if ($FullKit) { "Full Field Kit" } elseif ($NoDetectWeights) { "Mini (no detect weights)" } else { "Portable Lite" }
$modelsLine = if ($NoDetectWeights) {
  "assets\models\        (empty — import .pt via USB / Система)"
} else {
  "assets\models\        (detect .pt; no seg/SAM in Lite copy filter)"
}
$sidecarLine = if ($FullKit) {
  "sidecars\colmap\      (COLMAP)`nsidecars\gsplat_examples\  (trainer)`nsidecars\alicevision\  (optional Dense/Mesh)`nollama\               (ollama.exe + models/qwen2.5vl)`nPORTABLE_README.md"
} else {
  "README.md"
}
$note = @"
MuraveiVision PRO v3.1 — $kitLabel
=================================
Запустить.bat
muravei_env\          (embeddable Python 3.12.10 + packages$(if ($FullKit) { ' + torch cu128' }))
dist\                 (UI + CSP)
backend\              (FastAPI)
$modelsLine
runs\detect\train\weights\
archive\ crops\ recordings\ captures\
military_classes.yaml
$sidecarLine

PIN: operator 1234567 / engineer 0000000 / master 0987907

Python: ONLY muravei_env (3.12) — never system 3.14.
CPU Intel/AMD amd64 OK; NVIDIA recommended for realtime YOLO/VLM.
Offline map tiles (assets/map_tiles) are NOT in this ZIP — ship separately if needed.
"@
Set-Content -LiteralPath (Join-Path $Stage "PORTABLE.txt") -Value $note -Encoding UTF8

if (-not $SkipZip) {
  Write-Host "Creating ZIP (Zip64/Fastest)..." -ForegroundColor Yellow
  Write-Zip64 -SourceDir $Stage -DestZip $ZipPath
  $zipMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
  Write-Host "ZIP: $ZipPath ($zipMb MB)" -ForegroundColor Green
}

Write-Host "Staged: $Stage" -ForegroundColor Green
Write-Host "Done."
