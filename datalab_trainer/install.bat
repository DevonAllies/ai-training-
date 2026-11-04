@echo off
REM DataLab Trainer - one-time setup on Windows.
REM Needs Python 3.10+ from https://www.python.org/downloads/ (tick "Add python.exe to PATH").
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (echo Python not found. Install Python 3.10+ and tick "Add python.exe to PATH". & pause & exit /b 1)
if not exist .venv\Scripts\python.exe %PY% -m venv .venv || (pause & exit /b 1)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt || (pause & exit /b 1)
echo.
where Rscript >nul 2>nul || if not exist "%ProgramFiles%\R" (
  echo R was not found. For the R exercises install it from https://cran.r-project.org/bin/windows/base/
)
echo DataLab Trainer is installed. Start it with run.bat
pause
