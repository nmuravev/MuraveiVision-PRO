#Requires -Version 5.1
<#
.SYNOPSIS
  Сборка MuraveiVision PRO Portable ZIP (Mini или Full Field Kit).

.DESCRIPTION
  Mini (-Mini):
  - Embeddable Python 3.12.10 + dist/backend
  - tactical YOLO26 *.pt (copy-only) + exactly one sam3.pt
  - torch CPU + onnxruntime-directml
  - ZIP: portable\MuraveiVision_PRO_Mini.zip (~3.5–4.5 GB with SAM3)
  - Ollama NOT bundled (system-optional)

  FullKit (-FullKit):
  - same weights + sam3 + sidecars (COLMAP/gsplat/AliceVision)
  - torch CUDA cu128 by default (-TorchFlavor cpu → CPU)
  - ZIP: portable\MuraveiVision_PRO_FullKit.zip
  - Ollama NOT bundled

  Lite (no -Mini/-FullKit): legacy Portable.zip with same weight rules.
  -NoDetectWeights: debug-only empty models (not a product kit).

  Never download detect weights at build time (tactical .pt copy-only).
  Torch profile: Mini/Lite → CPU; FullKit → CUDA unless -TorchFlavor cpu.
#>
param(
  [switch]$SkipNpmBuild,
  [switch]$FetchEmbeddablePython,
  [switch]$SkipZip,
  [switch]$FullKit,
  [switch]$Mini,
  [switch]$NoDetectWeights,
  [switch]$IncludeAliceVision,
  [switch]$NoAliceVision,
  [switch]$NoDA3,
  [switch]$Offline,
  [ValidateSet("cuda", "cpu")]
  [string]$TorchFlavor = "cuda"
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutRoot = Join-Path $Repo "portable"
$CacheDir = Join-Path $OutRoot "cache"
$PyVer = "3.12.10"
$HostPy = Join-Path $Repo "muravei_env\Scripts\python.exe"
$HostPip = Join-Path $Repo "muravei_env\Scripts\pip.exe"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"

# Air-gap contract: a CUDA FullKit is allowed only when both matching cu128
# wheels have already been seeded locally. Never probe or download CUDA wheels.
$CudaFlavorPending = $false
if ($FullKit -and $TorchFlavor -eq "cuda") {
  $wheelRoot = Join-Path $CacheDir "wheels"
  $cuTorch = @(Get-ChildItem -LiteralPath $wheelRoot -File -Filter "torch*+cu128*.whl" -ErrorAction SilentlyContinue)
  $cuVision = @(Get-ChildItem -LiteralPath $wheelRoot -File -Filter "torchvision*+cu128*.whl" -ErrorAction SilentlyContinue)
  if ($cuTorch.Count -eq 0 -or $cuVision.Count -eq 0) {
    $CudaFlavorPending = $true
    $TorchFlavor = "cpu"
    Write-Host "CUDA FullKit skipped: portable/cache/wheels has no matching +cu128 torch + torchvision wheels. Building CPU FullKit; no network probe/download." -ForegroundColor Yellow
  }
}

if ($FullKit) {
  $KitTag = if ($TorchFlavor -eq "cpu") { "FullKitCpu" } else { "FullKit" }
  $ZipPath = if ($TorchFlavor -eq "cpu") {
    Join-Path $OutRoot "MuraveiVision_PRO_FullKit_win_cpu.zip"
  } else {
    Join-Path $OutRoot "MuraveiVision_PRO_FullKit.zip"
  }
  $KitKind = if ($TorchFlavor -eq "cpu") { "FULL KIT (CPU / no CUDA torch)" } else { "FULL KIT" }
  $KitMarker = "full"
} elseif ($Mini -or $NoDetectWeights) {
  # Product Mini uses -Mini (with weights). -NoDetectWeights is debug-only empty models.
  $KitTag = "Mini"
  $ZipPath = Join-Path $OutRoot "MuraveiVision_PRO_Mini.zip"
  $KitKind = if ($NoDetectWeights -and -not $Mini) { "Mini (debug: no detect weights)" } else { "Mini (tactical YOLO + SAM3)" }
  $KitMarker = "mini"
  if ($Mini) { $NoDetectWeights = $false }
} else {
  $KitTag = "Lite"
  $ZipPath = Join-Path $OutRoot "MuraveiVision_PRO_Portable.zip"
  $KitKind = "Lite"
  $KitMarker = "mini"
}
# Unique stage per run — avoids stale DLL locks on fixed-name dirs
$StageName = "stage_${KitTag}_$Stamp"
$Stage = Join-Path $OutRoot $StageName

Write-Host "== MuraveiVision PRO portable $KitKind ==" -ForegroundColor Cyan
Write-Host "Repo:  $Repo"
Write-Host "Stage: $Stage"

function Get-AppVersionString {
  $desc = ""
  try {
    Push-Location $Repo
    $desc = (& git describe --tags --always 2>$null | Out-String).Trim()
  } catch { $desc = "" } finally { Pop-Location }
  if (-not $desc) {
    $pkg = Join-Path $Repo "package.json"
    if (Test-Path -LiteralPath $pkg) {
      $m = Select-String -Path $pkg -Pattern '"version"\s*:\s*"([^"]+)"' | Select-Object -First 1
      if ($m) { $desc = $m.Matches[0].Groups[1].Value }
    }
  }
  if (-not $desc) { $desc = "unknown" }
  return ($desc -replace '^[vV]', '')
}

$AppVersion = Get-AppVersionString
Write-Host "VERSION: $AppVersion"

function Assert-File([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { throw "Missing: $Path" }
}

function Ensure-PackFfmpeg {
  # Offline-first: portable/cache/ffmpeg/{ffmpeg,ffprobe}.exe → stage assets/ffmpeg.
  # If missing, one-time fetch from portable_manifest.json (URL+sha256 only there).
  $cacheFf = Join-Path $CacheDir "ffmpeg"
  $stageFf = Join-Path $Stage "assets\ffmpeg"
  New-Item -ItemType Directory -Force -Path $cacheFf | Out-Null
  New-Item -ItemType Directory -Force -Path $stageFf | Out-Null
  $need = @("ffmpeg.exe", "ffprobe.exe")
  $missing = @($need | Where-Object { -not (Test-Path -LiteralPath (Join-Path $cacheFf $_)) })
  if ($missing.Count -gt 0) {
    if ($Offline) { throw "BUILD FAIL (offline): ffmpeg cache missing $($missing -join ', ')" }
    Write-Host "ffmpeg cache missing ($($missing -join ', ')) — one-time fetch from manifest..." -ForegroundColor Yellow
    $manPath = Join-Path $Repo "scripts\portable_manifest.json"
    if (-not (Test-Path -LiteralPath $manPath)) { throw "portable_manifest.json missing for ffmpeg fetch" }
    $man = Get-Content -LiteralPath $manPath -Raw | ConvertFrom-Json
    $comp = $man.components.ffmpeg_windows_essentials
    if (-not $comp -or -not $comp.url -or -not $comp.sha256) { throw "manifest.components.ffmpeg_windows_essentials incomplete" }
    $zip = Join-Path $CacheDir "ffmpeg-6.1.1-essentials_build.zip"
    if (-not (Test-Path -LiteralPath $zip)) {
      Invoke-WebRequest -Uri ([string]$comp.url) -OutFile $zip -UseBasicParsing
    }
    $got = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
    $expect = ([string]$comp.sha256).ToLowerInvariant()
    if ($got -ne $expect) { throw "ffmpeg zip sha256 mismatch: got $got expected $expect" }
    $ex = Join-Path $CacheDir "_ffmpeg_extract"
    if (Test-Path $ex) { Remove-Item $ex -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $ex -Force
    foreach ($n in $need) {
      $hit = Get-ChildItem $ex -Recurse -Filter $n -File | Select-Object -First 1
      if (-not $hit) { throw "ffmpeg extract missing $n" }
      Copy-Item -LiteralPath $hit.FullName -Destination (Join-Path $cacheFf $n) -Force
    }
    Remove-Item $ex -Recurse -Force -EA SilentlyContinue
  }
  foreach ($n in $need) {
    $src = Join-Path $cacheFf $n
    if (-not (Test-Path -LiteralPath $src)) { throw "BUILD FAIL: pack ffmpeg missing $src" }
    if ((Get-Item $src).Length -lt 1024) { throw "BUILD FAIL: $n too small (shim?)" }
    Copy-Item -LiteralPath $src -Destination (Join-Path $stageFf $n) -Force
    Write-Host ("  assets/ffmpeg/{0} ({1:N1} MB)" -f $n, ((Get-Item $src).Length / 1MB))
  }
}

function Assert-PackInventory {
  param([string]$Kit)
  $missing = New-Object System.Collections.Generic.List[string]
  $fail = New-Object System.Collections.Generic.List[string]
  $py = Join-Path $Stage "muravei_env\python.exe"
  if (-not (Test-Path $py)) { $py = Join-Path $Stage "muravei_env\Scripts\python.exe" }
  if (-not (Test-Path $py)) { $missing.Add("python 3.12 embeddable") }

  $reqImports = @(
    "torch", "onnx", "onnxslim", "onnxruntime", "ultralytics", "sahi",
    "fastapi", "uvicorn", "pydantic", "cv2", "numpy", "PIL", "timm", "safetensors"
  )
  if (Test-Path $py) {
    $code = @"
import importlib, importlib.metadata, sys
pkgs = ['onnx','onnxslim','timm','safetensors']
for p in pkgs:
    print('META', p, importlib.metadata.version(p))
import onnxruntime as ort
print('ORT', ','.join(ort.get_available_providers()))
for m in ['torch','ultralytics','sahi','fastapi','uvicorn','pydantic','cv2','numpy','PIL','timm','safetensors']:
    importlib.import_module(m)
print('IMPORTS_OK')
assert sys.version.startswith('3.12')
"@
    $out = & $py -c $code 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or ($out -notmatch "IMPORTS_OK")) {
      $fail.Add("python imports failed: $out")
    } else {
      if ($out -notmatch "META onnx") { $missing.Add("onnx metadata") }
      if ($out -notmatch "META onnxslim") { $missing.Add("onnxslim metadata") }
      if ($out -notmatch "META timm") { $missing.Add("timm metadata") }
      if ($Kit -eq "mini" -or $TorchFlavor -eq "cpu") {
        if ($out -notmatch "DmlExecutionProvider") {
          $fail.Add("DmlExecutionProvider missing for Mini/CPU kit")
        }
      }
    }
  }

  foreach ($n in @("ffmpeg.exe", "ffprobe.exe")) {
    if (-not (Test-Path (Join-Path $Stage "assets\ffmpeg\$n"))) { $missing.Add("assets/ffmpeg/$n") }
  }
  if (-not $NoDetectWeights) {
    $models = Join-Path $Stage "assets\models"
    $yolo = @(Get-ChildItem $models -File -Filter "yolo26*.pt" -EA SilentlyContinue | Where-Object { $_.Name -notmatch "seg" -and $_.Length -gt 1024 })
    if ($yolo.Count -lt 1) { $missing.Add("yolo26*.pt tactical") }
    $sam = Join-Path $models "sam3.pt"
    if (-not (Test-Path $sam)) { $missing.Add("sam3.pt") }
  }
  foreach ($rel in @("backend", "dist", "assets\smoke_sample", "VERSION", "KIT", "Запустить.bat")) {
    if (-not (Test-Path (Join-Path $Stage $rel))) { $missing.Add($rel) }
  }
  if ($Kit -eq "full") {
    if (-not (Test-Path (Join-Path $Stage "sidecars\colmap"))) { $missing.Add("sidecars/colmap") }
  }
  # N3: sidecars/da3 is OPTIONAL — Mini never requires it; FullKit only when staged (do not fail if absent)
  $da3Stage = Join-Path $Stage "sidecars\da3"
  if ($Kit -eq "mini") {
    if (Test-Path -LiteralPath $da3Stage) {
      $da3Bins = @(Get-ChildItem -LiteralPath $da3Stage -File -EA SilentlyContinue |
        Where-Object { $_.Extension -match '\.(safetensors|pt)$' })
      if ($da3Bins.Count -gt 0) { $fail.Add("FORBIDDEN Mini sidecars/da3 weights") }
    }
  } else {
    # FullKit: if any NC weight staged, NOTICE must sit beside it
    if (Test-Path -LiteralPath $da3Stage) {
      $ncWeights = @(Get-ChildItem -LiteralPath $da3Stage -File -EA SilentlyContinue |
        Where-Object { $_.Name -match '^da3_(large|giant)\.(safetensors|pt)$' })
      if ($ncWeights.Count -gt 0) {
        $notice = Join-Path $da3Stage "NOTICE_CC-BY-NC-4.0.txt"
        if (-not (Test-Path -LiteralPath $notice)) {
          $fail.Add("MISSING sidecars/da3/NOTICE_CC-BY-NC-4.0.txt (NC weights present)")
        }
      }
    }
  }
  # Forbidden
  if (Test-Path (Join-Path $Stage "ollama")) { $fail.Add("FORBIDDEN ollama/") }
  if (Test-Path (Join-Path $Stage "node_modules")) { $fail.Add("FORBIDDEN node_modules") }
  if (Test-Path (Join-Path $Stage ".git")) { $fail.Add("FORBIDDEN .git") }
  $runsDetect = Join-Path $Stage "runs\detect"
  if (Test-Path -LiteralPath $runsDetect) {
    $runsBytes = (Get-ChildItem -LiteralPath $runsDetect -Recurse -File -EA SilentlyContinue | Measure-Object Length -Sum).Sum
    if ($null -eq $runsBytes) { $runsBytes = 0 }
    if ($runsBytes -gt 50MB) { $fail.Add("FORBIDDEN runs/detect >50 MB") }
  }
  $samHits = @(Get-ChildItem -LiteralPath (Join-Path $Stage "assets\models") -Recurse -File -Filter "*sam*.pt" -EA SilentlyContinue)
  if (-not $NoDetectWeights -and ($samHits.Count -ne 1 -or $samHits[0].Name -ne "sam3.pt")) {
    $fail.Add("FORBIDDEN SAM duplicates: $($samHits.Name -join ',')")
  }
  $archive = Join-Path $Stage "archive"
  if (Test-Path -LiteralPath $archive) {
    $archiveMedia = @(Get-ChildItem -LiteralPath $archive -Recurse -File -EA SilentlyContinue |
      Where-Object { $_.Extension -match '^\.(mp4|mov|avi|mkv|jpg|jpeg|png|webp|ply|obj)$' })
    if ($archiveMedia.Count -gt 0) { $fail.Add("FORBIDDEN archive media: $($archiveMedia[0].Name)") }
  }
  $parts = Get-ChildItem $Stage -Recurse -File -EA SilentlyContinue | Where-Object { $_.Name -match '\.(part|tmp)$' }
  if ($parts) { $fail.Add("FORBIDDEN *.part/*.tmp: $($parts.Name -join ',')") }

  if ($missing.Count -gt 0 -or $fail.Count -gt 0) {
    $msg = "INVENTORY FAIL kit=$Kit`n missing: $($missing -join '; ')`n fail: $($fail -join '; ')"
    throw $msg
  }
  Write-Host "Assert-PackInventory OK ($Kit)" -ForegroundColor Green
}

function Assert-LauncherLineEndings([string]$Root) {
  $bat = Join-Path $Root "Запустить.bat"
  $sh  = Join-Path $Root "Запустить.sh"
  if (Test-Path -LiteralPath $bat) {
    $bytes = [System.IO.File]::ReadAllBytes($bat)
    $hasCrlf = $false
    for ($i = 0; $i -lt ($bytes.Length - 1); $i++) {
      if ($bytes[$i] -eq 0x0D -and $bytes[$i+1] -eq 0x0A) { $hasCrlf = $true; break }
    }
    if (-not $hasCrlf) { throw "Запустить.bat must have CRLF line endings" }
    Write-Host "Assert-LauncherLineEndings: Запустить.bat CRLF OK" -ForegroundColor Green
  }
  if (Test-Path -LiteralPath $sh) {
    $bytes = [System.IO.File]::ReadAllBytes($sh)
    $hasCr = $false
    for ($i = 0; $i -lt ($bytes.Length - 1); $i++) {
      if ($bytes[$i] -eq 0x0D -and $bytes[$i+1] -ne 0x0A) { $hasCr = $true; break }
      if ($bytes[$i] -eq 0x0D) { $hasCr = $true; break }
    }
    if ($hasCr) { throw "Запустить.sh must have LF-only line endings (found CR)" }
    Write-Host "Assert-LauncherLineEndings: Запустить.sh LF OK" -ForegroundColor Green
  }
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

# Profile → torch CUDA yes/no (Mini/Lite always CPU). See scripts/portable_torch_policy.py
$TorchPolicyScript = Join-Path $PSScriptRoot "portable_torch_policy.py"
$WantCudaTorch = $false
if ($FullKit -and $TorchFlavor -eq "cuda") { $WantCudaTorch = $true }
$TorchKitName = if ($FullKit) { "fullkit" } elseif ($Mini -or $NoDetectWeights) { "mini" } else { "lite" }

function Get-TorchPolicyJson {
  param([string]$Kit, [string]$Flavor = "cuda", [string]$ListWheels = "")
  $pyArgs = @($TorchPolicyScript, "--kit", $Kit, "--flavor", $Flavor, "--json")
  if ($ListWheels) { $pyArgs += @("--list-wheels", $ListWheels) }
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $raw = & $HostPy @pyArgs 2>&1 | Out-String
  $ErrorActionPreference = $prevEap
  if (-not $raw) { throw "portable_torch_policy.py produced no output" }
  # Pretty-printed JSON spans lines — extract from first { to last }
  $start = $raw.IndexOf("{")
  $end = $raw.LastIndexOf("}")
  if ($start -lt 0 -or $end -le $start) { throw "failed to parse torch policy JSON: $raw" }
  $jsonText = $raw.Substring($start, $end - $start + 1)
  return ($jsonText | ConvertFrom-Json)
}

function New-FilteredWheelFindLinks {
  <#
    Build a temp find-links dir that EXCLUDES the wrong torch variant.
    Non-torch wheels are linked as-is. Keeps both variants in the real cache.
  #>
  param(
    [string]$WheelDir,
    [bool]$WantCuda,
    [string]$Stamp
  )
  $names = @(Get-ChildItem -LiteralPath $WheelDir -File | ForEach-Object { $_.Name })
  $list = ($names -join ",")
  $pol = Get-TorchPolicyJson -Kit $TorchKitName -Flavor $(if ($WantCuda) { "cuda" } else { "cpu" }) -ListWheels $list
  $rejected = @{}
  if ($pol.rejected) {
    foreach ($r in @($pol.rejected)) { $rejected[$r] = $true }
  }
  $out = Join-Path $env:TEMP "muravei_wheels_${TorchKitName}_$Stamp"
  if (Test-Path -LiteralPath $out) { Remove-Item -LiteralPath $out -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $out | Out-Null
  $linked = 0
  foreach ($f in (Get-ChildItem -LiteralPath $WheelDir -File)) {
    if ($rejected.ContainsKey($f.Name)) {
      Write-Host "  skip wrong-variant wheel: $($f.Name)" -ForegroundColor DarkYellow
      continue
    }
    $dest = Join-Path $out $f.Name
    # Hardlink when possible (same volume); else copy
    try {
      New-Item -ItemType HardLink -Path $dest -Value $f.FullName -ErrorAction Stop | Out-Null
    } catch {
      Copy-Item -LiteralPath $f.FullName -Destination $dest -Force
    }
    $linked++
  }
  $selCount = 0
  if ($pol.selected) { $selCount = @($pol.selected).Count }
  Write-Host "Filtered find-links: $linked files (torch matches=$selCount, excluded=$($rejected.Count)) → $out" -ForegroundColor Yellow
  return @{
    Path = $out
    SelectedTorch = $selCount
    CacheMismatch = [bool]$pol.cache_mismatch
    IndexUrl = [string]$pol.index_url
  }
}

function Install-ProfileTorch {
  <#
    Force torch+torchvision to the kit profile after requirements bake / host mirror.
    Mini/Lite: CPU (+ onnxruntime CPU/DirectML). FullKit cuda: cu128. Never pick opposite from cache.
  #>
  param(
    [string]$PyExe,
    [string]$HostPyExe,
    [bool]$WantCuda,
    [bool]$HasWheels,
    [string]$WheelDir,
    [string]$Stamp
  )
  $label = if ($WantCuda) { "CUDA cu128" } else { "CPU" }
  Write-Host "Forcing profile torch ($label) for kit=$TorchKitName ..." -ForegroundColor Yellow
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $HostPyExe -m pip --python $PyExe uninstall -y torch torchvision 2>&1 | Out-Host
  if (-not $WantCuda) {
    & $HostPyExe -m pip --python $PyExe uninstall -y onnxruntime-gpu 2>&1 | Out-Host
  }
  $ErrorActionPreference = $prevEap

  $torchArgs = $null
  $usedCache = $false
  if ($HasWheels) {
    $flt = New-FilteredWheelFindLinks -WheelDir $WheelDir -WantCuda $WantCuda -Stamp "$Stamp-torch"
    if ($flt.SelectedTorch -gt 0) {
      $torchArgs = @(
        "--python", $PyExe, "install", "--no-index", "--find-links", $flt.Path,
        "--force-reinstall", "--no-deps", "--no-warn-script-location",
        "torch", "torchvision"
      )
      $usedCache = $true
      Write-Host "Profile torch from filtered wheel cache ($($flt.SelectedTorch) matches)" -ForegroundColor Yellow
    } else {
      if ($WantCuda) {
        throw "CUDA FullKit requires pre-seeded torch*+cu128* wheels under portable/cache/wheels; network download is forbidden. Build CPU FullKit instead."
      }
      if ($Offline) { throw "BUILD FAIL (offline): CPU torch wheels missing from portable/cache/wheels" }
      Write-Host "WARNING: wheel cache has no $label torch — falling back to $($flt.IndexUrl) (never opposite variant)" -ForegroundColor Yellow
      $torchArgs = @(
        "--python", $PyExe, "install", "--force-reinstall", "--no-warn-script-location",
        "--no-cache-dir", "--index-url", $flt.IndexUrl, "torch", "torchvision"
      )
    }
  } else {
    if ($WantCuda) {
      throw "CUDA FullKit requires portable/cache/wheels with torch*+cu128*; network download is forbidden. Build CPU FullKit instead."
    }
    if ($Offline) { throw "BUILD FAIL (offline): portable/cache/wheels missing for CPU torch" }
    $idx = if ($WantCuda) { "https://download.pytorch.org/whl/cu128" } else { "https://download.pytorch.org/whl/cpu" }
    Write-Host "No wheel cache — installing torch from $idx" -ForegroundColor Yellow
    $torchArgs = @(
      "--python", $PyExe, "install", "--force-reinstall", "--no-warn-script-location",
      "--no-cache-dir", "--index-url", $idx, "torch", "torchvision"
    )
  }
  & $HostPyExe -m pip @torchArgs
  if ($LASTEXITCODE -ne 0) { throw "profile torch ($label) install failed" }

  if (-not $WantCuda) {
    # Prefer DirectML on Windows field kits; fall back to CPU ORT.
    # Use --no-deps so onnxruntime-directml cannot bump numpy to 2.x (requirements pin <2).
    $ortArgs = @("--python", $PyExe, "install", "--force-reinstall", "--no-deps", "--no-warn-script-location")
    if ($HasWheels) {
      $ortArgs += @("--no-index", "--find-links", $WheelDir, "onnxruntime-directml")
      & $HostPyExe -m pip @ortArgs
      if ($LASTEXITCODE -ne 0) {
        if ($Offline) { throw "BUILD FAIL (offline): onnxruntime-directml missing from wheel cache" }
        Write-Host "onnxruntime-directml not in cache — trying online / onnxruntime" -ForegroundColor Yellow
        & $HostPyExe -m pip --python $PyExe install --force-reinstall --no-deps --no-warn-script-location --no-cache-dir "onnxruntime-directml>=1.16.0"
        if ($LASTEXITCODE -ne 0) {
          & $HostPyExe -m pip --python $PyExe install --force-reinstall --no-deps --no-warn-script-location --no-cache-dir "onnxruntime>=1.16.0"
          if ($LASTEXITCODE -ne 0) { throw "onnxruntime (CPU/DirectML) install failed for CPU kit" }
        }
      }
    } else {
      if ($Offline) { throw "BUILD FAIL (offline): no wheel cache for onnxruntime-directml" }
      & $HostPyExe -m pip --python $PyExe install --force-reinstall --no-deps --no-warn-script-location --no-cache-dir "onnxruntime-directml>=1.16.0"
      if ($LASTEXITCODE -ne 0) {
        & $HostPyExe -m pip --python $PyExe install --force-reinstall --no-deps --no-warn-script-location --no-cache-dir "onnxruntime>=1.16.0"
        if ($LASTEXITCODE -ne 0) { throw "onnxruntime (CPU/DirectML) install failed for CPU kit" }
      }
    }
    # Re-assert numpy pin after ORT (cache may hold numpy 2.x as transitive)
    if ($HasWheels) {
      & $HostPyExe -m pip --python $PyExe install --force-reinstall --no-deps --no-warn-script-location --no-index --find-links $WheelDir "numpy>=1.26.0,<2" 2>&1 | Out-Host
    }
  }

  if ($WantCuda) {
    & $PyExe -c "import torch; assert torch.version.cuda is not None, 'expected CUDA torch (torch.version.cuda is not None)'; print('STAGE_TORCH', torch.__version__, 'cuda', torch.version.cuda)"
    if ($LASTEXITCODE -ne 0) { throw "POST-STAGE ASSERT FAILED: FullKit requires CUDA torch (torch.version.cuda is not None)" }
  } else {
    & $PyExe -c "import torch; assert torch.version.cuda is None, 'expected CPU torch (torch.version.cuda is None)'; print('STAGE_TORCH', torch.__version__, 'cpu', torch.version.cuda)"
    if ($LASTEXITCODE -ne 0) { throw "POST-STAGE ASSERT FAILED: Mini/Lite/CPU kit requires CPU torch (torch.version.cuda is None)" }
  }
  Write-Host "Torch profile assert OK ($label)" -ForegroundColor Green
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
# Copy UI dist only (never env-pack ZIPs / _env_pack_stage pollution)
$distSrc = Join-Path $Repo "dist"
$distDst = Join-Path $Stage "dist"
New-Item -ItemType Directory -Force -Path $distDst | Out-Null
Get-ChildItem -LiteralPath $distSrc -Force -ErrorAction SilentlyContinue |
  Where-Object {
    $n = $_.Name.ToLowerInvariant()
    ($n -ne "_env_pack_stage") -and ($n -notlike "muravei_env_pack*") -and ($n -notlike "_unittest*") -and ($n -notlike "_make_*")
  } |
  ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $distDst $_.Name) -Recurse -Force
  }
Remove-Pycache (Join-Path $Stage "backend")

foreach ($rel in @(
  "archive", "archive\crops", "archive\recordings", "archive\captures",
  "cache", "logs", "reports", "assets\models", "assets\ffmpeg",
  "runs\detect\train\weights"
)) {
  New-Item -ItemType Directory -Force -Path (Join-Path $Stage $rel) | Out-Null
}

Write-Host "Copy tactical detect weights + sam3.pt (copy-only, no downloads)..."
$destA = Join-Path $Stage "assets\models"
New-Item -ItemType Directory -Force -Path $destA | Out-Null
if ($NoDetectWeights) {
  Write-Host "  -NoDetectWeights: skip .pt / sam3 (debug empty models)" -ForegroundColor Yellow
} else {
  $weightSources = @(
    (Join-Path $Repo "assets\models"),
    (Join-Path $Repo "runs\detect\train\weights")
  )
  foreach ($srcDir in $weightSources) {
    if (-not (Test-Path -LiteralPath $srcDir)) { continue }
    Get-ChildItem -LiteralPath $srcDir -File -Filter "yolo26*.pt" -ErrorAction SilentlyContinue |
      Where-Object {
        $n = $_.Name.ToLowerInvariant()
        ($n -notmatch "seg") -and ($n -notmatch "yoloe") -and ($_.Length -gt 1024)
      } |
      ForEach-Object {
        $dest = Join-Path $destA $_.Name
        if (Test-Path -LiteralPath $dest) { return }
        Write-Host ("  {0} → assets/models ({1:N1} MB)" -f $_.Name, ($_.Length / 1MB))
        Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
      }
  }
  $samSrc = Join-Path $Repo "assets\models\sam3.pt"
  $samDst = Join-Path $destA "sam3.pt"
  if (Test-Path -LiteralPath $samSrc) {
    Copy-Item -LiteralPath $samSrc -Destination $samDst -Force
    Write-Host ("  sam3.pt → assets/models ({0:N1} MB)" -f ((Get-Item $samSrc).Length / 1MB))
  } else {
    throw "BUILD FAIL: assets/models/sam3.pt missing — required in both packs (C3)"
  }
  $yoloHits = @(Get-ChildItem -LiteralPath $destA -File -Filter "yolo26*.pt" -EA SilentlyContinue |
    Where-Object { $_.Name -notmatch "seg" -and $_.Length -gt 1024 })
  if ($yoloHits.Count -lt 1) {
    throw "BUILD FAIL: no tactical yolo26*.pt under assets/models after copy"
  }

  # UAV custom architecture YAML configs (needed for use_uav_arch/use_uav_ghost_arch training)
  foreach ($yamlName in @("yolo26n-uav.yaml", "yolo26n-uav-ghost.yaml")) {
    $yamlSrc = Join-Path $Repo "assets\models\$yamlName"
    if (Test-Path -LiteralPath $yamlSrc) {
      Copy-Item -LiteralPath $yamlSrc -Destination (Join-Path $destA $yamlName) -Force
      Write-Host ("  {0} → assets/models (UAV architecture config)" -f $yamlName)
    } else {
      Write-Host "  WARNING: $yamlName not found — UAV training will fail in this pack" -ForegroundColor Yellow
    }
  }
}

if (Test-Path (Join-Path $Repo "military_classes.yaml")) {
  Copy-Item (Join-Path $Repo "military_classes.yaml") $Stage -Force
}

# Smoke sample (CC0 synthetic) for portable functional smoke
$smokeSrc = Join-Path $Repo "assets\smoke_sample"
if (Test-Path -LiteralPath $smokeSrc) {
  $smokeDst = Join-Path $Stage "assets\smoke_sample"
  New-Item -ItemType Directory -Force -Path $smokeDst | Out-Null
  Copy-Item -LiteralPath (Join-Path $smokeSrc "*") -Destination $smokeDst -Force
  Write-Host "  assets/smoke_sample copied"
}


Copy-Item (Join-Path $Repo "Запустить.bat") $Stage -Force
$shLaunch = Join-Path $Repo "Запустить.sh"
if (Test-Path -LiteralPath $shLaunch) { Copy-Item $shLaunch $Stage -Force }
Copy-Item (Join-Path $Repo "README.md") $Stage -Force
# Stamp VERSION at pack root (single source for banner + /api/health)
Set-Content -LiteralPath (Join-Path $Stage "VERSION") -Value $AppVersion -Encoding ascii -NoNewline
Set-Content -LiteralPath (Join-Path $Repo "VERSION") -Value $AppVersion -Encoding ascii -NoNewline
Set-Content -LiteralPath (Join-Path $Stage "KIT") -Value $KitMarker -Encoding ascii -NoNewline
Write-Host "KIT marker: $KitMarker"


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
  $pyExe = Join-Path $PyHome "python.exe"
  if ($Offline) {
    # The embedded distribution has no pip. Seed it from the mandated 3.12 host
    # environment instead of asking get-pip to resolve anything from the network.
    $hostSite = Join-Path $Repo "muravei_env\Lib\site-packages"
    $targetSite = Join-Path $PyHome "Lib\site-packages"
    $hostPipPkg = Join-Path $hostSite "pip"
    if (-not (Test-Path -LiteralPath $hostPipPkg)) { throw "BUILD FAIL (offline): host pip package missing" }
    New-Item -ItemType Directory -Force -Path $targetSite | Out-Null
    Copy-Item -LiteralPath $hostPipPkg -Destination (Join-Path $targetSite "pip") -Recurse -Force
    Get-ChildItem -LiteralPath $hostSite -Directory -Filter "pip-*.dist-info" -ErrorAction SilentlyContinue |
      ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $targetSite $_.Name) -Recurse -Force }
    & $pyExe -m pip --version
    if ($LASTEXITCODE -ne 0) { throw "BUILD FAIL (offline): seeded embedded pip did not start" }
    Write-Host "Offline build: seeded embedded pip from muravei_env (no get-pip/network)." -ForegroundColor Yellow
  } else {
    if (-not (Test-Path -LiteralPath $getPip)) {
      Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
    }
    & $pyExe $getPip --no-warn-script-location
    if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }
  }

  # Do NOT copy python.exe into Scripts\ — without python*._pth beside it, Windows
  # resolves sys.prefix to the host/system install (same binary, wrong site-packages).
  # Запустить.bat prefers muravei_env\python.exe (embed root). Remove any stale copy.
  $scriptsPy = Join-Path $PyHome "Scripts\python.exe"
  if (Test-Path -LiteralPath $scriptsPy) {
    Remove-Item -LiteralPath $scriptsPy -Force -ErrorAction SilentlyContinue
    Write-Host "Removed Scripts\python.exe (embed must use root python.exe + ._pth)" -ForegroundColor Yellow
  }
  $scriptsPyw = Join-Path $PyHome "Scripts\pythonw.exe"
  if (Test-Path -LiteralPath $scriptsPyw) {
    Remove-Item -LiteralPath $scriptsPyw -Force -ErrorAction SilentlyContinue
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
  if ($Offline) {
    Write-Host "Offline build: skip pip/setuptools/wheel upgrade (network prohibited)." -ForegroundColor Yellow
  } else {
    & $HostPy -m pip --python $pyExe install --upgrade pip setuptools wheel --no-warn-script-location
    $bakeEc = $LASTEXITCODE
    if ($bakeEc -ne 0) { throw "pip upgrade failed" }
  }
  Ensure-PipCaBundle $PyHome
  $reqFile = Join-Path $Repo "backend\requirements.txt"
  $wheelDir = Join-Path $CacheDir "wheels"
  $hasWheels = (Test-Path -LiteralPath $wheelDir) -and (
    $null -ne (Get-ChildItem -LiteralPath $wheelDir -File -ErrorAction SilentlyContinue | Select-Object -First 1)
  )
  if (($Mini -or $NoDetectWeights) -and ($env:MURAVEI_PORTABLE_MIRROR -eq "1")) {
    Write-Host "WARNING: MURAVEI_PORTABLE_MIRROR=1 with Mini — host CUDA may be mirrored; profile torch force will reinstall CPU" -ForegroundColor Yellow
  }
  $bakeFindLinks = $wheelDir
  if ($hasWheels) {
    # Exclude opposite torch variant from find-links so pip never picks CUDA for Mini
    $fltBake = New-FilteredWheelFindLinks -WheelDir $wheelDir -WantCuda $WantCudaTorch -Stamp "$Stamp-bake"
    $bakeFindLinks = $fltBake.Path
    Write-Host "Using filtered local wheel cache: $bakeFindLinks" -ForegroundColor Yellow
    $bakeArgs = @("--python", $pyExe, "install", "--no-index", "--find-links", $bakeFindLinks, "--prefer-binary", "--no-warn-script-location", "-r", $reqFile)
  } else {
    if ($Offline) { throw "BUILD FAIL (offline): portable/cache/wheels is empty" }
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

  # Profile-driven torch: Mini/Lite always CPU; FullKit follows -TorchFlavor.
  # Runs after bake AND after host mirror (so MURAVEI_PORTABLE_MIRROR cannot ship CUDA into Mini).
  Install-ProfileTorch -PyExe $pyExe -HostPyExe $HostPy -WantCuda $WantCudaTorch `
    -HasWheels $hasWheels -WheelDir $wheelDir -Stamp $Stamp

  & $pyExe -c "import sys,fastapi,uvicorn,ultralytics,cv2,jwt; assert sys.version.startswith('3.12'); print('BAKE_OK', sys.version.split()[0], fastapi.__version__)"
  if ($LASTEXITCODE -ne 0) { throw "BAKE import failed" }
  & $pyExe -c "import importlib.metadata as m, onnxruntime as ort; print('ONNX', m.version('onnx'), 'ONNXSLIM', m.version('onnxslim')); print('ORT', ort.get_available_providers()); import onnx, onnxslim"
  if ($LASTEXITCODE -ne 0) { throw "BAKE onnx/onnxslim/ort assert failed" }
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

# --- FullKit: 3D sidecars (Ollama NOT bundled — system-optional) ---
if ($FullKit) {
  Write-Host "FullKit: Ollama runtime NOT bundled (install separately)." -ForegroundColor Cyan
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

  # DA3 neural dense weights (optional FullKit-only; Mini never)
  if ($NoDA3) {
    Write-Host "  DA3 sidecar skipped (-NoDA3)"
  } else {
    $da3Src = Join-Path $Repo "sidecars\da3"
    $da3HasWeights = $false
    if (Test-Path -LiteralPath $da3Src) {
      $da3HasWeights = @(Get-ChildItem -LiteralPath $da3Src -File -EA SilentlyContinue |
        Where-Object { $_.Extension -match '\.(safetensors|pt)$' }).Count -gt 0
    }
    if ($da3HasWeights) {
      $da3Dest = Join-Path $sidecarDest "da3"
      New-Item -ItemType Directory -Force -Path $da3Dest | Out-Null
      # Copy only root files (weights + NOTICE + config_*.json). Skip HF staging dirs (base/large/…).
      Get-ChildItem -LiteralPath $da3Src -File -EA SilentlyContinue | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $da3Dest $_.Name) -Force
      }
      Write-Host "  sidecars\da3 copied (FullKit optional DA3 weights + NOTICE; no HF staging dirs)"
    } else {
      Write-Host "  DA3 sidecar skipped (no weights under sidecars\da3 — stage via fetch_da3_weights.py)"
    }
  }
}

$kitLabel = if ($FullKit) { "Full Field Kit" } elseif ($Mini -or $KitMarker -eq "mini") { "Mini (tactical YOLO + SAM3)" } else { "Portable Lite" }
$modelsLine = if ($NoDetectWeights) {
  "assets\models\        (empty — debug NoDetectWeights)"
} else {
  "assets\models\        (tactical yolo26*.pt + sam3.pt exactly once)"
}
$sidecarLine = if ($FullKit) {
  "sidecars\colmap\      (COLMAP)`nsidecars\gsplat_examples\  (trainer)`nsidecars\da3\         (optional Dense weights)`nsidecars\alicevision\  (optional Mesh)`nPORTABLE_README.md`n(Ollama не в комплекте — поставьте отдельно)"
} else {
  "README.md`n(Ollama не в комплекте — поставьте отдельно)"
}
$note = @"
MuraveiVision PRO v$AppVersion — $kitLabel
=================================
Запустить.bat
VERSION               ($AppVersion)
muravei_env\          (embeddable Python 3.12.10 + packages$(if ($FullKit) { if ($TorchFlavor -eq 'cuda') { ' + torch cu128' } else { ' + torch CPU / DirectML' } }))
dist\                 (UI + CSP)
backend\              (FastAPI)
$modelsLine
runs\detect\train\weights\  (stub dirs only)
archive\ crops\ recordings\ captures\  (empty)
military_classes.yaml
$sidecarLine

PIN: operator 1234567 / engineer 0000000 / master 0987907

Python: ONLY muravei_env (3.12) — never system 3.14.
CPU Intel/AMD amd64 OK; NVIDIA recommended for realtime YOLO/VLM.
Offline map tiles (assets/map_tiles) are NOT in this ZIP — ship separately if needed.
Ollama не в комплекте: поставьте отдельно; air-gap — installer + blob в OLLAMA_MODELS.
Бинарные паки не публикуются на GitHub — внутренний офлайн-канал.
"@
Set-Content -LiteralPath (Join-Path $Stage "PORTABLE.txt") -Value $note -Encoding UTF8


# --- Hygiene asserts before zip (fail loud) ---
function Assert-SlimStageHygiene {
  $ollamaDir = Join-Path $Stage "ollama"
  if (Test-Path -LiteralPath $ollamaDir) {
    throw "HYGIENE: ollama/ dir present in stage — Ollama must not be bundled"
  }
  $modelsDir = Join-Path $Stage "assets\models"
  $samHits = @(Get-ChildItem $modelsDir -File -Filter "*sam*" -EA SilentlyContinue)
  if (-not $NoDetectWeights) {
    $sam3 = Join-Path $modelsDir "sam3.pt"
    if (-not (Test-Path -LiteralPath $sam3)) { throw "HYGIENE: sam3.pt missing under assets/models" }
    $extraSam = @($samHits | Where-Object { $_.Name -ne "sam3.pt" })
    if ($extraSam.Count -gt 0) { throw "HYGIENE: extra sam* in assets/models: $($extraSam.Name -join ', ')" }
    if ($samHits.Count -ne 1) { throw "HYGIENE: expected exactly one sam* (sam3.pt), found $($samHits.Count)" }
    $yoloHits = @(Get-ChildItem $modelsDir -File -Filter "yolo26*.pt" -EA SilentlyContinue |
      Where-Object { $_.Name -notmatch "seg" -and $_.Length -gt 1024 })
    if ($yoloHits.Count -lt 1) { throw "HYGIENE: no tactical yolo26*.pt in assets/models" }
  } else {
    if ($samHits) { throw "HYGIENE: NoDetectWeights but sam* present: $($samHits.Name -join ', ')" }
  }
  $runsDir = Join-Path $Stage "runs\detect"
  if (Test-Path $runsDir) {
    $rBytes = (Get-ChildItem $runsDir -Recurse -File -EA SilentlyContinue | Measure-Object Length -Sum).Sum
    if ($null -eq $rBytes) { $rBytes = 0 }
    if ($rBytes -gt 50MB) { throw "HYGIENE: runs/detect too large ($([math]::Round($rBytes/1MB,1)) MB > 50 MB)" }
    $runSam = Get-ChildItem $runsDir -Recurse -File -Filter "*sam*" -EA SilentlyContinue
    if ($runSam) { throw "HYGIENE: sam* under runs/detect: $($runSam.Name -join ', ')" }
  }
  $rootSam = Get-ChildItem $Stage -File -Filter "*sam*" -EA SilentlyContinue
  if ($rootSam) { throw "HYGIENE: sam* at stage root: $($rootSam.Name -join ', ')" }
  $archDir = Join-Path $Stage "archive"
  if (Test-Path $archDir) {
    $media = Get-ChildItem $archDir -Recurse -File -EA SilentlyContinue |
      Where-Object { $_.Extension -match '\.(mp4|mov|avi|mkv|jpg|jpeg|png|ply|obj)$' }
    if ($media) { throw "HYGIENE: archive has media files: $($media.FullName | Select-Object -First 5)" }
  }
  $rootClip = Join-Path $Stage "mobileclip2_b.ts"
  if (Test-Path $rootClip) { throw "HYGIENE: root mobileclip duplicate — keep only under assets/models" }
  $packJunk = Get-ChildItem (Join-Path $Stage "dist") -Force -EA SilentlyContinue |
    Where-Object { $_.Name -like "muravei_env_pack*" -or $_.Name -eq "_env_pack_stage" }
  if ($packJunk) { throw "HYGIENE: dist contains env-pack junk: $($packJunk.Name -join ', ')" }
  $verPath = Join-Path $Stage "VERSION"
  if (-not (Test-Path -LiteralPath $verPath)) { throw "HYGIENE: VERSION file missing at pack root" }
  $verText = (Get-Content -LiteralPath $verPath -Raw -ErrorAction SilentlyContinue).Trim()
  if (-not $verText -or $verText -eq "unknown") { throw "HYGIENE: VERSION empty/unknown — refuse to ship" }
  $kitPath = Join-Path $Stage "KIT"
  if (-not (Test-Path -LiteralPath $kitPath)) { throw "HYGIENE: KIT marker missing at pack root" }
  $kitText = (Get-Content -LiteralPath $kitPath -Raw -ErrorAction SilentlyContinue).Trim().ToLowerInvariant()
  if ($kitText -notin @("mini", "full")) { throw "HYGIENE: KIT must be mini|full, got '$kitText'" }
  Write-Host "Hygiene asserts OK (VERSION=$verText KIT=$kitText)" -ForegroundColor Green
}
Write-Host "Ensure pack-local ffmpeg/ffprobe..."
Ensure-PackFfmpeg
Assert-PackInventory -Kit $KitMarker
Assert-LauncherLineEndings -Root $Stage
Assert-SlimStageHygiene

if ($CudaFlavorPending) {
  Set-Content -LiteralPath (Join-Path $Stage "CUDA_FLAVOR_PENDING.txt") -Encoding UTF8 -Value "CUDA FullKit was not built: seed matching torch*+cu128* and torchvision*+cu128* wheels in portable/cache/wheels, then rebuild. No network probe/download was attempted."
}

if (-not $SkipZip) {
  Write-Host "Creating ZIP (Zip64/Fastest)..." -ForegroundColor Yellow
  Write-Zip64 -SourceDir $Stage -DestZip $ZipPath
  $zipBytes = (Get-Item $ZipPath).Length
  $zipGb = [math]::Round($zipBytes / 1GB, 2)
  $zipMb = [math]::Round($zipBytes / 1MB, 1)
  Write-Host "ZIP: $ZipPath ($zipGb GB / $zipMb MB)" -ForegroundColor Green
  if ($FullKit) {
    $da3Stage = Join-Path $Stage "sidecars\da3"
    $da3WeightCount = 0
    if (Test-Path -LiteralPath $da3Stage) {
      $da3WeightCount = @(Get-ChildItem -LiteralPath $da3Stage -File -EA SilentlyContinue |
        Where-Object { $_.Extension -match '\.(safetensors|pt)$' }).Count
    }
    if ($da3WeightCount -gt 0) {
      # DA3 all-variants (base+large+metric+giant) ≈ +8.5 GB compressed poorly → higher band
      if ($zipGb -gt 22) { throw "FULLKIT+DA3 SIZE ASSERT FAILED: ZIP is $zipGb GB (>22). Reject." }
      if ($zipGb -gt 18) { Write-Host "WARNING: FullKit+DA3 ZIP is $zipGb GB (band ~12–18 GB with all DA3 variants)" -ForegroundColor Yellow }
    } else {
      if ($zipGb -gt 10) { throw "FULLKIT SIZE ASSERT FAILED: ZIP is $zipGb GB (>10). Reject." }
      if ($zipGb -gt 9.5) { Write-Host "WARNING: FullKit ZIP is $zipGb GB (band ~7.5–9 GB)" -ForegroundColor Yellow }
    }
  } elseif ($Mini -or $KitMarker -eq "mini") {
    if ($zipGb -gt 5) { throw "MINI SIZE ASSERT FAILED: ZIP is $zipGb GB (>5). Reject." }
    if ($zipGb -gt 4.5) { Write-Host "WARNING: Mini ZIP is $zipGb GB (band ~3.5–4.5 GB)" -ForegroundColor Yellow }
  }
}

Write-Host "Staged: $Stage" -ForegroundColor Green
Write-Host "Done."
