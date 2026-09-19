@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
if not defined MURAVEI_LOG_DIR set "MURAVEI_LOG_DIR=%~dp0logs"
if not exist "%MURAVEI_LOG_DIR%" mkdir "%MURAVEI_LOG_DIR%"

REM --- Dynamic version from VERSION file (never hardcode product version) ---
set "VER=unknown"
if exist "%~dp0VERSION" (
  set /p VER=<"%~dp0VERSION"
)
if not defined VER set "VER=unknown"
if "!VER!"=="" set "VER=unknown"

echo ============================================
echo   MuraveiVision PRO v!VER!
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
    REM ping instead of timeout — timeout fails when stdin is redirected (smoke)
    ping -n 4 127.0.0.1 >nul
) else (
    echo Ollama not in kit ^(Lite/Mini^). AI analysis needs a system Ollama if available.
)

REM --- Portable bootstrap (Z2/Z3): stamp missing/stale → audit + offline-first ---
if not defined MURAVEI_BOOTSTRAP_YES set "MURAVEI_BOOTSTRAP_YES=1"
if exist "%~dp0scripts\bootstrap_portable.ps1" (
    echo Checking portable bootstrap...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_portable.ps1" >> "%MURAVEI_LOG_DIR%\bootstrap.log" 2>&1
    if errorlevel 1 (
        echo [ОШИБКА] bootstrap_portable failed. See logs\bootstrap.log
        echo Offline: place wheels/ and sidecars/ next to the project.
        echo See docs\PORTABLE_GUIDE.md
        if not defined MURAVEI_NO_PAUSE pause
        exit /b 1
    )
) else if not exist "%~dp0muravei_env\Scripts\python.exe" (
    if exist "%~dp0scripts\setup_env.bat" (
        echo muravei_env не найден — запускаю scripts\setup_env.bat ...
        call "%~dp0scripts\setup_env.bat"
        if errorlevel 1 (
            echo [ОШИБКА] Не удалось подготовить muravei_env.
            echo Распакуйте dist\muravei_env_pack.zip в корень проекта и снова Запустить.bat
            echo Либо при наличии интернета: scripts\setup_env.bat поставит пакеты с PyPI.
            echo Подробнее: docs\DEPLOY_GUIDE.md
            if not defined MURAVEI_NO_PAUSE pause
            exit /b 1
        )
    )
)

REM === Single-instance check (lock in tempfile) ===
for /f "delims=" %%T in ('echo %TEMP%') do set TEMP_DIR=%%T
if exist "%TEMP_DIR%\.muravei_backend.lock" (
    REM Read stale PID from lock file
    set /p STALE_PID=<"%TEMP_DIR%\.muravei_backend.lock" 2>nul
    REM Check if process is alive
    tasklist /FI "PID eq !STALE_PID!" 2>nul | findstr /i "python" >nul
    if not errorlevel 1 (
        echo [ERROR] Another backend instance already running (PID !STALE_PID!).
        echo Close the existing backend window or delete %TEMP_DIR%\.muravei_backend.lock
        exit /b 1
    ) else (
        echo [WARN] Stale lock file detected (PID !STALE_PID! is dead). Removing...
        del "%TEMP_DIR%\.muravei_backend.lock" 2>nul
    )
)

set "PYTHON="
REM Prefer embeddable root python.exe (portable). Scripts\python.exe is often a
REM same-binary copy without python*._pth and resolves to host/system prefix.
if exist "%~dp0muravei_env\python.exe" set "PYTHON=%~dp0muravei_env\python.exe"
if not defined PYTHON if exist "%~dp0muravei_env\Scripts\python.exe" set "PYTHON=%~dp0muravei_env\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0runtime\python\python.exe" set "PYTHON=%~dp0runtime\python\python.exe"

