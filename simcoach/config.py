"""Persistent user configuration (Garage 61 token, preferences) and data folders."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def app_dir() -> Path:
    """Folder where SimCoach keeps its config and recorded laps."""
    override = os.environ.get("SIMCOACH_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "SimCoach"
    else:
        base = Path.home() / ".simcoach"
    base.mkdir(parents=True, exist_ok=True)
    return base


def laps_dir() -> Path:
    d = app_dir() / "laps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    d = app_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Config:
    garage61_token: str = ""
    # Units used in the UI: "metric" (km/h, m) or "imperial" (mph, ft)
    units: str = "metric"
    # Laps fetched from Garage 61: include laps of drivers you follow
    include_following: bool = True
    # Extra Garage 61 driver slugs to always include in lap searches
    extra_drivers: list[str] = field(default_factory=list)
    # Automatically save every clean lap you drive
    record_laps: bool = True
    # In-game overlay: "practice" (only in practice/testing sessions), "always" or "off"
    overlay_mode: str = "practice"
    overlay_x: int = 60
    overlay_y: int = 60
    overlay_scale: float = 1.0
    overlay_opacity: float = 0.85
    # Voice coach: "off", "cues" (one short reminder before a corner) or "detailed"
    voice_mode: str = "cues"
    voice_native: bool = True          # speak through Windows text-to-speech
    voice_practice_only: bool = True
    # Corner drill: a corner counts as "on target" within this many seconds of the reference
    focus_target: float = 0.05
    # Updates from GitHub Releases: "auto" (install when not driving), "notify" or "off"
    update_mode: str = "auto"
    update_repo: str = "DevonAllies/ai-training-"

    @classmethod
    def path(cls) -> Path:
        return app_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        p = cls.path()
        if not p.exists():
            cfg = cls()
        else:
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = {}
            known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            cfg = cls(**known)
        env_token = os.environ.get("GARAGE61_TOKEN")
        if env_token and not cfg.garage61_token:
            cfg.garage61_token = env_token
        return cfg

    def save(self) -> None:
        self.path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    def public(self) -> dict:
        """Config for the UI - never send the full token back to the browser."""
        d = asdict(self)
        tok = d.pop("garage61_token")
        d["has_token"] = bool(tok)
        d["token_hint"] = (tok[:4] + "…" + tok[-4:]) if len(tok) > 10 else ""
        return d
