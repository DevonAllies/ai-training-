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
from .config import Config, laps_dir
from .lap import GRID, N_BINS, Lap, fmt_time

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
        return {
            "on_track": True, "session_num": 0, "session_time": self.session_time, "pct": self.pct,
            "lap": self.lap, "speed": at(self._v), "throttle": at(self._thr), "brake": at(self._brk),
            "gear": round(at(self._gear)), "steer": at(self._steer), "lat": at(self._lat),
            "lon": at(self._lon), "on_pit_road": False, "surface": 3, "last_lap_time": 0.0,
        }

    def session(self) -> dict:
        return {"track": "Demo Ring", "track_config": "GP", "track_id": None,
                "track_length": demo.TRACK_LENGTH, "car": "Demo GT3", "car_id": None,
                "driver": "You", "session_types": {0: "Practice"},
                "sectors": [0.0, 0.25, 0.5, 0.75]}


def parse_track_length(s: str) -> float:
    m = re.search(r"([\d.]+)\s*(km|mi)", s or "")
    if not m:
        return 0.0
    v = float(m.group(1))
    return v * 1000 if m.group(2) == "km" else v * 1609.344


# ------------------------------------------------------------- lap buffer
class LapBuffer:
    """Fills the distance grid as samples arrive."""

    CH = ("speed", "throttle", "brake", "gear", "steer", "lat", "lon", "time")

    def __init__(self, start_session_time: float | None):
        self.start = start_session_time
        self.data = {k: np.zeros(N_BINS) for k in self.CH}
        self.filled = np.zeros(N_BINS, dtype=bool)
        self.prev: dict | None = None
        self.valid = start_session_time is not None
        self.max_bin = -1

    def add(self, s: dict) -> None:
        if s["on_pit_road"] or s["surface"] == 0:
            self.valid = False
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
                self.data[k][i] = p0[k] + (s[k] - p0[k]) * f
            self.filled[i] = True
            self.max_bin = max(self.max_bin, i)

    def coverage(self) -> float:
        return float(self.filled.mean())

    def to_lap(self, track_length: float) -> Lap:
        idx = np.flatnonzero(self.filled)
        arr = {}
        for k in self.CH:
            arr[k] = np.interp(np.arange(N_BINS), idx, self.data[k][idx]) if len(idx) else self.data[k]
        return Lap(speed=np.clip(arr["speed"], 0.5, None), throttle=arr["throttle"],
                   brake=arr["brake"], time=np.maximum.accumulate(arr["time"]), gear=arr["gear"],
                   steer=arr["steer"], lat=arr["lat"], lon=arr["lon"], track_length=track_length)


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


def build_ref_corners(ref: Lap, corners: list[Corner]) -> list[RefCorner]:
    out = []
    for c in corners:
        a, m, b = c.start, c.apex, c.end
        w = max(5, (b - a) // 4)
        lo, hi = max(a, m - w), min(b, m + w)
        apex = lo + int(np.argmin(ref.speed[lo:hi + 1]))
        thr = steer_threshold(ref, a, b)
        out.append(RefCorner(
            corner=c, brake=_brake_on(ref.brake, a, m), turn_in=turn_in_bin(ref, a, apex, thr),
            apex=apex, min_speed=float(ref.speed[apex]), throttle=_throttle_on(ref.throttle, apex, b),
            steer_thr=thr, win=w,
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
    return kind, "ok"


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
        self.last_lap: Lap | None = None
        self.last_comparison: dict | None = None
        self.session_best: Lap | None = None
        self.laps_done: list[dict] = []
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

    def set_reference(self, lap: Lap | None, session_best: bool = False) -> None:
        with self.lock:
            self.reference = lap
            self.ref_corners = detect_corners(lap) if lap is not None else []
            self.ref_marks = build_ref_corners(lap, self.ref_corners) if lap is not None else []
            self.ref_label = lap.label if lap is not None else ""
            self.ref_is_session_best = session_best
            self._next_corner = self._corner_after(self.last_sample["pct"] if self.last_sample else 0)

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
                self._finish_lap(old, t_cross - old.start)
            self.buf = LapBuffer(t_cross)
            self.buf.add(dict(s, pct=0.0, session_time=t_cross))
            self.buf.add(s)
            self.callouts = []
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
        self.events.append({"corner": rc.corner.name, "kind": kind, "value": round(value, 1),
                            "text": text, "severity": sev,
                            "t": self.last_sample["session_time"] if self.last_sample else 0.0})
        self.events = self.events[-30:]

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
                self._event(idx, rc, "min_speed", (float(seg.min()) - rc.min_speed) * MS_TO_KMH)
            if rc.throttle is not None and idx in self._my_apex and (idx, "throttle") not in self._reported:
                mt = _throttle_on(data["throttle"], self._my_apex[idx], min(cur, b))
                if mt is not None:
                    self._event(idx, rc, "throttle", (mt - rc.throttle) * bin_m)

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
            self.callouts.append(rep.to_dict())

    def track_length(self) -> float:
        return (self.session.get("track_length") or
                (self.reference.track_length if self.reference is not None else 0.0) or 4000.0)

    def _finish_lap(self, buf: LapBuffer, lap_time: float) -> None:
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
        }
        self.last_lap = lap
        info = {"lap_time": round(lap_time, 3), "valid": buf.valid, "label": lap.label, "file": None,
                "sectors": [x["time"] for x in self.cur_sectors]}

        if self.reference is not None:
            cmp = compare_laps(lap, self.reference, self.ref_corners, self.config.units)
            self.last_comparison = cmp.to_dict()
            info["gap"] = round(lap_time - self.reference.lap_time, 3)

        if buf.valid:
            if self.session_best is None or lap_time < self.session_best.lap_time:
                self.session_best = lap
                if self.reference is None or self.ref_is_session_best:
                    self.set_reference(lap, session_best=True)
            if self.config.record_laps:
                info["file"] = self._save(lap, when)
        self.laps_done.append(info)

    def _save(self, lap: Lap, when: datetime) -> str:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{lap.meta['track']}_{lap.meta['car']}").strip("_")
        name = f"{when:%Y%m%d_%H%M%S}_{safe}_{lap.lap_time:.3f}.csv"
        path: Path = laps_dir() / name
        lap.save(path)
        return name

    # ------------------------------------------------------------ snapshot
    def _brake_cue(self, pct: float) -> dict | None:
        """Distance to the next reference braking point (only when it's close)."""
        L = self.track_length()
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
                "laps": self.laps_done[-15:],
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
        recent = [e for e in snap.get("events", []) if now - e["t"] < 12.0][-4:]
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
        }

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
