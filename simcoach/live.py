"""Live telemetry: read iRacing (or the demo driver) at 60 Hz, build the current
lap on the shared distance grid, compute the live delta against the reference
lap and produce coaching feedback as you drive:

* per-corner phase events the moment they happen - brake point, turn-in,
  minimum speed and throttle pick-up compared with the reference lap
* a corner summary when you exit each corner
* sector times against target sectors (from an imported Garage 61 session
  or your session best)
* a "brake now" cue at the reference braking point
"""

from __future__ import annotations

import collections
import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from . import demo
from .analysis import (MS_TO_KMH, Corner, _brake_on, _throttle_on, compare_corner, compare_laps,
                       detect_corners, steer_threshold, turn_in_bin)
from . import history
from .coach import SessionCoach
from .race import RaceTracker, extra_lap_target, lift_plan
from .config import Config, laps_dir
from .corners import apply_names
from .lap import GRID, N_BINS, Lap, fmt_time
from .voice import VoiceCoach

log = logging.getLogger(__name__)

HZ = 60
PRACTICE_TYPES = {"practice", "open practice", "lone practice", "offline testing", "warmup", "testing"}


# ------------------------------------------------------------------ sources
class TelemetrySource:
    name = "none"

    def connect(self) -> bool:
        raise NotImplementedError

    def read(self) -> dict | None:
        """Return the latest sample or None if not available."""
        raise NotImplementedError

    def session(self) -> dict:
        return {}

    def close(self) -> None:
        pass


class IRacingSource(TelemetrySource):
    """Reads iRacing's shared-memory telemetry via pyirsdk (Windows only)."""
    name = "iracing"

    def __init__(self):
        try:
            import irsdk  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on platform
            raise RuntimeError("pyirsdk is not installed (pip install pyirsdk)") from exc
        self.ir = irsdk.IRSDK()
        self._session_cache: dict = {}
        self._session_update = -1

    def connect(self) -> bool:
        if self.ir.is_initialized and self.ir.is_connected:
            return True
        if self.ir.is_initialized:
            self.ir.shutdown()
        return bool(self.ir.startup()) and self.ir.is_connected

    def read(self) -> dict | None:
        ir = self.ir
        if not (ir.is_initialized and ir.is_connected):
            return None
        ir.freeze_var_buffer_latest()
        try:
            base = {"session_num": int(ir["SessionNum"] or 0)}
            if not ir["IsOnTrack"]:
                return dict(base, on_track=False)
            return dict(
                base,
                on_track=True,
                session_time=float(ir["SessionTime"]),
                pct=float(ir["LapDistPct"]),
                lap=int(ir["Lap"]),
                speed=float(ir["Speed"]),
                throttle=float(ir["Throttle"]),
                brake=float(ir["Brake"]),
                gear=float(ir["Gear"]),
                steer=float(ir["SteeringWheelAngle"]),
                lat=float(ir["Lat"] or 0.0),
                lon=float(ir["Lon"] or 0.0),
                on_pit_road=bool(ir["OnPitRoad"]),
                surface=int(ir["PlayerTrackSurface"]),   # 0 = off track, 3 = on track
                last_lap_time=float(ir["LapLastLapTime"] or 0.0),
                yaw=_f(ir["YawRate"]),
                latacc=_f(ir["LatAccel"]),
                rpm=_f(ir["RPM"]),
                abs=_f(ir["BrakeABSactive"]),
                fuel=_f(ir["FuelLevel"]),
                fuel_per_hour=_f(ir["FuelUsePerHour"]),          # kg/h
                time_remain=_f(ir["SessionTimeRemain"], -1.0),
                laps_remain=_f(ir["SessionLapsRemainEx"], -1.0),
                track_temp=_f(ir["TrackTempCrew"]),
            )
        finally:
            ir.unfreeze_var_buffer_latest()

    def session(self) -> dict:
        ir = self.ir
        upd = getattr(ir, "last_session_info_update", None)
        if self._session_cache and upd == self._session_update:
            return self._session_cache
        try:
            wk = ir["WeekendInfo"] or {}
            drv = ir["DriverInfo"] or {}
            me = drv.get("Drivers", [])[drv.get("DriverCarIdx", 0)]
            sessions = (ir["SessionInfo"] or {}).get("Sessions", []) or []
            splits = (ir["SplitTimeInfo"] or {}).get("Sectors", []) or []
        except (KeyError, IndexError, TypeError):
            return self._session_cache
        self._session_update = upd
        self._session_cache = {
            "track": wk.get("TrackDisplayName", ""),
            "track_config": wk.get("TrackConfigName", "") or "",
            "track_id": wk.get("TrackID"),
            "track_length": parse_track_length(wk.get("TrackLength", "")),
            "car": me.get("CarScreenName", ""),
            "car_id": me.get("CarID"),
            "driver": me.get("UserName", ""),
            "session_types": {int(s.get("SessionNum", i)): s.get("SessionType", "")
                              for i, s in enumerate(sessions)},
            "sectors": sorted(float(s.get("SectorStartPct", 0)) for s in splits),
            "fuel_max_l": _f(drv.get("DriverCarFuelMaxLtr")) * (_f(drv.get("DriverCarMaxFuelPct"), 1.0) or 1.0),
            "session_lengths": {int(s.get("SessionNum", i)): {"laps": s.get("SessionLaps"),
                                                              "time": s.get("SessionTime")}
                                for i, s in enumerate(sessions)},
        }
        return self._session_cache

    def close(self) -> None:
        if self.ir.is_initialized:
            self.ir.shutdown()


