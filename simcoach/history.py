"""Progress across sessions + a practice plan for the next session.

Every driving session (per car/track) is written to
%APPDATA%\\SimCoach\\history\\<id>.json as laps complete: lap times, technique
grades, fuel used and the session report (time lost per corner and the most
common mistake there). The Progress tab reads these to show trends over weeks,
problems that keep coming back, and a concrete plan for the next session.
"""

from __future__ import annotations

import collections
import json
import re
import statistics
from datetime import datetime
from pathlib import Path

from . import drills
from .analysis import ISSUE_LABELS, SHORT_CUES
from .config import app_dir

MAX_LAPS = 300
GRADES = ("braking", "turn_in", "trail_braking", "min_speed", "throttle", "line", "car_control")
GRADE_LABELS = {"braking": "Braking", "turn_in": "Turn-in", "trail_braking": "Trail braking",
                "min_speed": "Minimum speed", "throttle": "Throttle", "line": "Racing line",
                "car_control": "Car control"}


def history_dir() -> Path:
    d = app_dir() / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def new_session_id(track: str, car: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", f"{track}_{car}".lower()).strip("_")[:80]
    return f"{datetime.now():%Y%m%d_%H%M%S}_{slug}"


def save_session(sid: str, track: str, car: str, laps: list[dict], report: dict) -> None:
    valid = [l for l in laps if l.get("valid")]
    data = {
        "id": sid, "date": sid[:15], "track": track, "car": car,
        "laps": laps[-MAX_LAPS:],
        "lap_count": len(laps), "valid_laps": len(valid),
        "best": min((l["lap_time"] for l in valid), default=None),
        "report": {"corners": [{k: c.get(k) for k in ("index", "name", "title", "avg_loss", "best_loss", "spread",
                                                       "main_issue", "main_issue_code", "main_issue_laps", "laps")}
                               for c in report.get("corners", [])],
                   "summary": report.get("summary", []), "focus": report.get("focus", [])},
    }
    grades = collections.defaultdict(list)
    for l in valid:
        for k, v in (l.get("scores") or {}).items():
            if v is not None:
                grades[k].append(v)
    data["grades"] = {k: round(statistics.fmean(v)) for k, v in grades.items()}
    fuel = [l["fuel_used"] for l in valid if l.get("fuel_used")]
    data["fuel_per_lap"] = round(statistics.fmean(fuel), 3) if fuel else None
    (history_dir() / f"{sid}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")


def load_sessions(track: str = "", car: str = "") -> list[dict]:
    out = []
    for p in sorted(history_dir().glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if track and not _similar(d.get("track", ""), track):
            continue
        if car and d.get("car") and not _similar(d.get("car", ""), car):
            continue
        out.append(d)
    return out


def combos() -> list[dict]:
    seen: dict[tuple, dict] = {}
    for d in load_sessions():
        key = (d.get("track", ""), d.get("car", ""))
        e = seen.setdefault(key, {"track": key[0], "car": key[1], "sessions": 0, "best": None})
        e["sessions"] += 1
        if d.get("best") and (e["best"] is None or d["best"] < e["best"]):
            e["best"] = d["best"]
    return sorted(seen.values(), key=lambda e: -e["sessions"])


def progress(track: str, car: str = "") -> dict:
    sessions = [s for s in load_sessions(track, car) if s.get("valid_laps")]
    out = {"track": track, "car": car, "sessions": [], "recurring": [], "improved": [], "pb": None}
    if not sessions:
        return out
    pb = None
    for s in sessions:
        pb = s["best"] if pb is None or (s["best"] and s["best"] < pb) else pb
        out["sessions"].append({"id": s["id"], "date": s["date"], "best": s["best"], "laps": s["valid_laps"],
                                "grades": s.get("grades", {}), "fuel_per_lap": s.get("fuel_per_lap"),
                                "pb_so_far": pb})
    out["pb"] = pb
    # problems that keep coming back: (corner, issue) in a session's top 3, in >= 2 sessions
    counter: collections.Counter = collections.Counter()
    for s in sessions:
        ranked = sorted(s["report"]["corners"], key=lambda c: c.get("avg_loss") or 0, reverse=True)[:3]
        for c in ranked:
            if c.get("main_issue") and (c.get("avg_loss") or 0) > 0.05:
                counter[(c.get("title") or c.get("name"), c["main_issue"])] += 1
    out["recurring"] = [{"corner": k[0], "issue": k[1], "sessions": n}
                        for k, n in counter.most_common(5) if n >= 2]
    # corners that improved: first vs latest session average loss
    if len(sessions) >= 2:
        first = {c["name"]: c for c in sessions[0]["report"]["corners"]}
        last = {c["name"]: c for c in sessions[-1]["report"]["corners"]}
        for name, c in last.items():
            f = first.get(name)
            if f and f.get("avg_loss") is not None and c.get("avg_loss") is not None:
                gain = f["avg_loss"] - c["avg_loss"]
                if abs(gain) >= 0.05:
                    out["improved"].append({"corner": c.get("title") or name, "gain": round(gain, 3)})
        out["improved"].sort(key=lambda x: -x["gain"])
    return out


def practice_plan(report: dict, grades: dict | None = None, minutes: int = 45) -> list[dict]:
    """A concrete plan for the next session from the latest session report."""
    plan = [{"title": "Warm-up", "minutes": 5,
             "detail": "3-4 laps building to ~98 % pace. Use the live delta only - no drills yet."}]
    corners = sorted([c for c in report.get("corners", []) if (c.get("avg_loss") or 0) > 0.05],
                     key=lambda c: c["avg_loss"], reverse=True)
    for c in corners[:2]:
        code = c.get("main_issue_code") or ""
        cue = SHORT_CUES.get(code, "")
        label = ISSUE_LABELS.get(code, c.get("main_issue") or "losing time")
        target = max(0.05, round((c["avg_loss"] - (c.get("best_loss") or 0)) / 2 + (c.get("best_loss") or 0), 2))
        kind = drills.drill_for(code)
        d = drills.DRILLS[kind]
        step = {"title": f"{d['title']} drill: {c.get('title') or c.get('name')}", "minutes": 12,
                "detail": f"{label} (avg {c['avg_loss']:+.2f}s). Focus: {cue}. {d['how']}"
                          + (f" Goal: within {target:.2f}s of the reference 3 laps in a row." if kind == "time" else "")}
        if c.get("index") is not None:
            step["drill"] = {"corner": c["index"], "kind": kind, "target": target}
        plan.append(step)
    if grades:
        scored = [(k, v) for k, v in grades.items() if k in GRADES and v is not None]
        if scored:
            k, v = min(scored, key=lambda kv: kv[1])
            if v < 90:
                plan.append({"title": f"Technique focus: {GRADE_LABELS[k]}", "minutes": 8,
                             "detail": f"Your weakest grade ({v}/100). Concentrate on {GRADE_LABELS[k].lower()} in "
                                       f"every corner for 5 laps; check the grade after each lap."})
    spreads = [c.get("spread") or 0 for c in report.get("corners", [])]
    if spreads and max(spreads) > 0.1:
        plan.append({"title": "Consistency run", "minutes": 8,
                     "detail": "5 consecutive laps at 99 % - aim for every lap within ±0.3 s. "
                               "Consistency first, then speed."})
    plan.append({"title": "Push laps", "minutes": 5, "action": "optimal",
                 "detail": "3 flying laps against your optimal lap (Laps → Build my optimal lap). "
                           "Put the drills together."})
    used = sum(p["minutes"] for p in plan)
    if used > minutes:                         # too much for the session: scale every step down
        for p in plan:
            p["minutes"] = max(3, round(p["minutes"] * minutes / used))
        used = sum(p["minutes"] for p in plan)
    if used != minutes:                        # put the rounding difference on the longest step
        longest = max(plan, key=lambda p: p["minutes"])
        longest["minutes"] = max(3, longest["minutes"] + minutes - used)
    return plan
