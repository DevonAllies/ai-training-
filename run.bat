@echo off
REM Starts SimCoach and opens the dashboard in your browser.
REM Add --demo to try it without iRacing:   run.bat --demo
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run - installing...
  call install.bat
)
.venv\Scripts\python.exe -m simcoach %*
pause
