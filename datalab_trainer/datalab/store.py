"""Where DataLab keeps your work: progress, saved code, report drafts, settings.

* Windows: %APPDATA%\\DataLabTrainer
* Linux:   $XDG_DATA_HOME/datalab-trainer (usually ~/.local/share/datalab-trainer)
* Override with the DATALAB_HOME environment variable.

The workspace sub-folder is where your code runs. It holds a copy of the
datasets (data/), captured figures (figures/), exported reports (reports/) and
anything your own code writes.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path

PACKAGE_DATA = Path(__file__).resolve().parent / "data"


def home_dir() -> Path:
    if os.environ.get("DATALAB_HOME"):
        return Path(os.environ["DATALAB_HOME"])
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home())) / "DataLabTrainer"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "datalab-trainer"


def prepare_workspace(home: Path, reset: bool = False) -> Path:
    ws = home / "workspace"
    data = ws / "data"
    for sub in ("data", "figures", "reports", "scripts"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    for f in PACKAGE_DATA.iterdir():
        if f.is_file() and f.suffix in {".csv", ".json", ".db", ".xlsx"}:
            dest = data / f.name
            if reset or not dest.exists():
                shutil.copy2(f, dest)
    return ws


DEFAULT_SETTINGS = {"python_path": "", "rscript_path": "", "timeout": 120}


class Store:
    def __init__(self, home: Path | None = None):
        self.home = home or home_dir()
        self.home.mkdir(parents=True, exist_ok=True)
        self.workspace = prepare_workspace(self.home)
        self.path = self.home / "progress.json"
        self._lock = threading.Lock()
        self.data = {"exercises": {}, "quiz": {}, "report": {}, "settings": dict(DEFAULT_SETTINGS),
                     "playground": {}, "project": {}}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                for k, v in loaded.items():
                    if isinstance(v, dict) and isinstance(self.data.get(k), dict):
                        self.data[k].update(v)
            except (OSError, ValueError):
                shutil.copy2(self.path, self.path.with_suffix(".broken.json"))

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    # -- exercises
    def exercise(self, ex_id: str) -> dict:
        return self.data["exercises"].get(ex_id, {})

    def save_code(self, ex_id: str, code: str) -> None:
        with self._lock:
            rec = self.data["exercises"].setdefault(ex_id, {"passed": False, "attempts": 0})
            rec["code"] = code
            rec["updated"] = time.time()
            self.save()

    def record_attempt(self, ex_id: str, code: str, passed: bool) -> None:
        with self._lock:
            rec = self.data["exercises"].setdefault(ex_id, {"passed": False, "attempts": 0})
            rec["attempts"] = rec.get("attempts", 0) + 1
            rec["code"] = code
            rec["updated"] = time.time()
            if passed:
                rec["passed"] = True
                rec.setdefault("passed_at", time.time())
            self.save()

    def mark_revealed(self, ex_id: str) -> None:
        with self._lock:
            rec = self.data["exercises"].setdefault(ex_id, {"passed": False, "attempts": 0})
            rec["revealed"] = True
            self.save()

    # -- generic sections
    def get(self, section: str) -> dict:
        return self.data.setdefault(section, {})

    def put(self, section: str, value: dict) -> None:
        with self._lock:
            self.data[section] = value
            self.save()

    def reset_progress(self) -> None:
        with self._lock:
            settings = self.data.get("settings", dict(DEFAULT_SETTINGS))
            self.data = {"exercises": {}, "quiz": {}, "report": {}, "settings": settings,
                         "playground": {}, "project": {}}
            self.save()
