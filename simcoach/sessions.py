"""Import and analyse Garage 61 session exports (.xlsx).

Garage 61 can export an event/session to Excel. The export contains an
"Overview" sheet (car, track, driver, date) and one sheet per session
("Session - Practice", "Session - Qualify", "Session - Race", ...) with a row
per lap: lap time, clean flag, pit flags, conditions, fuel and sector times.

There is no per-metre telemetry in this export, so the analysis is sector
based: best sectors, theoretical best lap, consistency, and where the most
time is left on the table. Best sectors are also used as live targets in the
overlay when you drive the same car/track.
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import timedelta
from pathlib import Path

from .config import app_dir


def sessions_dir() -> Path:
    d = app_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _seconds(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, timedelta):
        return v.total_seconds()
    if isinstance(v, (int, float)):
        # Excel durations stored as a fraction of a day
        return float(v) * 86400 if 0 < v < 1 else float(v)
    s = str(v).strip()
    m = re.fullmatch(r"(?:(\d+):)?(\d+(?:\.\d+)?)", s)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_g61_export(path: str | Path) -> dict:
    """Parse a Garage 61 Excel export into a plain dict."""
    import openpyxl  # imported lazily: only needed for imports

    wb = openpyxl.load_workbook(path, data_only=True)
    info: dict = {"source_file": Path(path).name}
    if "Overview" in wb.sheetnames:
        cells = [c for row in wb["Overview"].iter_rows(values_only=True) for c in row if c not in (None, "")]
        keys = {"Car": "car", "Track": "track", "Driver": "driver", "Session date": "date",
                "In-sim date": "sim_date"}
        for i, c in enumerate(cells[:-1]):
            if isinstance(c, str) and c.strip() in keys:
                info[keys[c.strip()]] = str(cells[i + 1])
            elif isinstance(c, str) and c.startswith("Exported by:"):
                info["exported_by"] = c.split(":", 1)[1].strip()

    sessions = []
    for name in wb.sheetnames:
        if not name.lower().startswith("session"):
            continue
        rows = list(wb[name].iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(h).strip() if h is not None else "" for h in rows[0]]
        idx = {h: i for i, h in enumerate(header)}
        sector_cols = sorted((h for h in header if re.fullmatch(r"Sector \d+", h)),
                             key=lambda h: int(h.split()[1]))

        def g(row, col):
            i = idx.get(col)
            return row[i] if i is not None and i < len(row) else None

        laps = []
        for row in rows[1:]:
            if not row or all(v in (None, "") for v in row):
                continue
            lt = _seconds(g(row, "Lap time"))
            if lt is None:
                continue
            laps.append({
                "run": int(_num(g(row, "Run")) or 0),
                "lap": int(_num(g(row, "Lap")) or 0),
                "lap_time": lt,
                "started_at": g(row, "Started at"),
                "driver": g(row, "Driver"),
                "clean": bool(_num(g(row, "Clean"))),
                "pit_in": bool(_num(g(row, "Pit in"))),
                "pit_out": bool(_num(g(row, "Pit out"))),
                "fuel_level": _num(g(row, "Fuel level")),
                "fuel_used": _num(g(row, "Fuel used")),
                "track_temp": _num(g(row, "Track temp")),
                "air_temp": _num(g(row, "Air temperature")),
                "sectors": [_seconds(g(row, c)) for c in sector_cols],
            })
        title = name.split("-", 1)[1].strip() if "-" in name else name
        sessions.append({"name": title, "sector_count": len(sector_cols), "laps": laps})
    info["sessions"] = sessions
    return info


# ----------------------------------------------------------------- analysis
def _is_timed(lap: dict, n_sectors: int) -> bool:
    """A full flying lap: every sector present, not an in/out lap."""
    return (not lap["pit_in"] and not lap["pit_out"] and n_sectors > 0
            and all(s is not None for s in lap["sectors"]))


def analyse_session(sess: dict) -> dict:
    n = sess["sector_count"]
    laps = sess["laps"]
    timed = [l for l in laps if _is_timed(l, n)]
    clean = [l for l in timed if l["clean"]]
    pool = clean or timed
    if pool:
        # Ignore slow outliers (incidents, traffic, safety car): the usual 107% rule.
        fastest = min(l["lap_time"] for l in pool)
        pool = [l for l in pool if l["lap_time"] <= fastest * 1.07]
    out = {"name": sess["name"], "sector_count": n, "laps": len(laps),
           "timed_laps": len(timed), "clean_laps": len(clean), "used_laps": len(pool),
           "lap_list": [{"lap": l["lap"], "run": l["run"], "lap_time": round(l["lap_time"], 3),
                         "clean": l["clean"], "pit_in": l["pit_in"], "pit_out": l["pit_out"],
                         "used": l in pool,
                         "sectors": [None if x is None else round(x, 3) for x in l["sectors"]]}
                        for l in laps]}
    if not pool:
        out["note"] = "No complete flying laps with all sector times in this session."
        return out

    best_lap = min(pool, key=lambda l: l["lap_time"])
    best_sectors = [min(l["sectors"][i] for l in pool) for i in range(n)]
    theoretical = sum(best_sectors)
    times = [l["lap_time"] for l in pool]

    sector_stats = []
    for i in range(n):
        vals = [l["sectors"][i] for l in pool]
        avg = statistics.fmean(vals)
        sector_stats.append({
            "sector": i + 1,
            "best": round(best_sectors[i], 3),
            "best_lap": next(l["lap"] for l in pool if l["sectors"][i] == best_sectors[i]),
            "avg": round(avg, 3),
            "spread": round(statistics.pstdev(vals), 3) if len(vals) > 1 else 0.0,
            "avg_loss": round(avg - best_sectors[i], 3),             # avg time left vs best
            "best_lap_loss": round(best_lap["sectors"][i] - best_sectors[i], 3),
        })

    ranked = sorted(sector_stats, key=lambda s: s["avg_loss"], reverse=True)
    tips = []
    if ranked and ranked[0]["avg_loss"] > 0.05:
        a = ranked[0]
        tips.append(f"Sector {a['sector']} costs you the most: on average {a['avg_loss']:.2f}s slower "
                    f"than your best there (lap {a['best_lap']}). Study what you did on that lap.")
    if len(ranked) > 1 and ranked[1]["avg_loss"] > 0.05:
        b = ranked[1]
        tips.append(f"Next: sector {b['sector']}, {b['avg_loss']:.2f}s on average vs your best.")
    gain = best_lap["lap_time"] - theoretical
    if gain > 0.05:
        tips.append(f"Theoretical best {fmt(theoretical)} is {gain:.2f}s quicker than your fastest lap - "
                    f"putting your best sectors together is realistic pace.")
    stdev = statistics.pstdev(times) if len(times) > 1 else 0.0
    if len(times) > 2:
        if stdev < 0.4:
            tips.append(f"Very consistent: lap times vary by only ±{stdev:.2f}s.")
        else:
            worst = max(sector_stats, key=lambda s: s["spread"])
            tips.append(f"Lap times vary by ±{stdev:.2f}s; sector {worst['sector']} is the least "
                        f"consistent (±{worst['spread']:.2f}s). Consistency there first.")

    out.update({
        "best_lap": {"lap": best_lap["lap"], "lap_time": round(best_lap["lap_time"], 3),
                     "sectors": [round(s, 3) for s in best_lap["sectors"]]},
        "theoretical_best": round(theoretical, 3),
        "best_sectors": [round(s, 3) for s in best_sectors],
        "average_lap": round(statistics.fmean(times), 3),
        "stdev": round(stdev, 3),
        "sectors": sector_stats,
        "focus_sectors": [s["sector"] for s in ranked if s["avg_loss"] > 0.05][:2],
        "tips": tips,
    })
    return out


def analyse_export(data: dict) -> dict:
    sessions = [analyse_session(s) for s in data["sessions"]]
    # Overall best sectors across all sessions with the same sector layout
    n = max((s["sector_count"] for s in data["sessions"]), default=0)
    best = None
    for s in sessions:
        bs = s.get("best_sectors")
        if bs and len(bs) == n:
            best = bs if best is None else [min(a, b) for a, b in zip(best, bs)]
    return {
        "car": data.get("car"), "track": data.get("track"), "driver": data.get("driver"),
        "date": data.get("date"), "sessions": sessions,
        "best_sectors": best, "theoretical_best": round(sum(best), 3) if best else None,
    }


def fmt(seconds: float | None) -> str:
    if not seconds:
        return "-:--.---"
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:06.3f}"


# ------------------------------------------------------------------ storage
def import_file(path: str | Path) -> str:
    data = parse_g61_export(path)
    if not data["sessions"]:
        raise ValueError("No 'Session - …' sheets found. Is this a Garage 61 session export?")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{data.get('date', '')}_{data.get('track', '')}_{data.get('car', '')}")
    slug = slug.strip("_")[:120] or Path(path).stem
    (sessions_dir() / f"{slug}.json").write_text(json.dumps(data, default=str, indent=1), encoding="utf-8")
    return slug


def list_imports() -> list[dict]:
    out = []
    for p in sorted(sessions_dir().glob("*.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"id": p.stem, "car": d.get("car"), "track": d.get("track"), "date": d.get("date"),
                    "driver": d.get("driver"),
                    "sessions": [s["name"] for s in d.get("sessions", [])]})
    return out


def load_import(slug: str) -> dict:
    p = (sessions_dir() / f"{slug}.json").resolve()
    if p.parent != sessions_dir().resolve() or not p.exists():
        raise FileNotFoundError(slug)
    return json.loads(p.read_text(encoding="utf-8"))
