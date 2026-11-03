"""Live telemetry: read iRacing (or the demo driver) at 60 Hz, build the current
lap on the shared distance grid, compute the live delta against the reference
lap and produce per-corner coaching callouts as you drive.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import demo
from .analysis import Corner, compare_corner, compare_laps, detect_corners
from .config import Config, laps_dir
from .lap import GRID, N_BINS, Lap, fmt_time

log = logging.getLogger(__name__)

HZ = 60


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
        self._irsdk = irsdk
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
            if not ir["IsOnTrack"]:
                return {"on_track": False}
            return {
                "on_track": True,
                "session_time": float(ir["SessionTime"]),
                "pct": float(ir["LapDistPct"]),
                "lap": int(ir["Lap"]),
                "speed": float(ir["Speed"]),
                "throttle": float(ir["Throttle"]),
                "brake": float(ir["Brake"]),
                "gear": float(ir["Gear"]),
                "steer": float(ir["SteeringWheelAngle"]),
                "lat": float(ir["Lat"] or 0.0),
                "lon": float(ir["Lon"] or 0.0),
                "on_pit_road": bool(ir["OnPitRoad"]),
                "surface": int(ir["PlayerTrackSurface"]),   # 0 = off track, 3 = on track
                "last_lap_time": float(ir["LapLastLapTime"] or 0.0),
            }
        finally:
            ir.unfreeze_var_buffer_latest()

    def session(self) -> dict:
        ir = self.ir
        try:
            upd = ir.last_session_info_update  # type: ignore[attr-defined]
        except AttributeError:
            upd = None
        if self._session_cache and upd == self._session_update:
            return self._session_cache
        try:
            wk = ir["WeekendInfo"] or {}
            drv = ir["DriverInfo"] or {}
            me = drv.get("Drivers", [])[drv.get("DriverCarIdx", 0)]
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
        self.t0 = time.monotonic()
        self.session_time = 0.0
        self.pct = 0.95
        self.lap = 0
        self._new_profile()
        self._last = time.monotonic()

    def _new_profile(self):
        self._lapno = getattr(self, "_lapno", 0) + 1
        lap = demo.make_lap(demo.YOU_STYLE, "you", jitter=1.2, seed=self._lapno)
        self._v, self._thr, self._brk, self._gear = lap.speed, lap.throttle, lap.brake, lap.gear
        self._lat, self._lon = lap.lat, lap.lon

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
            "on_track": True, "session_time": self.session_time, "pct": self.pct, "lap": self.lap,
            "speed": at(self._v), "throttle": at(self._thr), "brake": at(self._brk),
            "gear": round(at(self._gear)), "steer": 0.0, "lat": at(self._lat), "lon": at(self._lon),
            "on_pit_road": False, "surface": 3, "last_lap_time": 0.0,
        }

    def session(self) -> dict:
        return {"track": "Demo Ring", "track_config": "GP", "track_id": None,
                "track_length": demo.TRACK_LENGTH, "car": "Demo GT3", "car_id": None,
                "driver": "You"}


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
        self.reference: Lap | None = None
        self.ref_corners: list[Corner] = []
        self.ref_label = ""
        self.ref_is_session_best = False

        self.buf: LapBuffer | None = None
        self.last_sample: dict | None = None
        self.callouts: list[dict] = []          # this lap's corner results
        self.last_lap: Lap | None = None
        self.last_comparison: dict | None = None
        self.session_best: Lap | None = None
        self.laps_done: list[dict] = []
        self.status_msg = "Waiting for iRacing…"
        self._next_corner = 0

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
            self.ref_label = lap.label if lap is not None else ""
            self.ref_is_session_best = session_best
            self._next_corner = self._corner_after(self.last_sample["pct"] if self.last_sample else 0)

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
            if sess and sess != self.session:
                self.session = sess
            if not s.get("on_track"):
                self.status_msg = "Connected - not on track"
                self.buf = None
                self.last_sample = None
                return
            self.status_msg = "On track"
            self._process(s)

    def _process(self, s: dict) -> None:
        prev = self.last_sample
        self.last_sample = s
        if prev is None:
            self.buf = LapBuffer(None)
            self.buf.add(s)
            return
        crossed = s["pct"] < 0.1 and prev["pct"] > 0.9
        if crossed:
            # interpolate the exact crossing time
            span = (1.0 - prev["pct"]) + s["pct"]
            f = (1.0 - prev["pct"]) / span if span > 0 else 0.0
            t_cross = prev["session_time"] + f * (s["session_time"] - prev["session_time"])
            old = self.buf
            if old is not None and old.start is not None:
                # close the last bins with a virtual sample at pct=1.0
                end = dict(s, pct=1.0, session_time=t_cross)
                old.add(end)
                self._finish_lap(old, t_cross - old.start)
            self.buf = LapBuffer(t_cross)
            self.buf.add(dict(s, pct=0.0, session_time=t_cross))
            self.buf.add(s)
            self.callouts = []
            self._next_corner = 0
            return
        if self.buf is None:
            self.buf = LapBuffer(None)
        self.buf.add(s)
        self._check_corner(s["pct"])

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
        # rescale so the grid times end exactly at the measured lap time
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
            "source": "live",
        }
        self.last_lap = lap
        info = {"lap_time": round(lap_time, 3), "valid": buf.valid, "label": lap.label, "file": None}

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
    def snapshot(self) -> dict:
        with self.lock:
            s = self.last_sample
            out = {
                "connected": self.connected,
                "status": self.status_msg,
                "session": self.session,
                "reference": self.ref_label,
                "ref_is_session_best": self.ref_is_session_best,
                "ref_lap_time": self.reference.lap_time if self.reference is not None else None,
                "laps": self.laps_done[-15:],
            }
            if not s or not s.get("on_track"):
                return out
            out.update({k: s[k] for k in ("pct", "speed", "throttle", "brake", "gear", "lap")})
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
                    # trend over the last ~4% of the lap: are we losing time right now?
                    back = int(pct * N_BINS) - 40
                    if back >= 0 and buf.filled[back]:
                        out["trend"] = delta - (buf.data["time"][back] - ref.time[back])
                    out["predicted"] = ref.lap_time + delta
                    nxt = self._next_corner
                    if nxt < len(self.ref_corners):
                        c = self.ref_corners[nxt]
                        out["next_corner"] = c.name
                        out["next_corner_m"] = max(0.0, (GRID[c.apex] - pct) * self.track_length())
            out["callouts"] = self.callouts[-8:]
            return out

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
