@echo off
REM Builds DataLabTrainer.exe and (if Inno Setup 6 is installed) the installer, on Windows.
REM The same steps run automatically on GitHub Actions - see .github\workflows\datalab.yml
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe call install.bat < NUL
.venv\Scripts\python.exe -m pip install pyinstaller || (pause & exit /b 1)
.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist --workpath build packaging\datalab.spec || (pause & exit /b 1)
for /f %%v in ('.venv\Scripts\python.exe -c "import datalab; print(datalab.__version__)"') do set VER=%%v
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ISCC%" ("%ISCC%" /DMyAppVersion=%VER% packaging\DataLabTrainer.iss) else (echo Inno Setup 6 not found - skipping the installer. The app is in dist\DataLabTrainer\)
pause
