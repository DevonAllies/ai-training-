"""'Start with Windows' - a per-user Run key, the same one the installer sets."""

from __future__ import annotations

import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "SimCoach"


def supported() -> bool:
    return sys.platform == "win32"


def command() -> str:
    if getattr(sys, "frozen", False):           # installed SimCoach.exe
        return f'"{sys.executable}" --no-browser'
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{exe}" -m simcoach --no-browser'


def is_enabled() -> bool:
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, VALUE)
            return True
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    if not supported():
        return False
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if on:
            winreg.SetValueEx(k, VALUE, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, VALUE)
            except OSError:
                pass
    return is_enabled()
