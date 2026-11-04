@echo off
REM Starts DataLab Trainer and opens it in your browser. Close this window to stop it.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call install.bat
.venv\Scripts\python.exe -m datalab %*
pause
