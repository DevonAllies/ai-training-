"""Lap data model.

Every lap - live from iRacing, recorded locally, or downloaded from Garage 61 -
is resampled onto the same grid of ``N_BINS`` points over lap distance
(0..1 of the lap). That makes laps directly comparable bin-by-bin.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

N_BINS = 1000
GRID = (np.arange(N_BINS) + 0.5) / N_BINS  # bin centres, fraction of lap

CHANNELS = ("speed", "throttle", "brake", "gear", "steer", "lat", "lon",
            "yaw", "latacc", "rpm", "abs", "fuel")
# Optional extra channels (car control & fuel). Present when the source has them.
EXTRA = ("yaw", "latacc", "rpm", "abs", "fuel")

# Column name aliases seen in Garage 61 / iRacing / MoTeC style CSV exports.
_ALIASES = {
    "pct": ["lapdistpct", "lap_dist_pct", "distpct", "lapdistancepct", "lappct", "pct"],
    "dist": ["lapdist", "lap_dist", "distance", "lapdistance", "dist"],
    "time": ["lapcurrentlaptime", "laptime", "time", "elapsed", "t", "sessiontime"],
    "speed": ["speed", "velocity", "groundspeed", "speedms", "speed_ms"],
    "throttle": ["throttle", "throttleraw", "throttlepct", "gas"],
    "brake": ["brake", "brakeraw", "brakepct"],
    "gear": ["gear"],
    "steer": ["steeringwheelangle", "steering", "steer", "steeringangle"],
    "lat": ["lat", "latitude"],
    "lon": ["lon", "long", "longitude", "lng"],
    "yaw": ["yawrate", "yaw_rate"],                       # rad/s (not "Yaw", which is heading)
    "latacc": ["lataccel", "latacc", "lateralacceleration", "glat", "g_lat"],   # m/s^2
    "rpm": ["rpm", "enginerpm"],
    "abs": ["absactive", "absactivity"],
    "fuel": ["fuellevel", "fuel"],                        # litres in tank
}


@dataclass
class Lap:
    speed: np.ndarray            # m/s
    throttle: np.ndarray         # 0..1
    brake: np.ndarray            # 0..1
    time: np.ndarray             # seconds elapsed since the start line, at each bin
    gear: np.ndarray | None = None
    steer: np.ndarray | None = None
    lat: np.ndarray | None = None
    lon: np.ndarray | None = None
    yaw: np.ndarray | None = None      # yaw rate, rad/s
    latacc: np.ndarray | None = None   # lateral acceleration, m/s^2
    rpm: np.ndarray | None = None
    abs: np.ndarray | None = None      # 1 while ABS is working
    fuel: np.ndarray | None = None     # litres in the tank
    track_length: float = 0.0    # metres
    label: str = ""
    meta: dict = field(default_factory=dict)

    # --------------------------------------------------------------- derived
    @property
    def lap_time(self) -> float:
        # time[] is sampled at bin centres; extrapolate the last half bin.
        if len(self.time) < 2:
            return float(self.time[-1]) if len(self.time) else 0.0
        return float(self.time[-1] + (self.time[-1] - self.time[-2]) / 2)

    @property
    def bin_m(self) -> float:
        return self.track_length / N_BINS if self.track_length else 0.0

    def time_at(self, pct: float) -> float:
        return float(np.interp(pct, GRID, self.time, left=0.0, right=self.lap_time))

    def value_at(self, channel: str, pct: float) -> float:
        arr = getattr(self, channel)
        if arr is None:
            return 0.0
        return float(np.interp(pct, GRID, arr))

    def has_map(self) -> bool:
        return (self.lat is not None and self.lon is not None
                and np.nanmax(np.abs(self.lat)) > 0 and np.nanstd(self.lat) > 0)

    # ------------------------------------------------------------- serialise
    def to_json(self, decimals: int = 4) -> dict:
        def arr(a):
            return None if a is None else np.round(a.astype(float), decimals).tolist()
        return {
            "label": self.label,
            "lap_time": round(self.lap_time, 3),
            "track_length": round(self.track_length, 1),
            "speed": arr(self.speed),
            "throttle": arr(self.throttle),
            "brake": arr(self.brake),
            "time": arr(self.time),
            "gear": arr(self.gear),
            "steer": arr(self.steer),
            # GPS needs ~8 decimals (1e-8 deg ~ 1 mm) - 4 decimals would be 11 m steps
            "lat": np.round(self.lat.astype(float), 8).tolist() if self.has_map() else None,
            "lon": np.round(self.lon.astype(float), 8).tolist() if self.has_map() else None,
            **{k: arr(getattr(self, k)) for k in EXTRA if getattr(self, k) is not None},
            "meta": self.meta,
        }

    def save(self, path: Path) -> None:
        """Save as CSV with a JSON metadata header line."""
        extras = [k for k in EXTRA if getattr(self, k) is not None]
        cols = ["pct", "time", "speed", "throttle", "brake", "gear", "steer", "lat", "lon"] + \
            [{"yaw": "yawrate", "latacc": "lataccel", "rpm": "rpm", "abs": "absactive", "fuel": "fuellevel"}[k]
             for k in extras]
        buf = io.StringIO()
        meta = dict(self.meta, label=self.label, track_length=self.track_length,
                    lap_time=self.lap_time)
        buf.write("# " + json.dumps(meta) + "\n")
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(cols)
        zeros = np.zeros(N_BINS)
        data = [GRID, self.time, self.speed, self.throttle, self.brake,
                self.gear if self.gear is not None else zeros,
                self.steer if self.steer is not None else zeros,
                self.lat if self.lat is not None else zeros,
                self.lon if self.lon is not None else zeros] + [getattr(self, k) for k in extras]
        for row in zip(*data):
            # lat/lon (columns 7, 8) need full precision for racing-line comparison
            w.writerow([f"{v:.12g}" if i in (7, 8) else f"{v:.7g}" for i, v in enumerate(row)])
        path.write_text(buf.getvalue(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Lap":
        text = path.read_text(encoding="utf-8")
        meta = {}
        if text.startswith("#"):
            first, text = text.split("\n", 1)
            try:
                meta = json.loads(first[1:].strip())
            except json.JSONDecodeError:
                meta = {}
        lap = parse_csv(text, lap_time=meta.get("lap_time"),
                        track_length=meta.get("track_length") or 0.0)
        lap.label = meta.pop("label", path.stem)
        meta.pop("track_length", None)
        meta.pop("lap_time", None)
        lap.meta = meta
        return lap


# ---------------------------------------------------------------- building
def from_samples(
    pct: np.ndarray,
    speed: np.ndarray,
    throttle: np.ndarray,
    brake: np.ndarray,
    time: np.ndarray | None = None,
    lap_time: float | None = None,
    track_length: float = 0.0,
    dist: np.ndarray | None = None,
    **channels: np.ndarray | None,
) -> Lap:
    """Resample raw (possibly irregular) samples onto the standard grid."""
    pct = np.asarray(pct, dtype=float)
    order_ok = _clean_order(pct)
    pct = pct[order_ok]

    def rs(a):
        if a is None:
            return None
        a = np.asarray(a, dtype=float)[order_ok]
        return np.interp(GRID, pct, a)

    spd = rs(speed)
    spd = np.clip(spd, 0.5, None)  # avoid divide-by-zero when integrating time
    thr = rs(throttle)
    brk = rs(brake)

    if not track_length and dist is not None:
        d = np.asarray(dist, dtype=float)[order_ok]
        # slope of dist vs pct = track length
        if np.ptp(pct) > 0.5:
            track_length = float(np.polyfit(pct, d, 1)[0])

    if time is not None:
        t_raw = np.asarray(time, dtype=float)[order_ok]
        t_raw = t_raw - t_raw[0] + _first_bin_offset(pct[0], spd[0], track_length, t_raw)
        t = np.interp(GRID, pct, t_raw)
        t = np.maximum.accumulate(t)
    else:
        t = _integrate_time(spd, track_length, lap_time)

    if not track_length:
        track_length = estimate_track_length(spd, lap_time or (t[-1] * N_BINS / (N_BINS - 0.5)))

    extra = {k: rs(v) for k, v in channels.items() if k in CHANNELS}
    return Lap(speed=spd, throttle=thr, brake=brk, time=t, track_length=track_length, **extra)


def _clean_order(pct: np.ndarray) -> np.ndarray:
    """Indices of a strictly increasing subsequence of pct (drops wrap-around noise)."""
    idx = np.arange(len(pct))
    # Samples just before the line at the start (pct ~0.99) or after it at the end (pct ~0.01)
    if len(pct) > 10:
        n = len(pct)
        head_bad = (idx < n * 0.1) & (pct > 0.9)
        tail_bad = (idx > n * 0.9) & (pct < 0.1)
        keep = ~(head_bad | tail_bad)
        idx = idx[keep]
    out = []
    last = -1.0
    for i in idx:
        if pct[i] > last:
            out.append(i)
            last = pct[i]
    return np.array(out, dtype=int)


def _first_bin_offset(first_pct, first_speed, track_length, t_raw) -> float:
    # If the first sample is a little after the line, account for the time to get there.
    if track_length and first_speed > 0:
        return first_pct * track_length / first_speed
    return 0.0


def _integrate_time(speed: np.ndarray, track_length: float, lap_time: float | None) -> np.ndarray:
    """Cumulative time at each bin centre from a speed profile.

    dt per bin = bin length / speed. If lap_time is known the result is scaled so
    the lap adds up exactly (this also removes any error in track_length).
    """
    inv = 1.0 / speed
    seg = np.cumsum(inv) - inv / 2          # time to bin centres, in units of bin_len
    total = inv.sum()
    if lap_time:
        return seg * (lap_time / total)
    bin_len = (track_length or 4000.0) / N_BINS
    return seg * bin_len


def estimate_track_length(speed: np.ndarray, lap_time: float) -> float:
    """lap_time = sum(L/N / v_i)  =>  L = lap_time * N / sum(1/v_i)."""
    if not lap_time:
        return 0.0
    return float(lap_time * N_BINS / np.sum(1.0 / np.clip(speed, 0.5, None)))


# ------------------------------------------------------------------ parsing
def _norm(h: str) -> str:
    h = re.sub(r"[\(\[].*?[\)\]]", "", h.lower())   # drop unit suffixes like "(km/h)" or "[m/s]"
    return re.sub(r"[^a-z0-9]", "", h)


def _find_col(header: list[str], key: str) -> int | None:
    norm = [_norm(h) for h in header]
    for alias in _ALIASES[key]:
        for i, h in enumerate(norm):
            if h == alias:
                return i
    return None


def parse_csv(text: str, lap_time: float | None = None, track_length: float = 0.0) -> Lap:
    """Parse a telemetry CSV (Garage 61 export or SimCoach file) into a Lap."""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if len(lines) < 10:
        raise ValueError("Telemetry CSV has too few rows")
    dialect = csv.Sniffer().sniff(lines[0], delimiters=",;\t")
    rows = list(csv.reader(lines, dialect))
    header, body = rows[0], rows[1:]

    cols = {k: _find_col(header, k) for k in _ALIASES}
    if cols["speed"] is None:
        raise ValueError(f"No speed column found in telemetry CSV. Columns: {header}")

    def col(key):
        i = cols[key]
        if i is None:
            return None
        out = np.empty(len(body))
        for r, row in enumerate(body):
            try:
                out[r] = float(row[i])
            except (ValueError, IndexError):
                out[r] = np.nan
        return out

    data = {k: col(k) for k in _ALIASES}
    valid = ~np.isnan(data["speed"])
    for k, v in data.items():
        if v is not None:
            data[k] = np.nan_to_num(v[valid])

    speed = data["speed"]
    if np.nanmax(speed) > 120:          # 120 m/s = 432 km/h -> value must be km/h
        speed = speed / 3.6

    pct = data["pct"]
    if pct is None and data["dist"] is not None:
        d = data["dist"]
        L = track_length or float(np.max(d))
        pct = d / L
        track_length = track_length or L
    if pct is None:
        pct = np.linspace(0, 1, len(speed), endpoint=False) + 0.5 / len(speed)
    if np.nanmax(pct) > 1.5:            # given in percent
        pct = pct / 100.0

    def unit(a):
        if a is None:
            return np.zeros_like(speed)
        return a / 100.0 if np.nanmax(a) > 1.5 else a

    t = data["time"]
    if t is not None and (np.ptp(t) <= 0 or np.any(np.diff(t) < -1)):
        t = None  # not a usable monotonic lap timer

    return from_samples(
        pct=pct, speed=speed, throttle=unit(data["throttle"]), brake=unit(data["brake"]),
        time=t, lap_time=lap_time, track_length=track_length, dist=data["dist"],
        gear=data["gear"], steer=data["steer"], lat=data["lat"], lon=data["lon"],
        **{k: data[k] for k in EXTRA if data.get(k) is not None},
    )


def fmt_time(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return "--:--.---"
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:06.3f}"
