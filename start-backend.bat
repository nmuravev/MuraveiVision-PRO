@echo off
REM Always use the Python 3.12 venv — never the system 3.14 interpreter.
cd /d "%~dp0"
set "COLMAP_ROOT=%~dp0sidecars\colmap"
if exist "%~dp0sidecars\alicevision\windows-x64\bin\aliceVision_featureExtraction.exe" (
  set "ALICEVISION_ROOT=%~dp0sidecars\alicevision\windows-x64"
)
set "MURAVEI_SESSION_TRACE=1"
"%~dp0muravei_env\Scripts\python.exe" -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --log-level info
