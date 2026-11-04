"""Race prep from a teammate's multi-lap .ibt (a practice stint, a race, an endurance run).

From every lap in the file (in driving order) it works out:

* **Race pace** - typical lap (median of clean laps within 3 % of the best),
  best lap, consistency (spread, laps within 0.5 s) and pace drop-off per stint.
* **Fuel** - fuel per lap (median of clean laps), its range, fuel per stint, and
  refuelling / pit laps.
* **Fuel saving** - their most fuel-efficient clean lap, what it saved and what it
  cost in time vs their typical lap, and *where* they lift and coast on it compared
  with their fastest lap (metres earlier off the throttle per corner).

The fastest and the fuel-saving laps are saved as normal laps, so either can be
your live reference. The prep feeds the endurance planner (lap time, fuel per
lap) and the fuel training (target fuel per lap = theirs).

Saved as JSON in the SimCoach folder (newest 20 kept).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import re
import statistics
from pathlib import Path

import numpy as np

from .analysis import detect_corners
from .config import app_dir, laps_dir
from .lap import GRID, Lap, fmt_time
from .race import pace_stats

log = logging.getLogger(__name__)

KEEP = 20


def preps_dir() -> Path:
    d = app_dir() / "preps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slope(xs, ys):
    if len(xs) < 4:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return None if den == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def _off_throttle_m(lap: Lap, brake_bin: int, look_bins: int, bin_m: float) -> float | None:
    """Distance (m) from the last full-throttle point to the braking point before a corner."""
    lo = max(0, brake_bin - look_bins)
    thr = lap.throttle[lo:brake_bin + 1]
    full = np.flatnonzero(thr > 0.9)
    if not len(full):
        return None
    return float((brake_bin - (lo + full[-1])) * bin_m)


def _brake_bin(lap: Lap, start: int, apex: int) -> int | None:
    seg = lap.brake[start:apex + 1]
    on = np.flatnonzero(seg > 0.1)
    return int(start + on[0]) if len(on) else None


def lift_points(fast: Lap, eco: Lap) -> list[dict]:
    """Where the fuel-saving lap comes off the throttle earlier than the fastest lap."""
    L = fast.track_length or eco.track_length or 4000.0
    bin_m = L / len(GRID)
    look = int(400 / bin_m)                          # look up to 400 m before the braking point
    out = []
    for c in detect_corners(fast):
        bf, be = _brake_bin(fast, c.start, c.apex), _brake_bin(eco, c.start, c.apex)
        if bf is None:
            continue
        a = _off_throttle_m(fast, bf, look, bin_m)
        b = _off_throttle_m(eco, be if be is not None else bf, look, bin_m)
        if a is None or b is None:
            continue
        earlier = b - a + ((bf - be) * bin_m if be is not None else 0.0)   # lift earlier and/or brake later
        lost = float((eco.time[c.end] - eco.time[c.start]) - (fast.time[c.end] - fast.time[c.start]))
        if earlier > 12:
            out.append({"corner": c.title or c.name, "index": c.index, "lift_earlier_m": round(earlier),
                        "coast_m": round(b), "brake_later_m": round((be - bf) * bin_m) if be is not None else None,
                        "time_lost_s": round(lost, 3)})
    return out


def build_prep(info: dict, laps: list[Lap], driver: str | None = None) -> dict:
    """Race prep from all laps of one .ibt (any order - sorted by lap number here)."""
    laps = sorted(laps, key=lambda l: (l.meta.get("lap") or 0))
    rows = []
    for l in laps:
        fuel = l.meta.get("fuel_used")
        refuel = fuel is not None and fuel < 0
        rows.append({"lap": l.meta.get("lap"), "lap_time": round(l.lap_time, 3), "valid": bool(l.meta.get("valid", True)),
                     "pit": bool(l.meta.get("pit")) or refuel,
                     "fuel_used": None if (fuel is None or refuel) else round(float(fuel), 3)})
    clean = [r for r in rows if r["valid"] and not r["pit"]]
    pace = pace_stats([{"lap_time": r["lap_time"], "fuel_used": r["fuel_used"], "clean": True} for r in clean])
    out: dict = {"driver": driver or info.get("driver") or "Teammate", "track": info.get("track", ""),
                 "track_config": info.get("track_config", ""), "car": info.get("car", ""),
                 "created": _dt.datetime.now().isoformat(timespec="minutes"),
                 "laps": rows, "lap_count": len(rows), "clean_laps": len(clean), "pace": pace}
    times = [r["lap_time"] for r in clean]
    if len(times) >= 3 and pace.get("lap_time"):
        typ = pace["lap_time"]
        out["consistency"] = {"spread": round(statistics.pstdev([t for t in times if t <= typ + 2]), 3),
                              "within_pct": round(100 * sum(abs(t - typ) <= 0.5 for t in times) / len(times))}
    # stints (split after pit laps)
    stints, cur = [], []
    for i, r in enumerate(rows):
        cur.append(r)
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if r["pit"] and nxt is not None and not nxt["pit"]:
            stints.append(cur)
            cur = []
    if cur:
        stints.append(cur)
    st_out = []
    for i, s in enumerate(stints):
        c = [r for r in s if r["valid"] and not r["pit"]]
        if c:
            med = statistics.median(r["lap_time"] for r in c)
            steady = [r for r in c if r["lap_time"] - med <= 1.0]
            slope = _slope([r["lap"] for r in steady], [r["lap_time"] for r in steady])
        else:
            slope = None
        f = [r["fuel_used"] for r in c if r["fuel_used"]]
        st_out.append({"stint": i + 1, "laps": len(s), "avg": round(statistics.fmean(r["lap_time"] for r in c), 3) if c else None,
                       "dropoff": round(slope, 3) if slope is not None else None,
                       "fuel_per_lap": round(statistics.fmean(f), 3) if f else None})
    out["stints"] = st_out
    fuel = [r["fuel_used"] for r in clean if r["fuel_used"]]
    out["fuel"] = {"per_lap": pace.get("fuel_per_lap"), "min": min(fuel) if fuel else None,
                   "max": max(fuel) if fuel else None, "laps": len(fuel)}
    # fastest and most fuel-efficient laps (eco = least fuel among clean laps within 2 % of the best)
    by_lap = {l.meta.get("lap"): l for l in laps}
    fast_row = min(clean, key=lambda r: r["lap_time"]) if clean else None
    eco_row = None
    if fuel and fast_row:
        pool = [r for r in clean if r["fuel_used"] and r["lap_time"] <= fast_row["lap_time"] * 1.02]
        eco_row = min(pool, key=lambda r: r["fuel_used"]) if pool else None
    out["fastest"] = fast_row
    out["eco"] = None
    if eco_row and pace.get("fuel_per_lap") and eco_row["fuel_used"] < pace["fuel_per_lap"] - 0.01:
        out["eco"] = dict(eco_row, saved_l=round(pace["fuel_per_lap"] - eco_row["fuel_used"], 3),
                          cost_s=round(eco_row["lap_time"] - pace["lap_time"], 3))
        try:
            out["eco"]["lift_points"] = lift_points(by_lap[fast_row["lap"]], by_lap[eco_row["lap"]])
        except Exception:                            # never let the extra analysis break the prep
            log.exception("lift point analysis failed")
            out["eco"]["lift_points"] = []
    # fuel vs time trade-off across clean laps (how much time per litre they gave up)
    if len(fuel) >= 5 and pace.get("lap_time"):
        pts = [(r["fuel_used"], r["lap_time"]) for r in clean
               if r["fuel_used"] and r["lap_time"] <= pace["lap_time"] + 1.5]
        sl = _slope([p[0] for p in pts], [p[1] for p in pts])
        out["fuel"]["s_per_litre"] = round(-sl, 2) if sl is not None and sl < 0 else None
    out["takeaways"] = _takeaways(out)
    return out


def _takeaways(p: dict) -> list[str]:
    t, who = [], p["driver"]
    pace = p["pace"]
    if pace.get("lap_time"):
        t.append(f"{who}'s race pace: {fmt_time(pace['lap_time'])} typical (best {fmt_time(pace['best'])}) "
                 f"over {pace['laps']} clean laps.")
    if p.get("consistency"):
        c = p["consistency"]
        t.append(f"Consistency: {c['within_pct']}% of laps within 0.5 s (spread ±{c['spread']:.2f} s).")
    if p["fuel"].get("per_lap"):
        f = p["fuel"]
        t.append(f"Fuel: {f['per_lap']:.2f} L per lap (range {f['min']:.2f}–{f['max']:.2f} L over {f['laps']} laps).")
    for s in p["stints"]:
        if s.get("dropoff") is not None and s["dropoff"] > 0.05:
            t.append(f"Stint {s['stint']}: pace dropped {s['dropoff']:.2f} s per lap (tyres).")
    e = p.get("eco")
    if e:
        t.append(f"Fuel-saving lap {e['lap']}: {e['fuel_used']:.2f} L ({e['saved_l']:.2f} L less) for "
                 f"{e['cost_s']:+.2f} s vs typical pace.")
        for lp in (e.get("lift_points") or [])[:4]:
            t.append(f"  {lp['corner']}: off the throttle {lp['lift_earlier_m']} m earlier "
                     f"({lp['time_lost_s']:+.2f} s).")
    return t


# ---------------------------------------------------------------- storage
def save_prep(prep: dict, laps: list[Lap]) -> dict:
    """Store the prep and save its fastest / fuel-saving laps as normal lap files."""
    now = _dt.datetime.now()
    safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{prep['driver']}_{prep['track']}_{prep['car']}").strip("_")[:60]
    pid = f"{now:%Y%m%d_%H%M%S}_{safe}"
    prep["id"] = pid
    by_lap = {l.meta.get("lap"): l for l in laps}
    files = {}
    for key in ("fastest", "eco"):
        row = prep.get(key)
        lap = by_lap.get(row["lap"]) if row else None
        if lap is None:
            continue
        lap = Lap(**{k: getattr(lap, k) for k in lap.__dataclass_fields__})     # don't change the caller's lap
        lap.label = f"{prep['driver']} {fmt_time(lap.lap_time)}" + (" fuel-save" if key == "eco" else "")
        lap.meta = dict(lap.meta, driver=prep["driver"], prep=pid, prep_role=key)
        name = f"{now:%Y%m%d_%H%M%S}_prep_{key}_{safe}_{lap.lap_time:.3f}.csv"
        lap.save(laps_dir() / name)
        files[key] = name
    prep["files"] = files
    (preps_dir() / f"{pid}.json").write_text(json.dumps(prep), encoding="utf-8")
    for p in sorted(preps_dir().glob("*.json"))[:-KEEP]:
        p.unlink(missing_ok=True)
    return prep


def list_preps() -> list[dict]:
    out = []
    for p in sorted(preps_dir().glob("*.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({k: d.get(k) for k in ("id", "driver", "track", "track_config", "car", "created", "lap_count",
                                          "clean_laps")} | {"lap_time": d["pace"].get("lap_time"),
                                                            "fuel_per_lap": d["fuel"].get("per_lap")})
    return out


def load_prep(pid: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_]+", pid or ""):
        raise ValueError("bad id")
    return json.loads((preps_dir() / f"{pid}.json").read_text(encoding="utf-8"))
