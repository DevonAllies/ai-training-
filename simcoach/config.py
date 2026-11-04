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


# Training features that can be switched on/off in Settings (all on by default).
FEATURES = {
    "live_feedback": "Live corner feedback (brake / turn-in / trail / apex / throttle calls)",
    "brake_cue": "Brake cue on the overlay",
    "sectors": "Sector times",
    "drills": "Corner drills",
    "consistency": "Consistency trainer",
    "endurance": "Race, endurance & fuel saving",
    "practice": "Progress & practice plan",
    "goals": "Weekly training goal & streak",
    "traffic": "Racecraft (clean passes, let-bys, defending, faster-car warnings)",
    "game": "Training game (XP, levels, combos, daily challenge, badges)",
}


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
    # Voice coach: "off", "cues" (one reminder before a corner), "detailed" (+ braking/turn-in/trail
    # calls) or "full" (+ brake pressure, apex speed and throttle calls)
    voice_mode: str = "full"
    voice_v2: bool = False             # one-time move of old "cues" setups to the more vocal coach
    voice_native: bool = True          # speak through Windows text-to-speech
    voice_practice_only: bool = True
    # Corner drill: a corner counts as "on target" within this many seconds of the reference
    focus_target: float = 0.05
    # Keep a history of every session (for the Progress tab)
    record_history: bool = True
    # Let a tablet/phone on the home network open the dashboard (needs a restart to apply)
    lan_access: bool = False
    # Weekly training goal: "minutes" on track, "sessions" or "laps" per week
    goal_type: str = "minutes"
    goal_value: float = 180
    # Race mode: in race sessions switch the training off (corner calls, drills, consistency
    # trainer, game pop-ups) and record a race report instead
    race_mode: bool = True
    # Training features on/off (keys from FEATURES)
    features: dict = field(default_factory=lambda: {k: True for k in FEATURES})

    def on(self, feature: str) -> bool:
        return bool(self.features.get(feature, True))
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
        cfg.features = {k: bool(cfg.features.get(k, True)) for k in FEATURES} if isinstance(cfg.features, dict) \
            else {k: True for k in FEATURES}
        if not cfg.voice_v2:                       # v0.7: the coach became more vocal by default
            if cfg.voice_mode == "cues":
                cfg.voice_mode = "full"
            cfg.voice_v2 = True
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
