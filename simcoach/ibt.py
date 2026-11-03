"""Reader for iRacing .ibt telemetry files - the file a teammate sends you.

iRacing writes an .ibt file per session when disk telemetry is on (press
Alt+L in the car, or enable it permanently; files land in
Documents\\iRacing\\telemetry\\). The format is the published iRacing SDK
layout:

    header (112 bytes) | disk sub-header (32 bytes) | var headers (144 bytes each)
    | session-info YAML | fixed-size sample records (one per tick, usually 60 Hz)

Records are read through a numpy memmap, so large files don't need to fit in RAM.
Each complete lap in the file becomes a Lap on SimCoach's distance grid.

iRacing's .blap / .olap ghost files are a private, undocumented format and are
deliberately not parsed: guessing their layout could produce a wrong reference.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .lap import Lap, from_samples, fmt_time

_TYPES = {0: ("S1", 1), 1: ("?", 1), 2: ("<i4", 4), 3: ("<u4", 4), 4: ("<f4", 4), 5: ("<f8", 8)}


class IBTError(ValueError):
    pass


@dataclass
class IBTLap:
    number: int
    lap_time: float
    valid: bool
    lap: Lap


def _read_header(buf: bytes) -> dict:
    if len(buf) < 144:
        raise IBTError("File is too small to be an iRacing .ibt telemetry file")
    (ver, status, tick_rate, si_update, si_len, si_offset, num_vars, var_hdr_offset,
     num_buf, buf_len) = struct.unpack_from("<10i", buf, 0)
    var_bufs = [struct.unpack_from("<2i", buf, 48 + i * 16) for i in range(4)]
    start_date, start_time, end_time, lap_count, record_count = struct.unpack_from("<qddii", buf, 112)
    if ver not in (1, 2) or num_vars <= 0 or num_vars > 10000 or buf_len <= 0 or tick_rate <= 0:
        raise IBTError("Not an iRacing .ibt telemetry file (unrecognised header)")
    return {"ver": ver, "tick_rate": tick_rate, "si_len": si_len, "si_offset": si_offset,
            "num_vars": num_vars, "var_hdr_offset": var_hdr_offset, "buf_len": buf_len,
            "data_offset": var_bufs[0][1], "record_count": record_count, "lap_count": lap_count}


def read_ibt(path: str | Path) -> tuple[dict, dict, np.ndarray, str]:
    """Return (header, vars, records memmap, session-info YAML text)."""
    path = Path(path)
    with open(path, "rb") as f:
        head = f.read(144)
        h = _read_header(head)
        f.seek(h["var_hdr_offset"])
        raw = f.read(144 * h["num_vars"])
        if len(raw) < 144 * h["num_vars"]:
            raise IBTError("Telemetry file is truncated (variable table incomplete)")
        f.seek(h["si_offset"])
        session_yaml = f.read(max(0, h["si_len"])).split(b"\0", 1)[0].decode("latin-1")
    variables = {}
    fields = []
    for i in range(h["num_vars"]):
        t, off, count = struct.unpack_from("<3i", raw, i * 144)
        name = raw[i * 144 + 16: i * 144 + 48].split(b"\0", 1)[0].decode("latin-1")
        if t not in _TYPES or not name:
            continue
        variables[name] = (t, off, count)
        dt, _ = _TYPES[t]
        fields.append((name, dt if count == 1 else (dt, (count,)), off))
    size = path.stat().st_size
    n = h["record_count"]
    max_n = (size - h["data_offset"]) // h["buf_len"]
    if n <= 0 or n > max_n:                       # some files leave the count at 0 - derive it
        n = max_n
    if n <= 0:
        raise IBTError("Telemetry file contains no samples")
    dtype = np.dtype({"names": [f[0] for f in fields], "formats": [f[1] for f in fields],
                      "offsets": [f[2] for f in fields], "itemsize": h["buf_len"]})
    records = np.memmap(path, dtype=dtype, mode="r", offset=h["data_offset"], shape=(n,))
    return h, variables, records, session_yaml


def session_details(session_yaml: str) -> dict:
    """Track/car/driver from the session-info YAML (tolerant of iRacing's YAML quirks)."""
    out = {"track": "", "track_config": "", "track_length": 0.0, "car": "", "driver": ""}
    try:
        import yaml
        d = yaml.safe_load(session_yaml) or {}
        wk = d.get("WeekendInfo", {}) or {}
        drv = d.get("DriverInfo", {}) or {}
        idx = drv.get("DriverCarIdx", 0)
        me = next((x for x in drv.get("Drivers", []) or [] if x.get("CarIdx") == idx), {})
        out.update(track=str(wk.get("TrackDisplayName") or ""), track_config=str(wk.get("TrackConfigName") or ""),
                   car=str(me.get("CarScreenName") or ""), driver=str(me.get("UserName") or ""))
        tl = str(wk.get("TrackLength") or "")
    except Exception:
        def grab(key):
            m = re.search(rf"^\s*{key}:\s*(.+?)\s*$", session_yaml, re.M)
            return m.group(1).strip() if m else ""
        out.update(track=grab("TrackDisplayName"), track_config=grab("TrackConfigName"),
                   car=grab("CarScreenName"), driver=grab("UserName"))
        tl = grab("TrackLength")
    m = re.search(r"([\d.]+)\s*(km|mi)", tl)
    if m:
        out["track_length"] = float(m.group(1)) * (1000 if m.group(2) == "km" else 1609.344)
    return out


def _col(records, variables, name, default=0.0):
    if name not in variables:
        return np.full(len(records), default, dtype=float)
    return np.array(records[name], dtype=float)      # copy - never hold a view into the memmap


def extract_laps(path: str | Path) -> tuple[dict, list[IBTLap]]:
    """All complete laps in the file (fastest first), plus session details."""
    h, v, rec, si = read_ibt(path)
    try:
        return _extract(rec, v, si)
    finally:                                         # release the file (Windows can't delete it otherwise)
        mm = getattr(rec, "_mmap", None)
        del rec
        if mm is not None:
            mm.close()


def _extract(rec, v, si) -> tuple[dict, list[IBTLap]]:
    info = session_details(si)
    for need in ("LapDistPct", "Speed", "SessionTime", "Lap"):
        if need not in v:
            raise IBTError(f"Telemetry file has no '{need}' channel - cannot extract laps")
    pct = _col(rec, v, "LapDistPct")
    t = _col(rec, v, "SessionTime")
    lapno = _col(rec, v, "Lap").astype(int)
    speed = _col(rec, v, "Speed")
    thr, brk = _col(rec, v, "Throttle"), _col(rec, v, "Brake")
    gear, steer = _col(rec, v, "Gear"), _col(rec, v, "SteeringWheelAngle")
    lat, lon = _col(rec, v, "Lat"), _col(rec, v, "Lon")
    pit = _col(rec, v, "OnPitRoad")
    surf = _col(rec, v, "PlayerTrackSurface", 3)
    extras = {k: _col(rec, v, name) for k, name in (("yaw", "YawRate"), ("latacc", "LatAccel"), ("rpm", "RPM"),
                                                    ("abs", "BrakeABSactive"), ("fuel", "FuelLevel"))
              if name in v}
    on_track = _col(rec, v, "IsOnTrack", 1)

    # line crossings: LapDistPct wraps from ~1 to ~0 while driving
    wraps = np.flatnonzero((pct[:-1] > 0.9) & (pct[1:] < 0.1) & (on_track[1:] > 0))
    crossings = []
    for i in wraps:
        p0, p1 = pct[i], pct[i + 1]
        span = (1 - p0) + p1
        f = (1 - p0) / span if span > 0 else 0.0
        crossings.append((i + 1, t[i] + f * (t[i + 1] - t[i])))

    laps: list[IBTLap] = []
    for (a, t_start), (b, t_end) in zip(crossings, crossings[1:]):
        seg = slice(a, b)
        lap_time = t_end - t_start
        if b - a < 50 or lap_time <= 10:
            continue
        p = pct[seg]
        if p.max() - p.min() < 0.97:                 # not a full lap (e.g. reset, tow)
            continue
        valid = not (pit[seg].any() or (surf[seg] == 0).any())
        ss = np.concatenate([[t_start], t[seg], [t_end]]) - t_start
        pp = np.concatenate([[0.0], p, [1.0]])

        def ext(a_):                                # pad channels for the two line points
            x = a_[seg]
            return np.concatenate([[x[0]], x, [x[-1]]])
        lap = from_samples(pp, ext(speed), np.clip(ext(thr), 0, 1), np.clip(ext(brk), 0, 1), time=ss,
                           lap_time=lap_time, track_length=info["track_length"], gear=ext(gear),
                           steer=ext(steer), lat=ext(lat), lon=ext(lon),
                           **{k: ext(a_) for k, a_ in extras.items()})
        lap.time = lap.time * (lap_time / lap.lap_time) if lap.lap_time > 0 else lap.time
        number = int(np.bincount(lapno[seg] - lapno[seg].min()).argmax() + lapno[seg].min())
        lap.label = f"{info['driver'] or 'Teammate'} {fmt_time(lap_time)}"
        lap.meta = {"track": " - ".join(x for x in (info["track"], info["track_config"]) if x),
                    "car": info["car"], "driver": info["driver"], "source": "ibt", "lap": number,
                    "valid": valid}
        if "fuel" in extras:
            lap.meta["fuel_used"] = round(float(extras["fuel"][a] - extras["fuel"][b - 1]), 3)
        laps.append(IBTLap(number, lap_time, valid, lap))
    laps.sort(key=lambda x: (not x.valid, x.lap_time))
    return info, laps


def write_ibt(path: str | Path, channels: dict[str, np.ndarray], session_yaml: str, tick_rate: int = 60) -> None:
    """Write a minimal .ibt (used by the tests to round-trip the reader)."""
    names = list(channels)
    types = []
    for n in names:
        a = channels[n]
        types.append(5 if a.dtype == np.float64 else 2 if a.dtype.kind in "iu" else 1 if a.dtype == bool else 4)
    offs, o = [], 0
    for tp in types:
        offs.append(o)
        o += _TYPES[tp][1]
    buf_len = o
    n_rec = len(next(iter(channels.values())))
    var_hdr_offset = 144
    si = session_yaml.encode("latin-1") + b"\0"
    si_offset = var_hdr_offset + 144 * len(names)
    data_offset = si_offset + len(si)
    with open(path, "wb") as f:
        hdr = struct.pack("<10i", 2, 1, tick_rate, 1, len(si), si_offset, len(names), var_hdr_offset, 1, buf_len)
        hdr += b"\0" * 8
        hdr += struct.pack("<2i8x", 0, data_offset) + b"\0" * 48
        hdr += struct.pack("<qddii", 0, 0.0, 0.0, 0, n_rec)
        f.write(hdr)
        for n, tp, off in zip(names, types, offs):
            f.write(struct.pack("<3i?3x", tp, off, 1, False) + n.encode().ljust(32, b"\0") + b"\0" * 96)
        f.write(si)
        dtype = np.dtype({"names": names, "formats": [_TYPES[t][0] for t in types], "offsets": offs,
                          "itemsize": buf_len})
        arr = np.zeros(n_rec, dtype=dtype)
        for n in names:
            arr[n] = channels[n]
        f.write(arr.tobytes())
