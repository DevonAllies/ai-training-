@echo off
REM Builds a standalone dist\SimCoach\SimCoach.exe (no Python needed on the target PC).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call install.bat
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller --noconfirm --name SimCoach --console ^
  --add-data "simcoach\static;simcoach\static" ^
  --collect-submodules uvicorn --hidden-import irsdk ^
  simcoach_launcher.py
echo.
echo Built dist\SimCoach\SimCoach.exe
pause
