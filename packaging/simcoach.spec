# PyInstaller build recipe for SimCoach (Windows, one-folder, no console window).
#   pyinstaller packaging/simcoach.spec
# Output: dist/SimCoach/SimCoach.exe
# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

hidden = (
    collect_submodules("uvicorn")
    + ["irsdk", "yaml", "pyttsx3", "pyttsx3.drivers", "pyttsx3.drivers.sapi5", "comtypes.client",
       "pystray", "pystray._win32", "PIL.Image", "openpyxl"]
)

a = Analysis(
    [os.path.join(ROOT, "simcoach_launcher.py")],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, "simcoach", "static"), os.path.join("simcoach", "static")),
        (os.path.join(ROOT, "sample_data"), "sample_data"),
    ],
    hiddenimports=hidden,
    excludes=["pytest", "matplotlib", "pandas", "scipy", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SimCoach",
    console=False,                      # tray app - no console window
    icon=os.path.join(ROOT, "packaging", "simcoach.ico"),
    upx=False,                          # UPX triggers antivirus false positives
)
coll = COLLECT(exe, a.binaries, a.datas, name="SimCoach", upx=False)
