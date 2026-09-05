@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
echo ============================================
echo   MuraveiVision PRO — setup_env
echo ============================================
echo.

where powershell >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] PowerShell не найден. Нужен Windows PowerShell 5.1+.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_env.ps1"
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo [ОШИБКА] setup_env завершился с кодом %EC%.
  exit /b %EC%
)
exit /b 0
