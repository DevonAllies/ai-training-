# PyInstaller recipe for DataLab Trainer (Windows and Linux, one-folder build).
#   pyinstaller --noconfirm packaging/datalab.spec      (run from the datalab_trainer folder)
# Output: dist/DataLabTrainer/DataLabTrainer(.exe)
#
# The build bundles Python plus every library the course uses, so learners
# don't need Python installed. The packaged app runs learner code with itself
# as the interpreter ("DataLabTrainer --python script.py"), so every module a
# learner might import has to be bundled: the whole standard library plus the
# data science stack.
# -*- mode: python ; coding: utf-8 -*-
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PKG = os.path.join(ROOT, "datalab")

datas = [
    (os.path.join(PKG, "static"), os.path.join("datalab", "static")),
    (os.path.join(PKG, "data"), os.path.join("datalab", "data")),
    (os.path.join(PKG, "curriculum"), os.path.join("datalab", "curriculum")),
]
binaries = []
hidden = []

# Learner-facing libraries: collect everything (code, data files, binaries).
for pkg in ["pandas", "numpy", "scipy", "sklearn", "statsmodels", "patsy", "matplotlib",
            "duckdb", "openpyxl", "shap", "numba", "llvmlite", "slicer", "cloudpickle",
            "joblib", "threadpoolctl", "dateutil", "pytz", "tzdata", "PIL", "formulaic"]:
    try:
        d, b, h = collect_all(pkg)
    except Exception as e:  # optional packages that aren't installed
        print(f"[datalab.spec] skipping {pkg}: {e}")
        continue
    datas += d
    binaries += b
    hidden += h

# The whole standard library, so learner code can import json, csv, statistics, sqlite3 ...
SKIP_STDLIB = {"tkinter", "turtle", "turtledemo", "idlelib", "test", "lib2to3", "ensurepip",
               "venv", "pydoc_data", "msilib", "nis", "spwd", "ossaudiodev", "crypt"}
for name in sorted(sys.stdlib_module_names):
    if name.startswith("_") or name in SKIP_STDLIB:
        continue
    try:
        hidden += collect_submodules(name, filter=lambda m: ".test" not in m and ".tests" not in m)
    except Exception:
        hidden.append(name)

a = Analysis(
    [os.path.join(ROOT, "packaging", "datalab_launcher.py")],
    pathex=[ROOT],
    datas=datas,
    binaries=binaries,
    hiddenimports=sorted(set(hidden)),
    excludes=["tkinter", "pytest", "IPython", "jupyter", "notebook", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DataLabTrainer",
    console=True,                       # a small window shows the address; closing it stops DataLab
    icon=os.path.join(ROOT, "packaging", "datalab.ico"),
    upx=False,                          # UPX triggers antivirus false positives
)
coll = COLLECT(exe, a.binaries, a.datas, name="DataLabTrainer", upx=False)
