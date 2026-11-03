@echo off
REM One-time setup: creates a Python virtual environment and installs SimCoach.
REM Requires Python 3.10+ from https://www.python.org/downloads/ (tick "Add python.exe to PATH").
cd /d "%~dp0"
where python >nul 2>nul || (echo Python not found. Install Python 3.10+ and tick "Add to PATH". & pause & exit /b 1)
python -m venv .venv || (pause & exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (pause & exit /b 1)
echo.
echo SimCoach installed. Start it with run.bat
pause
