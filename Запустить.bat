@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
echo ============================================
echo   MuraveiVision PRO v3.0
echo   Starting...
echo ============================================
echo.

REM --- Optional bundled Ollama (Full Field Kit) ---
if exist "%~dp0ollama\ollama.exe" (
    set "OLLAMA_MODELS=%~dp0ollama\models"
    set "OLLAMA_HOST=127.0.0.1:11434"
    echo Starting Ollama in background...
    echo   OLLAMA_MODELS=!OLLAMA_MODELS!
    start "Ollama" /B "%~dp0ollama\ollama.exe" serve
    timeout /t 3 /nobreak >nul
) else (
    echo Ollama not in kit ^(Lite/Mini^). AI analysis needs a system Ollama if available.
)

REM --- Ensure muravei_env (field: unpack muravei_env_pack.zip then setup_env) ---
if not exist "%~dp0muravei_env\Scripts\python.exe" (
    if exist "%~dp0scripts\setup_env.bat" (
        echo muravei_env не найден — запускаю scripts\setup_env.bat ...
        call "%~dp0scripts\setup_env.bat"
        if errorlevel 1 (
            echo [ОШИБКА] Не удалось подготовить muravei_env.
            echo Распакуйте dist\muravei_env_pack.zip в корень проекта и снова Запустить.bat
            echo Либо при наличии интернета: scripts\setup_env.bat поставит пакеты с PyPI.
            echo Подробнее: docs\DEPLOY_GUIDE.md
            pause
            exit /b 1
        )
    )
)

set "PYTHON="
if exist "%~dp0muravei_env\Scripts\python.exe" set "PYTHON=%~dp0muravei_env\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0muravei_env\python.exe" set "PYTHON=%~dp0muravei_env\python.exe"
if not defined PYTHON if exist "%~dp0runtime\python\python.exe" set "PYTHON=%~dp0runtime\python\python.exe"

if not defined PYTHON (
    echo [ОШИБКА] Python не найден.
    echo Ожидается muravei_env\Scripts\python.exe ^(3.12.x^).
    echo Поле:  распакуйте muravei_env_pack.zip → scripts\setup_env.bat
    echo Portable: scripts\build_portable.ps1 -FetchEmbeddablePython
    pause
    exit /b 1
)

if not exist "%~dp0dist\index.html" (
    echo [WARN] dist\index.html missing - UI may not open.
)

echo Python: !PYTHON!
set "MURAVEI_SESSION_TRACE=1"
set "COLMAP_ROOT="
if exist "%~dp0sidecars\colmap\COLMAP.bat" set "COLMAP_ROOT=%~dp0sidecars\colmap"
if not defined COLMAP_ROOT if exist "%~dp0sidecars\colmap\colmap.exe" set "COLMAP_ROOT=%~dp0sidecars\colmap"
if not defined COLMAP_ROOT if exist "%~dp0sidecars\colmap\bin\colmap.exe" set "COLMAP_ROOT=%~dp0sidecars\colmap"
if defined COLMAP_ROOT (
    echo COLMAP_ROOT=!COLMAP_ROOT!
) else (
    echo COLMAP sidecar not in kit - 3D recon needs sidecars\colmap ^(FullKit^).
)
set "ALICEVISION_ROOT="
if exist "%~dp0sidecars\alicevision\windows-x64\bin\aliceVision_featureExtraction.exe" set "ALICEVISION_ROOT=%~dp0sidecars\alicevision\windows-x64"
if defined ALICEVISION_ROOT (
    echo ALICEVISION_ROOT=!ALICEVISION_ROOT!
) else (
    echo AliceVision sidecar not in kit - Dense/Mesh presets will stay disabled.
)
echo Starting backend on http://127.0.0.1:8000 ...
start "MuraveiVision Backend" cmd /c "set COLMAP_ROOT=!COLMAP_ROOT!&& set ALICEVISION_ROOT=!ALICEVISION_ROOT!&& set MURAVEI_SESSION_TRACE=1&& \"!PYTHON!\" -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000"

echo Waiting for backend...
timeout /t 4 /nobreak >nul

"!PYTHON!" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)" 2>nul
if errorlevel 1 (
    echo [ERROR] Backend failed to start. Check logs and port 8000.
    pause
    exit /b 1
)

echo Backend ready. Opening UI...
start "" "http://127.0.0.1:8000"
echo.
echo System started.
echo Close the "MuraveiVision Backend" window to stop the API.
if exist "%~dp0ollama\ollama.exe" echo Ollama runs in background - end ollama.exe if needed.
pause
