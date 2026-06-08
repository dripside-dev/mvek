@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo === Game crashed. See error above. ===
    pause
)