class DemoSource(TelemetrySource):
    """Simulated driver lapping the demo track in real time."""
    name = "demo"

    def __init__(self, speedup: float = 1.0):
        self.speedup = speedup
        self.session_time = 0.0
        self.pct = 0.95
        self.lap = 0
        self._new_profile()
        self._last = time.monotonic()

    def _new_profile(self):
        self._lapno = getattr(self, "_lapno", 0) + 1
        lap = demo.make_lap(demo.YOU_STYLE, "you", jitter=1.2, seed=self._lapno)
        self._v, self._thr, self._brk, self._gear = lap.speed, lap.throttle, lap.brake, lap.gear
        self._lat, self._lon, self._steer = lap.lat, lap.lon, lap.steer
        self._yaw, self._latacc, self._rpm, self._abs = lap.yaw, lap.latacc, lap.rpm, lap.abs
        if not hasattr(self, "fuel_level"):
            self.fuel_level = demo.FUEL_TANK_L

    def connect(self) -> bool:
        return True

    def read(self) -> dict | None:
        now = time.monotonic()
        dt = min(0.1, now - self._last) * self.speedup
        self._last = now
        v = float(np.interp(self.pct, GRID, self._v, period=1.0))
        self.session_time += dt
        self.pct += v * dt / demo.TRACK_LENGTH
        if self.pct >= 1.0:
            self.pct -= 1.0
            self.lap += 1
            self._new_profile()

        def at(a):
            return float(np.interp(self.pct, GRID, a, period=1.0))
        thr = at(self._thr)
        self.fuel_level -= (0.002 + 0.045 * thr) * dt
        if self.fuel_level < 3.0:                     # demo: "refuel" silently
            self.fuel_level = demo.FUEL_TANK_L
        return {
            "on_track": True, "session_num": 0, "session_time": self.session_time, "pct": self.pct,
            "lap": self.lap, "speed": at(self._v), "throttle": at(self._thr), "brake": at(self._brk),
            "gear": round(at(self._gear)), "steer": at(self._steer), "lat": at(self._lat),
            "lon": at(self._lon), "on_pit_road": False, "surface": 3, "last_lap_time": 0.0,
            "yaw": at(self._yaw), "latacc": at(self._latacc), "rpm": at(self._rpm), "abs": at(self._abs),
            "fuel": self.fuel_level, "fuel_per_hour": (0.002 + 0.045 * thr) * 3600 * 0.75,
            "time_remain": max(0.0, 6 * 3600 - self.session_time), "laps_remain": -1.0, "track_temp": 30.0,
        }

    def session(self) -> dict:
        return {"track": "Demo Ring", "track_config": "GP", "track_id": None,
                "track_length": demo.TRACK_LENGTH, "car": "Demo GT3", "car_id": None,
                "driver": "You", "session_types": {0: "Practice"},
                "sectors": [0.0, 0.25, 0.5, 0.75], "fuel_max_l": demo.FUEL_TANK_L,
                "session_lengths": {0: {"laps": "unlimited", "time": "21600.0000 sec"}}}


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def parse_track_length(s: str) -> float:
    m = re.search(r"([\d.]+)\s*(km|mi)", s or "")
    if not m:
        return 0.0
    v = float(m.group(1))
    return v * 1000 if m.group(2) == "km" else v * 1609.344


# ------------------------------------------------------------- lap buffer
class LapBuffer:
    """Fills the distance grid as samples arrive."""

    CH = ("speed", "throttle", "brake", "gear", "steer", "lat", "lon", "time",
          "yaw", "latacc", "rpm", "abs", "fuel")

    def __init__(self, start_session_time: float | None):
        self.start = start_session_time
        self.data = {k: np.zeros(N_BINS) for k in self.CH}
        self.filled = np.zeros(N_BINS, dtype=bool)
        self.prev: dict | None = None
        self.valid = start_session_time is not None
        self.max_bin = -1
        self.pit = False                 # lap touched the pit lane
        self.fuel_start: float | None = None

    def add(self, s: dict) -> None:
        if s["on_pit_road"] or s["surface"] == 0:
            self.valid = False
        if s.get("on_pit_road"):
            self.pit = True
        if self.start is not None and self.fuel_start is None and s.get("fuel"):
            self.fuel_start = float(s["fuel"])
        if self.start is None:
            self.prev = s
            return
        s = dict(s, time=s["session_time"] - self.start)
        p0 = self.prev
        self.prev = s
        if p0 is None or "time" not in p0:
            return
        a, b = p0["pct"], s["pct"]
        if b <= a:
            return
        i0 = int(math.ceil(a * N_BINS - 0.5))
        i1 = int(math.floor(b * N_BINS - 0.5))
        for i in range(max(i0, 0), min(i1, N_BINS - 1) + 1):
            f = (GRID[i] - a) / (b - a)
            for k in self.CH:
                a0, a1 = p0.get(k, 0.0), s.get(k, 0.0)
                self.data[k][i] = a0 + (a1 - a0) * f
            self.filled[i] = True
            self.max_bin = max(self.max_bin, i)

    def coverage(self) -> float:
        return float(self.filled.mean())

    def to_lap(self, track_length: float) -> Lap:
        idx = np.flatnonzero(self.filled)
        arr = {}
        for k in self.CH:
            arr[k] = np.interp(np.arange(N_BINS), idx, self.data[k][idx]) if len(idx) else self.data[k]
        def opt(k):                                   # extra channels: None if the source never sent them
            a = arr[k]
            return a if np.any(a != 0) else None
        return Lap(speed=np.clip(arr["speed"], 0.5, None), throttle=arr["throttle"],
                   brake=arr["brake"], time=np.maximum.accumulate(arr["time"]), gear=arr["gear"],
                   steer=arr["steer"], lat=arr["lat"], lon=arr["lon"], yaw=opt("yaw"),
                   latacc=opt("latacc"), rpm=opt("rpm"), abs=opt("abs"), fuel=opt("fuel"),
                   track_length=track_length)


