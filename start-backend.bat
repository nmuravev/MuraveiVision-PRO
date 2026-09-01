@echo off
REM Always use the Python 3.12 venv — never the system 3.14 interpreter.
cd /d "%~dp0"
"%~dp0muravei_env\Scripts\python.exe" -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --log-level info
