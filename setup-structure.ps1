# setup-structure.ps1 — ИСПРАВЛЕННАЯ ВЕРСИЯ
$ErrorActionPreference = "Stop"

Write-Host "=== НАСТРОЙКА СТРУКТУРЫ MURAVEIVISION PRO (v2) ===" -ForegroundColor Cyan

$rootPath = "D:\LLM\MuraveiVision-PRO"
$openreelPath = "$rootPath\openreel-reference"

if (-not (Test-Path $openreelPath)) {
    Write-Host "❌ ОШИБКА: openreel-reference не найден!" -ForegroundColor Red
    exit 1
}

# Функция копирования с ПРАВИЛЬНЫМИ путями
function Copy-OpenReelFile {
    param(
        [string]$RelativePath,
        [string]$Destination,
        [string]$Description
    )
    
    $source = Join-Path $openreelPath $RelativePath
    
    if (Test-Path $source) {
        # Создаём папку назначения, если её нет
        $destDir = Split-Path $Destination -Parent
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        
        Copy-Item -Path $source -Destination $Destination -Force
        Write-Host "  ✅ $Description" -ForegroundColor Green
        return $true
    } else {
        Write-Host "  ⚠️  НЕ НАЙДЕН: $RelativePath" -ForegroundColor Yellow
        return $false
    }
}

Write-Host "`n📋 Копирование файлов из openreel-reference..." -ForegroundColor Yellow

# === TIMELINE CORE ===
Write-Host "`n   🧩 Timeline Core:" -ForegroundColor Cyan

Copy-OpenReelFile `
    -RelativePath "packages\core\src\timeline\clip-manager.ts" `
    -Destination "$rootPath\src\core\timeline\clip-manager.ts" `
    -Description "clip-manager.ts → src\core\timeline\"

Copy-OpenReelFile `
    -RelativePath "packages\core\src\timeline\track-manager.ts" `
    -Destination "$rootPath\src\core\timeline\track-manager.ts" `
    -Description "track-manager.ts → src\core\timeline\"

Copy-OpenReelFile `
    -RelativePath "packages\core\src\timeline\nested-sequence-engine.ts" `
    -Destination "$rootPath\src\core\timeline\nested-sequence-engine.ts" `
    -Description "nested-sequence-engine.ts → src\core\timeline\"

# === PLAYBACK ===
Write-Host "`n   🎬 Playback:" -ForegroundColor Cyan

Copy-OpenReelFile `
    -RelativePath "packages\core\src\playback\master-timeline-clock.ts" `
    -Destination "$rootPath\src\core\playback\master-timeline-clock.ts" `
    -Description "master-timeline-clock.ts → src\core\playback\"

# === TYPES ===
Write-Host "`n   📐 Types:" -ForegroundColor Cyan

Copy-OpenReelFile `
    -RelativePath "packages\core\src\types\timeline.ts" `
    -Destination "$rootPath\src\core\types\timeline.ts" `
    -Description "timeline.ts → src\core\types\"

# === STORES ===
Write-Host "`n   🗄️  Stores:" -ForegroundColor Cyan

Copy-OpenReelFile `
    -RelativePath "apps\web\src\stores\timeline-store.ts" `
    -Destination "$rootPath\src\store\timeline-store.ts" `
    -Description "timeline-store.ts → src\store\"

# === UTILS ===
Write-Host "`n   🔧 Utils:" -ForegroundColor Cyan

Copy-OpenReelFile `
    -RelativePath "apps\web\src\utils\timeline-item-actions.ts" `
    -Destination "$rootPath\src\utils\timeline-item-actions.ts" `
    -Description "timeline-item-actions.ts → src\utils\"

# === COMPONENTS ===
Write-Host "`n   🧱 Components:" -ForegroundColor Cyan

Copy-OpenReelFile `
    -RelativePath "apps\web\src\components\editor\Timeline.tsx" `
    -Destination "$rootPath\src\components\editor\Timeline.tsx" `
    -Description "Timeline.tsx → src\components\editor\"

# === ДОПОЛНИТЕЛЬНЫЕ ВАЖНЫЕ ФАЙЛЫ ===
Write-Host "`n   📦 Дополнительно (рекомендую):" -ForegroundColor Cyan

Copy-OpenReelFile `
    -RelativePath "packages\core\src\playback\playback-controller.ts" `
    -Destination "$rootPath\src\core\playback\playback-controller.ts" `
    -Description "playback-controller.ts → src\core\playback\"

Copy-OpenReelFile `
    -RelativePath "packages\core\src\video\playback-engine.ts" `
    -Destination "$rootPath\src\core\video\playback-engine.ts" `
    -Description "playback-engine.ts → src\core\video\"

Write-Host "`n=== НАСТРОЙКА ЗАВЕРШЕНА ===" -ForegroundColor Cyan