if not defined PYTHON (
    echo [ОШИБКА] Python не найден.
    echo Ожидается muravei_env\python.exe ^(embed portable^) или muravei_env\Scripts\python.exe ^(3.12.x^).
    echo Поле:  распакуйте muravei_env_pack.zip → scripts\setup_env.bat
    echo Portable: scripts\build_portable.ps1 -FetchEmbeddablePython
    if not defined MURAVEI_NO_PAUSE pause
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

REM --- Air-gap: Ultralytics must not AutoUpdate / pip at runtime ---
set "ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS=1"
set "YOLO_AUTOINSTALL=0"
REM Prefer pack-local ffmpeg over system PATH
if exist "%~dp0assets\ffmpeg" set "PATH=%~dp0assets\ffmpeg;%PATH%"
if exist "%~dp0sidecars\ffmpeg" set "PATH=%~dp0sidecars\ffmpeg;%PATH%"

REM --- One entry path: MODULE mode (never script-mode python backend\main.py) ---
echo Starting backend on http://127.0.0.1:8000 ...

REM === A1: Check if backend is already running via health check (before start) ===
set /a _health_check_tries=0
:health_check_loop
"!PYTHON!" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" 2>nul
if not errorlevel 1 (
    echo [INFO] Backend already running on port 8000. Opening UI...
    if not defined MURAVEI_NO_BROWSER start "" "http://127.0.0.1:8000"
    if not defined MURAVEI_NO_PAUSE pause
    exit /b 0
)
set /a _health_check_tries+=1
if !_health_check_tries! lss 3 goto wait_pid_delete
goto start_backend

:wait_pid_delete
del "%TEMP_DIR%\.muravei_backend.pid" 2>nul
goto start_backend

:start_backend

REM Env vars inherit to child. Use cmd /c ""exe" args" quoting (reliable on Windows).
REM Avoid nested \" escapes that silently fail under some launchers/smoke hosts.
set "MURAVEI_SESSION_TRACE=1"
start "MuraveiVision Backend" /D "%~dp0" cmd /c ""!PYTHON!" -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 >> "!MURAVEI_LOG_DIR!\uvicorn.log" 2>&1"

REM === A1: PID-based wait_loop (loop by PID liveness, NOT lock file) ===
echo Waiting for backend to start...
ping -n 4 127.0.0.1 >nul
:wait_loop
timeout /t 2 /nobreak >nul
if not exist "%TEMP_DIR%\.muravei_backend.pid" goto wait_loop
set /p CUR_PID=<"%TEMP_DIR%\.muravei_backend.pid"
REM Validate PID is a number
echo !CUR_PID! | findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 goto wait_loop
tasklist /FI "PID eq !CUR_PID!" 2>nul | findstr /i "python" >nul
if not errorlevel 1 goto wait_loop
REM Process disappeared — kill tree (no-op if already dead):
taskkill /F /T /PID !CUR_PID! >nul 2>&1

echo Waiting for backend...
set /a _tries=0
:wait_health
"!PYTHON!" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)" 2>nul
if not errorlevel 1 goto health_ok
set /a _tries+=1
if !_tries! geq 60 (
    echo [ERROR] Backend failed to start. Check logs\uvicorn.log and port 8000.
    if not defined MURAVEI_NO_PAUSE pause
    exit /b 1
)
REM ping instead of timeout — timeout fails when stdin is redirected (smoke)
ping -n 3 127.0.0.1 >nul
goto wait_health

:health_ok
echo Backend ready. Opening UI...
if not defined MURAVEI_NO_BROWSER start "" "http://127.0.0.1:8000"
echo.
echo System started.
echo Close the "MuraveiVision Backend" window to stop the API.
if exist "%~dp0ollama\ollama.exe" echo Ollama runs in background - end ollama.exe if needed.
if not defined MURAVEI_NO_PAUSE pause
goto :eof

:health_check_ok
echo [INFO] Backend already running on port 8000. Opening UI...
if not defined MURAVEI_NO_BROWSER start "" "http://127.0.0.1:8000"
echo.
echo System is already running.
if not defined MURAVEI_NO_PAUSE pause
