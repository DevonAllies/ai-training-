@echo off
REM Builds SimCoach.exe and (if Inno Setup 6 is installed) the SimCoach-Setup installer.
REM The same steps run automatically on GitHub Actions - see .github\workflows\build.yml
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call install.bat
.venv\Scripts\pip install pyinstaller || (pause & exit /b 1)
.venv\Scripts\pyinstaller --noconfirm --distpath dist --workpath build packaging\simcoach.spec || (pause & exit /b 1)
echo.
echo Built dist\SimCoach\SimCoach.exe
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  for /f "tokens=2 delims==" %%v in ('findstr /b "__version__" simcoach\__init__.py') do set VER=%%~v
  call set VER=%%VER: =%%
  call set VER=%%VER:"=%%
  %ISCC% /DMyAppVersion=%VER% packaging\SimCoach.iss && echo Built dist\SimCoach-Setup-%VER%.exe
) else (
  echo Inno Setup 6 not found - skipping the installer. Get it from https://jrsoftware.org/isinfo.php
)
pause
