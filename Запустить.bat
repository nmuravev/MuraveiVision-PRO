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
    echo Ollama not in kit ^(Lite^). AI analysis needs a system Ollama if available.
)

set "PYTHON="
if exist "%~dp0muravei_env\Scripts\python.exe" set "PYTHON=%~dp0muravei_env\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0muravei_env\python.exe" set "PYTHON=%~dp0muravei_env\python.exe"
if not defined PYTHON if exist "%~dp0runtime\python\python.exe" set "PYTHON=%~dp0runtime\python\python.exe"

if not defined PYTHON (
    echo [ERROR] Python not found.
    echo Expected muravei_env\Scripts\python.exe ^(embed 3.12.10^).
    echo Build kit: scripts\build_portable.ps1 -FetchEmbeddablePython
    echo Full Kit: scripts\build_portable.ps1 -FetchEmbeddablePython -FullKit
    pause
    exit /b 1
)

if not exist "%~dp0dist\index.html" (
    echo [WARN] dist\index.html missing - UI may not open.
)

echo Python: !PYTHON!
echo Starting backend on http://127.0.0.1:8000 ...
start "MuraveiVision Backend" "!PYTHON!" -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000

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