# ------------------------------------------------------- per-corner phases
@dataclass
class RefCorner:
    """Reference markers for one corner, pre-computed for fast live checks."""
    corner: Corner
    brake: int | None
    turn_in: int | None
    apex: int
    min_speed: float
    throttle: int | None
    steer_thr: float | None
    win: int
    trail_m: float | None = None       # metres the reference brakes while turned in (to the apex)
    peak_brake: float | None = None    # reference peak brake pressure in the braking zone


def _trail_m(brake, steer, start: int | None, apex: int, thr: float | None, bin_m: float) -> float | None:
    if start is None or thr is None or steer is None:
        return None
    seg = slice(start, apex + 1)
    return float(np.sum((brake[seg] > 0.05) & (np.abs(steer[seg]) > thr))) * bin_m


def build_ref_corners(ref: Lap, corners: list[Corner]) -> list[RefCorner]:
    out = []
    for c in corners:
        a, m, b = c.start, c.apex, c.end
        w = max(5, (b - a) // 4)
        lo, hi = max(a, m - w), min(b, m + w)
        apex = lo + int(np.argmin(ref.speed[lo:hi + 1]))
        thr = steer_threshold(ref, a, b)
        bb = _brake_on(ref.brake, a, m)
        bin_m = (ref.track_length or 4000.0) / N_BINS
        out.append(RefCorner(
            corner=c, brake=bb, turn_in=turn_in_bin(ref, a, apex, thr),
            apex=apex, min_speed=float(ref.speed[apex]), throttle=_throttle_on(ref.throttle, apex, b),
            steer_thr=thr, win=w, trail_m=_trail_m(ref.brake, ref.steer, bb, apex, thr, bin_m),
            peak_brake=float(np.max(ref.brake[a:apex + 1])) if bb is not None else None,
        ))
    return out


def classify(kind: str, value: float, units: str = "metric") -> tuple[str, str]:
    """Turn a phase difference into (text, severity) for the overlay."""
    def d(m):
        return f"{abs(m):.0f} m" if units == "metric" else f"{abs(m) * 3.281:.0f} ft"

    def v(k):
        return f"{abs(k):.0f} km/h" if units == "metric" else f"{abs(k) / 1.609:.0f} mph"

    if kind == "brake":
        if value < -8:
            return f"Brake {d(value)} too early", "bad"
        if value > 8:
            return f"Brake {d(value)} later", "warn"
        return "Brake point good", "good"
    if kind == "turn_in":
        if value > 8:
            return f"Turn-in {d(value)} too late", "bad"
        if value < -8:
            return f"Turn-in {d(value)} early", "warn"
        return "Turn-in good", "good"
    if kind == "min_speed":
        if value < -3:
            return f"Min speed {v(value)} too slow", "bad"
        if value > 3:
            return f"Min speed +{v(value)}", "good"
        return "Min speed on target", "good"
    if kind == "throttle":
        if value > 8:
            return f"Throttle {d(value)} late", "bad"
        if value < -8:
            return f"Throttle {d(value)} early", "good"
        return "Throttle on time", "good"
    if kind == "trail":                      # metres of trail braking vs the reference
        if value < -15:
            return f"Trail braking {d(value)} short - stay on the brake into the turn", "bad"
        if value > 20:
            return f"Trailing {d(value)} longer than reference", "warn"
        return "Trail braking good", "good"
    if kind == "brake_pressure":             # peak brake difference, fraction (0..1)
        if value < -0.12:
            return f"Brake pressure {abs(value) * 100:.0f}% low - brake harder", "bad"
        if value > 0.12:
            return f"Brake pressure {value * 100:.0f}% high", "warn"
        return "Brake pressure good", "good"
    return kind, "ok"


def spoken_call(kind: str, value: float, sev: str, units: str = "metric") -> str | None:
    """Very short phrase for the voice coach (spoken while driving, so a few words only)."""
    def d(m):
        n = round(abs(m) / 5) * 5 or round(abs(m))
        return f"{n} metres" if units == "metric" else f"{round(abs(m) * 3.281 / 10) * 10} feet"
    if sev == "good":
        return {"brake": "Good brake point", "turn_in": "Good turn in", "trail": "Good trail",
                "brake_pressure": "Good pressure", "min_speed": "Good speed", "throttle": "Good exit"}.get(kind)
    if kind == "brake":
        return f"Brake later, {d(value)}" if value < 0 else f"Braked {d(value)} later"
    if kind == "turn_in":
        return "Turn in earlier" if value > 0 else "Turn in later"
    if kind == "trail":
        return "Trail the brake deeper" if value < 0 else "Release the brake sooner"
    if kind == "brake_pressure":
        return "Brake harder" if value < 0 else "Less brake pressure"
    if kind == "min_speed":
        return "Carry more speed"
    if kind == "throttle":
        return "Throttle earlier"
    return None


# ------------------------------------------------------------------ engine
class LiveEngine:
    def __init__(self, config: Config, source: TelemetrySource | None = None):
        self.config = config
        self.source = source
        self.lock = threading.RLock()
        self.running = False
        self.thread: threading.Thread | None = None

        self.connected = False
        self.session: dict = {}
        self.session_num = 0
        self.reference: Lap | None = None
        self.ref_corners: list[Corner] = []
        self.ref_marks: list[RefCorner] = []
        self.ref_label = ""
        self.ref_is_session_best = False

        self.buf: LapBuffer | None = None
        self.last_sample: dict | None = None
        self.callouts: list[dict] = []          # this lap's corner summaries
        self.events: list[dict] = []            # phase events (brake/turn-in/min speed/throttle)
        self._reported: set[tuple[int, str]] = set()
        self._my_apex: dict[int, int] = {}
        self._last_sev: dict[tuple[int, str], str] = {}   # last lap's result per corner/phase (voice)
        self.last_lap: Lap | None = None
        self.last_comparison: dict | None = None
        self.session_best: Lap | None = None
        self.laps_done: collections.deque[dict] = collections.deque(maxlen=200)
        self.lap_count = 0
        self.race = RaceTracker()
        self.fuel_save: dict | None = None        # active lift-and-coast plan
        self.history_id: str | None = None
        self.history_laps: collections.deque[dict] = collections.deque(maxlen=history.MAX_LAPS)
        self.coach = SessionCoach(VoiceCoach(native=config.voice_native))
        self.coach.focus.target = config.focus_target
        self.status_msg = "Waiting for iRacing…"
        self._next_corner = 0

        # sectors
        self.sector_targets: list[float] | None = None
        self.sector_target_label = ""
        self.sector_targets_auto = True
        self.best_live_sectors: list[float] | None = None
        self.cur_sectors: list[dict] = []
        self._sector_idx = 0
        self._sector_t0 = 0.0
        self.on_session_change = None            # callback(engine) - used to auto-pick targets

    # -------------------------------------------------------------- control
    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, name="live-telemetry", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.source:
            self.source.close()
        self.coach.voice.stop()

    def set_reference(self, lap: Lap | None, session_best: bool = False) -> None:
        with self.lock:
            old = self.ref_corners
            self.reference = lap
            self.ref_corners = detect_corners(lap) if lap is not None else []
            apply_names(self.ref_corners, self.track_name(lap))
            same_layout = len(old) == len(self.ref_corners) and all(
                abs(a.apex - b.apex) <= 15 for a, b in zip(old, self.ref_corners))
            if not same_layout:
                self.coach.reset()
            self.ref_marks = build_ref_corners(lap, self.ref_corners) if lap is not None else []
            self.ref_label = lap.label if lap is not None else ""
            self.ref_is_session_best = session_best
            self._next_corner = self._corner_after(self.last_sample["pct"] if self.last_sample else 0)

    def track_name(self, lap: Lap | None = None) -> str:
        """Track name used for the corner map: live session first, else the lap's metadata."""
        s = self.session
        if s.get("track"):
            return " - ".join(x for x in (s.get("track"), s.get("track_config")) if x)
        lap = lap if lap is not None else self.reference
        return (lap.meta.get("track") if lap is not None else "") or ""

    def refresh_corner_names(self) -> None:
        """Re-apply the corner map (after it was edited or the session changed)."""
        with self.lock:
            if self.ref_corners:
                apply_names(self.ref_corners, self.track_name())

    def set_sector_targets(self, targets: list[float] | None, label: str = "", auto: bool = False) -> None:
        with self.lock:
            self.sector_targets = list(targets) if targets else None
            self.sector_target_label = label if targets else ""
            self.sector_targets_auto = auto or not targets

    def _corner_after(self, pct: float) -> int:
        for i, c in enumerate(self.ref_corners):
            if GRID[c.end] > pct:
                return i
        return len(self.ref_corners)

    # ----------------------------------------------------------------- loop
    def _run(self) -> None:
        if self.source is None:
            try:
                self.source = IRacingSource()
            except RuntimeError as exc:
                self.status_msg = f"Live telemetry unavailable: {exc}"
                log.warning(self.status_msg)
                self.running = False
                return
        period = 1.0 / HZ
        while self.running:
            t0 = time.monotonic()
            try:
                self._tick()
            except Exception:  # keep the loop alive no matter what
                log.exception("telemetry tick failed")
            dt = time.monotonic() - t0
            time.sleep(max(0.0, period - dt) if self.connected else 1.0)

    def _tick(self) -> None:
        src = self.source
        if not self.connected:
            if not src.connect():
                self.status_msg = "Waiting for iRacing…"
                return
            self.connected = True
            self.status_msg = "Connected"
        s = src.read()
        if s is None:
            self.connected = False
            self.status_msg = "iRacing disconnected"
            return
        sess = src.session()
        with self.lock:
            self.session_num = s.get("session_num", 0)
            if sess and sess != self.session:
                changed = (sess.get("track"), sess.get("car")) != \
                    (self.session.get("track"), self.session.get("car"))
                self.session = sess
                if changed:
                    self.best_live_sectors = None
                    self.race.reset()
                    self.fuel_save = None
                    self.history_id = None
                    self.history_laps.clear()
                    if self.ref_corners:
                        apply_names(self.ref_corners, self.track_name())
                    if self.on_session_change:
                        try:
                            self.on_session_change(self)
                        except Exception:
                            log.exception("session change hook failed")
            if not s.get("on_track"):
                self.status_msg = "Connected - not on track"
                self.buf = None
                self.last_sample = None
                return
            self.status_msg = "On track"
            self.coach.voice_mode = self.config.voice_mode
            self.coach.voice_allowed = self.is_practice or not self.config.voice_practice_only
            self._process(s)

    # ---------------------------------------------------------- processing
    @property
    def session_type(self) -> str:
        return (self.session.get("session_types") or {}).get(self.session_num, "")

    @property
    def is_practice(self) -> bool:
        return self.session_type.lower() in PRACTICE_TYPES

    def sector_starts(self) -> list[float]:
        return self.session.get("sectors") or []

    def _process(self, s: dict) -> None:
        prev = self.last_sample
        self.last_sample = s
        if prev is None:
            self.buf = LapBuffer(None)
            self.buf.add(s)
            return
        crossed = s["pct"] < 0.1 and prev["pct"] > 0.9
        if crossed:
            span = (1.0 - prev["pct"]) + s["pct"]
            f = (1.0 - prev["pct"]) / span if span > 0 else 0.0
            t_cross = prev["session_time"] + f * (s["session_time"] - prev["session_time"])
            old = self.buf
            if old is not None and old.start is not None:
                old.add(dict(s, pct=1.0, session_time=t_cross))
                self._finish_sector(t_cross - old.start, old.valid)
                fuel_used = None
                if old.fuel_start is not None and s.get("fuel"):
                    used = old.fuel_start - float(s["fuel"])
                    fuel_used = round(used, 3) if 0 < used < 50 else None   # refuel / reset -> unknown
                self.race.add(int(s.get("lap") or self.lap_count + 1), t_cross - old.start, fuel_used,
                              old.valid, old.pit)
                self._finish_lap(old, t_cross - old.start, fuel_used)
            self.buf = LapBuffer(t_cross)
            self.buf.add(dict(s, pct=0.0, session_time=t_cross))
            self.buf.add(s)
            self.callouts = []
            self.coach.new_lap()
            self._reported = set()
            self._my_apex = {}
            self._next_corner = 0
            self.cur_sectors = []
            self._sector_idx = 0
            self._sector_t0 = 0.0
            return
        if self.buf is None:
            self.buf = LapBuffer(None)
        self.buf.add(s)
        if self.buf.start is not None:
            self._check_sectors(prev, s)
            self._check_phases(s)
            self._check_cues(s["pct"])
        self._check_corner(s["pct"])

    # ------------------------------------------------------------- sectors
    def _check_sectors(self, prev: dict, s: dict) -> None:
        starts = self.sector_starts()
        if len(starts) < 2:
            return
        nxt = self._sector_idx + 1
        while nxt < len(starts) and s["pct"] >= starts[nxt] > prev["pct"]:
            b = starts[nxt]
            f = (b - prev["pct"]) / (s["pct"] - prev["pct"])
            t_prev = prev["session_time"] - self.buf.start
            t_now = s["session_time"] - self.buf.start
            self._finish_sector(t_prev + f * (t_now - t_prev), self.buf.valid)
            nxt = self._sector_idx + 1

    def current_sector_targets(self) -> list[float] | None:
        n = len(self.sector_starts())
        if self.sector_targets and len(self.sector_targets) == n:
            return self.sector_targets
        if self.best_live_sectors and all(math.isfinite(x) for x in self.best_live_sectors):
            return self.best_live_sectors
        return None

    def _finish_sector(self, t_boundary: float, valid: bool) -> None:
        starts = self.sector_starts()
        if len(starts) < 2 or self._sector_idx >= len(starts):
            return
        i = self._sector_idx
        st = t_boundary - self._sector_t0
        targets = self.current_sector_targets()
        target = targets[i] if targets and i < len(targets) else None
        self.cur_sectors.append({"sector": i + 1, "time": round(st, 3),
                                 "delta": None if target is None else round(st - target, 3)})
        if valid and st > 0:
            if self.best_live_sectors is None or len(self.best_live_sectors) != len(starts):
                self.best_live_sectors = [math.inf] * len(starts)
            self.best_live_sectors[i] = min(self.best_live_sectors[i], st)
        self._sector_idx += 1
        self._sector_t0 = t_boundary

    # -------------------------------------------------------------- phases
    def _event(self, idx: int, rc: RefCorner, kind: str, value: float) -> None:
        key = (idx, kind)
        if key in self._reported:
            return
        self._reported.add(key)
        text, sev = classify(kind, value, self.config.units)
        self.events.append({"corner": rc.corner.name, "title": rc.corner.title,
                            "kind": kind, "value": round(value, 1),
                            "text": text, "severity": sev,
                            "t": self.last_sample["session_time"] if self.last_sample else 0.0})
        self.events = self.events[-60:]
        self._speak_event(idx, rc, kind, value, sev)

    # Which phases the voice calls out in "full" mode (braking, turning, trail braking first).
    VOICE_KINDS = ("brake", "brake_pressure", "turn_in", "trail", "min_speed", "throttle")

    def _speak_event(self, idx: int, rc: RefCorner, kind: str, value: float, sev: str) -> None:
        """Live voice calls for braking / turn-in / trail braking as they happen."""
        mode = self.config.voice_mode
        if mode not in ("full", "detailed") or kind not in self.VOICE_KINDS:
            return
        f = self.coach.focus
        if f.active and f.corner is not None and f.corner != idx:
            return                                   # drilling another corner: stay quiet here
        prev = self._last_sev.get((idx, kind))
        self._last_sev[(idx, kind)] = sev
        if sev == "good" and prev not in ("bad", "warn"):
            return                                   # only praise a fixed mistake, not every good corner
        if mode == "detailed" and kind not in ("brake", "turn_in", "trail"):
            return
        phrase = spoken_call(kind, value, sev, self.config.units)
        if phrase:
            self.coach._say(phrase, important=(sev == "bad"))

    def _check_phases(self, s: dict) -> None:
        """Report brake / turn-in / min-speed / throttle differences as they happen."""
        if self.reference is None or not self.ref_marks:
            return
        buf = self.buf
        data = buf.data
        cur = min(N_BINS - 1, int(s["pct"] * N_BINS))
        bin_m = self.track_length() / N_BINS
        for idx, rc in enumerate(self.ref_marks):
            c = rc.corner
            if cur < c.start or cur > c.end + 2:
                continue
            a, b = c.start, c.end
            upto = min(cur, rc.apex + rc.win)
            if rc.brake is not None and (idx, "brake") not in self._reported:
                mb = _brake_on(data["brake"], a, upto)
                if mb is not None:
                    self._event(idx, rc, "brake", (mb - rc.brake) * bin_m)
            if rc.turn_in is not None and (idx, "turn_in") not in self._reported:
                hit = np.flatnonzero(np.abs(data["steer"][a:upto + 1]) > rc.steer_thr)
                if len(hit):
                    self._event(idx, rc, "turn_in", (a + int(hit[0]) - rc.turn_in) * bin_m)
            lo, hi = max(a, rc.apex - rc.win), min(b, rc.apex + rc.win)
            if cur >= hi and (idx, "min_speed") not in self._reported and buf.filled[lo:hi + 1].all():
                seg = data["speed"][lo:hi + 1]
                self._my_apex[idx] = lo + int(np.argmin(seg))
                my_apex = self._my_apex[idx]
                # braking phase is over at the apex: brake pressure and trail braking
                mb = _brake_on(data["brake"], a, my_apex)
                if rc.peak_brake is not None and mb is not None:
                    self._event(idx, rc, "brake_pressure", float(np.max(data["brake"][a:my_apex + 1])) - rc.peak_brake)
                if rc.trail_m is not None and mb is not None:
                    mine = _trail_m(data["brake"], data["steer"], mb, my_apex, rc.steer_thr, bin_m)
                    if mine is not None:
                        self._event(idx, rc, "trail", mine - rc.trail_m)
                self._event(idx, rc, "min_speed", (float(seg.min()) - rc.min_speed) * MS_TO_KMH)
            if rc.throttle is not None and idx in self._my_apex and (idx, "throttle") not in self._reported:
                mt = _throttle_on(data["throttle"], self._my_apex[idx], min(cur, b))
                if mt is not None:
                    self._event(idx, rc, "throttle", (mt - rc.throttle) * bin_m)

    def _check_cues(self, pct: float) -> None:
        """Give the coach a chance to speak a reminder before each corner."""
        if not self.ref_marks:
            return
        L = self.track_length()
        for idx, rc in enumerate(self.ref_marks):
            cue_bin = rc.brake if rc.brake is not None else rc.corner.start
            dist = (GRID[cue_bin] - pct) * L
            if dist < -L / 2:
                dist += L
            if 120 <= dist <= 350:
                plan = (self.fuel_save or {}).get("plan") or []
                lift = next((p for p in plan if p["index"] == idx), None)
                if lift and idx not in self.coach._cued:      # fuel-save mode: lift cue replaces the tip
                    self.coach._cued.add(idx)
                    self.coach._say(f"{rc.corner.spoken}, lift {lift['lift_m']} metres early")
                else:
                    self.coach.pre_corner(idx, rc.corner.name, rc.corner.spoken)

    def _check_corner(self, pct: float) -> None:
        ref = self.reference
        buf = self.buf
        if ref is None or buf is None or buf.start is None:
            return
        while self._next_corner < len(self.ref_corners):
            c = self.ref_corners[self._next_corner]
            if GRID[c.end] > pct:
                break
            self._next_corner += 1
            if not buf.filled[c.start:c.end + 1].all():
                continue
            me = buf.to_lap(self.track_length())
            rep = compare_corner(me, ref, c, self.track_length() / N_BINS)
            d = rep.to_dict()
            self.callouts.append(d)
            self.coach.on_corner(self._next_corner - 1, d)

    def track_length(self) -> float:
        return (self.session.get("track_length") or
                (self.reference.track_length if self.reference is not None else 0.0) or 4000.0)

    def _finish_lap(self, buf: LapBuffer, lap_time: float, fuel_used: float | None = None) -> None:
        if buf.coverage() < 0.97 or lap_time <= 0:
            return
        lap = buf.to_lap(self.track_length())
        if lap.lap_time > 0:
            lap.time = lap.time * (lap_time / lap.lap_time)
        when = datetime.now()
        lap.label = f"{self.session.get('driver') or 'Me'} {fmt_time(lap_time)} ({when:%H:%M})"
        lap.meta = {
            "track": " - ".join(x for x in (self.session.get("track"), self.session.get("track_config")) if x),
            "car": self.session.get("car", ""),
            "ir_track_id": self.session.get("track_id"),
            "ir_car_id": self.session.get("car_id"),
            "date": when.isoformat(timespec="seconds"),
            "valid": buf.valid,
            "session_type": self.session_type,
            "source": "live",
            "fuel_used": fuel_used,
        }
        self.last_lap = lap
        info = {"lap_time": round(lap_time, 3), "valid": buf.valid, "label": lap.label, "file": None,
                "sectors": [x["time"] for x in self.cur_sectors], "fuel_used": fuel_used}

        if self.reference is not None:
            cmp = compare_laps(lap, self.reference, self.ref_corners, self.config.units)
            self.last_comparison = cmp.to_dict()
            info["gap"] = round(lap_time - self.reference.lap_time, 3)
            info["scores"] = self.last_comparison.get("scores")
        self.lap_count += 1
        info["lap"] = self.lap_count
        self.coach.add_lap(self.lap_count, lap_time, buf.valid,
                           self.last_comparison if self.reference is not None else None)

        if buf.valid:
            if self.session_best is None or lap_time < self.session_best.lap_time:
                self.session_best = lap
                if self.reference is None or self.ref_is_session_best:
                    self.set_reference(lap, session_best=True)
            if self.config.record_laps:
                info["file"] = self._save(lap, when)
        self.laps_done.append(info)
        self._record_history(info, lap)

    def _record_history(self, info: dict, lap: Lap) -> None:
        if not self.config.record_history:
            return
        try:
            if self.history_id is None:
                self.history_id = history.new_session_id(lap.meta.get("track", ""), lap.meta.get("car", ""))
            self.history_laps.append({k: info.get(k) for k in ("lap", "lap_time", "valid", "gap", "scores",
                                                               "fuel_used")})
            history.save_session(self.history_id, lap.meta.get("track", ""), lap.meta.get("car", ""),
                                 list(self.history_laps), self.coach.report())
        except OSError:
            log.warning("could not write session history")

    # ------------------------------------------------------------- fuel save
    def enable_fuel_save(self, save_per_lap: float | None = None, extra_lap: bool = False) -> dict:
        """Activate lift-and-coast cues. Plan from your last clean lap (your own brake points)."""
        with self.lock:
            base = self.last_lap if (self.last_lap is not None and self.last_lap.meta.get("valid")) else \
                (self.session_best or self.reference)
            if base is None:
                return {"available": False, "reason": "Drive a clean lap first."}
            fpl = self.race.fuel_per_lap() or (base.meta.get("fuel_used") if base.meta else None)
            target = save_per_lap
            info = None
            if extra_lap and fpl and self.last_sample and self.last_sample.get("fuel"):
                info = extra_lap_target(float(self.last_sample["fuel"]), fpl)
                target = info["save_per_lap"]
            plan = lift_plan(base, target_save_per_lap=target, fuel_per_lap=fpl,
                             corners=self.ref_corners if base is self.reference else None)
            if not plan.get("available"):
                return plan
            plan["extra_lap"] = info
            plan["fuel_per_lap"] = fpl
            self.fuel_save = plan
            return plan

    def disable_fuel_save(self) -> None:
        with self.lock:
            self.fuel_save = None

    def race_status(self) -> dict:
        with self.lock:
            s = self.last_sample or {}
            st = self.race.status(s.get("fuel") or None, s.get("time_remain", -1.0), s.get("laps_remain", -1.0),
                                  self.session.get("fuel_max_l") or None, int(s.get("lap") or self.lap_count))
            st["fuel_save"] = self.fuel_save
            st["session_type"] = self.session_type
            st["session_length"] = (self.session.get("session_lengths") or {}).get(self.session_num)
            return st

    def _save(self, lap: Lap, when: datetime) -> str:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{lap.meta['track']}_{lap.meta['car']}").strip("_")
        name = f"{when:%Y%m%d_%H%M%S}_{safe}_{lap.lap_time:.3f}.csv"
        path: Path = laps_dir() / name
        lap.save(path)
        return name

    # ------------------------------------------------------------ snapshot
    def _brake_cue(self, pct: float) -> dict | None:
        """Distance to the next reference braking point (only when it's close).
        In fuel-save mode the cue points at the lift-and-coast point instead."""
        L = self.track_length()
        if self.fuel_save:
            for p in self.fuel_save.get("plan", []):
                dist = (GRID[p["lift_bin"]] - pct) * L
                if dist < -L / 2:
                    dist += L
                to_brake = (GRID[p["brake_bin"]] - pct) * L
                if to_brake < -L / 2:
                    to_brake += L
                if -40 <= dist <= 250 or (dist < 0 < to_brake):
                    return {"corner": p["corner"], "m": round(dist), "kind": "lift", "lift_m": p["lift_m"]}
        for rc in self.ref_marks:
            if rc.brake is None:
                continue
            dist = (GRID[rc.brake] - pct) * L
            if -40 <= dist <= 250 and pct < GRID[rc.apex]:
                return {"corner": rc.corner.name, "m": round(dist)}
        return None

    def snapshot(self) -> dict:
        with self.lock:
            s = self.last_sample
            out = {
                "connected": self.connected,
                "status": self.status_msg,
                "session": {k: v for k, v in self.session.items() if k != "session_types"},
                "session_type": self.session_type,
                "is_practice": self.is_practice,
                "reference": self.ref_label,
                "ref_is_session_best": self.ref_is_session_best,
                "ref_lap_time": self.reference.lap_time if self.reference is not None else None,
                "laps": list(self.laps_done)[-15:],
                "focus": self.coach.focus.status(),
                "scores": (self.last_comparison or {}).get("scores"),
                "sector_target_label": self.sector_target_label or (
                    "session best" if self.current_sector_targets() else ""),
                "sector_targets": self.current_sector_targets(),
            }
            if not s or not s.get("on_track"):
                return out
            out.update({k: s[k] for k in ("pct", "speed", "throttle", "brake", "gear", "lap")})
            out["on_track"] = True
            buf = self.buf
            if buf is not None and buf.start is not None:
                elapsed = s["session_time"] - buf.start
                out["elapsed"] = elapsed
                out["valid"] = buf.valid
                ref = self.reference
                if ref is not None:
                    pct = s["pct"]
                    delta = elapsed - ref.time_at(pct)
                    out["delta"] = delta
                    out["ref_speed"] = ref.value_at("speed", pct)
                    out["ref_throttle"] = ref.value_at("throttle", pct)
                    out["ref_brake"] = ref.value_at("brake", pct)
                    out["ref_gear"] = ref.value_at("gear", pct) if ref.gear is not None else None
                    back = int(pct * N_BINS) - 40
                    if back >= 0 and buf.filled[back]:
                        out["trend"] = delta - (buf.data["time"][back] - ref.time[back])
                    out["predicted"] = ref.lap_time + delta
                    nxt = self._next_corner
                    if nxt < len(self.ref_corners):
                        c = self.ref_corners[nxt]
                        out["next_corner"] = c.name
                        out["next_corner_title"] = c.title
                        out["next_corner_m"] = max(0.0, (GRID[c.apex] - pct) * self.track_length())
                    out["brake_cue"] = self._brake_cue(pct)
            out["callouts"] = self.callouts[-8:]
            out["events"] = self.events[-8:]
            out["sectors"] = self.cur_sectors
            return out

    def overlay(self) -> dict:
        """Compact state for the in-game overlay."""
        snap = self.snapshot()
        mode = self.config.overlay_mode
        on_track = bool(snap.get("on_track"))
        visible = on_track and (mode == "always" or (mode == "practice" and snap["is_practice"]))
        now = self.last_sample["session_time"] if self.last_sample else 0.0
        focus = snap.get("focus") or {}
        evs = [e for e in snap.get("events", []) if now - e["t"] < 12.0]
        if focus.get("active") and focus.get("name"):
            evs = [e for e in evs if e["corner"] == focus["name"]]
        recent = evs[-4:]
        return {
            "visible": visible,
            "mode": mode,
            "session_type": snap.get("session_type"),
            "delta": snap.get("delta"),
            "trend": snap.get("trend"),
            "predicted": snap.get("predicted"),
            "ref_lap_time": snap.get("ref_lap_time"),
            "has_reference": bool(snap.get("reference")),
            "brake_cue": snap.get("brake_cue"),
            "next_corner": snap.get("next_corner"),
            "events": recent,
            "sectors": snap.get("sectors", []),
            "sector_count": len(self.sector_starts()),
            "units": self.config.units,
            "focus": focus,
            "fuel": self._fuel_overlay(),
            "voice": self.coach.voice.recent(5),
            "voice_mode": self.config.voice_mode,
        }

    def _fuel_overlay(self) -> dict | None:
        s = self.last_sample or {}
        fpl = self.race.fuel_per_lap()
        if not s.get("fuel"):
            return None
        return {"level": round(float(s["fuel"]), 1), "per_lap": fpl,
                "laps": round(float(s["fuel"]) / fpl, 1) if fpl else None,
                "save_mode": bool(self.fuel_save),
                "target": (self.fuel_save or {}).get("target_l")}

    def trace(self) -> dict:
        """Current-lap arrays for the live chart (sent a few times per second)."""
        with self.lock:
            buf = self.buf
            if buf is None or buf.start is None:
                return {"filled_to": -1}
            n = buf.max_bin + 1
            return {
                "filled_to": n,
                "speed": np.round(buf.data["speed"][:n], 2).tolist(),
                "throttle": np.round(buf.data["throttle"][:n], 3).tolist(),
                "brake": np.round(buf.data["brake"][:n], 3).tolist(),
                "delta": (np.round(buf.data["time"][:n] - self.reference.time[:n], 3).tolist()
                          if self.reference is not None else None),
            }
