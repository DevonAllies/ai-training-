"""Race report: what happened in a race, built while you drive.

* **Result** - start / finish position (overall and in class), positions per lap.
* **Pace & consistency** - best and typical lap, spread, laps within 0.5 s of
  your typical pace, the laps that went wrong.
* **Stints** - laps, pace, pace drop-off per lap (tyre wear) and fuel per stint.
* **Fuel** - per lap, average, spare at the finish, fuel-save laps on target.
* **Tyres** - iRacing only sends tyre wear and temperatures while you're in
  your pit stall, so wear per stint is measured at your stops.
* **Racecraft** - clean passes, let-bys, defending, incidents, traffic time.

Saved as JSON in the SimCoach folder (newest 50 races kept).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import re
import statistics
from pathlib import Path

from .config import app_dir

log = logging.getLogger(__name__)

MAX_LAPS = 400
KEEP_REPORTS = 50
CORNERS = ("LF", "RF", "LR", "RR")


def races_dir() -> Path:
    d = app_dir() / "races"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slope(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 4:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return None if den == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


class RaceRecorder:
    def __init__(self):
        self.active = False
        self.id: str | None = None
        self.meta: dict = {}
        self.laps: list[dict] = []
        self.tyres: list[dict] = []          # one snapshot per pit stop
        self._stall: dict | None = None      # latest tyre reading during the current stop
        self.start_pos: dict | None = None
        self.last_pos: dict | None = None
        self.fuel_end: float | None = None
        self.finished = False                # chequered flag seen (SessionState >= 5)

    def start(self, meta: dict) -> None:
        now = _dt.datetime.now()
        safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{meta.get('track', '')}_{meta.get('car', '')}").strip("_")[:60]
        self.__init__()
        self.active = True
        self.id = f"{now:%Y%m%d_%H%M%S}_{safe}"
        self.meta = dict(meta, date=now.isoformat(timespec="minutes"))

    # ------------------------------------------------------------ live input
    def position(self, pos: int | None, class_pos: int | None) -> None:
        if not self.active or not pos or pos <= 0:
            return
        p = {"pos": int(pos), "class_pos": int(class_pos) if class_pos and class_pos > 0 else None}
        if self.start_pos is None:
            self.start_pos = p
        self.last_pos = p

    def session_state(self, state: int | None) -> None:
        if self.active and state is not None and state >= 5 and self.laps:
            self.finished = True

    def tyre_reading(self, tyres: dict | None, lap: int) -> None:
        """Called while in the pit stall (the only time iRacing sends tyre data)."""
        if not self.active:
            return
        if tyres:
            self._stall = {"lap": lap, "tyres": tyres}
        elif self._stall is not None:             # left the stall: keep the last reading of the stop
            self.tyres.append(self._stall)
            del self.tyres[:-20]
            self._stall = None

    def add_lap(self, rec: dict) -> None:
        if not self.active:
            return
        self.laps.append(dict(rec, pos=(self.last_pos or {}).get("pos"),
                              class_pos=(self.last_pos or {}).get("class_pos")))
        del self.laps[:-MAX_LAPS]
        if rec.get("fuel_level") is not None:
            self.fuel_end = rec["fuel_level"]

    # ---------------------------------------------------------------- report
    def report(self, racecraft: dict | None = None) -> dict:
        laps = self.laps
        out: dict = {"id": self.id, **self.meta, "laps": laps, "lap_count": len(laps), "finished": self.finished,
                     "start": self.start_pos, "finish": self.last_pos, "takeaways": []}
        racing = [l for l in laps if l.get("valid") and not l.get("pit") and not l.get("out_lap")]
        times = [l["lap_time"] for l in racing]
        pace: dict = {"best": min(times) if times else None}
        if len(times) >= 3:
            med = statistics.median(times)
            within = [t for t in times if abs(t - med) <= 0.5]
            off = [l for l in racing if l["lap_time"] - med > 1.0]
            pace.update(typical=round(med, 3), spread=round(statistics.pstdev(times), 3),
                        within_pct=round(100 * len(within) / len(times)),
                        bad_laps=[{"lap": l["lap"], "lost": round(l["lap_time"] - med, 2)} for l in off][:10])
        out["pace"] = pace

        # stints (split at pit laps)
        stints, cur = [], []                     # a stint ends after the in-lap / out-lap pair
        for i, l in enumerate(laps):
            cur.append(l)
            nxt = laps[i + 1] if i + 1 < len(laps) else None
            if l.get("pit") and nxt is not None and not nxt.get("pit"):
                stints.append(cur)
                cur = []
        if cur:
            stints.append(cur)
        st_out = []
        for i, s in enumerate(stints):
            clean = [l for l in s if l.get("valid") and not l.get("pit") and not l.get("out_lap")
                     and not l.get("in_traffic")]
            fuel = [l["fuel_used"] for l in s if l.get("fuel_used") and not l.get("pit")]
            # tyre trend: leave out mistakes (laps > 1 s off the stint's typical pace)
            med = statistics.median(l["lap_time"] for l in clean) if clean else 0.0
            steady = [l for l in clean if l["lap_time"] - med <= 1.0]
            slope = _slope([l["lap"] for l in steady], [l["lap_time"] for l in steady])
            st_out.append({"stint": i + 1, "laps": len(s), "from": s[0]["lap"], "to": s[-1]["lap"],
                           "avg": round(statistics.fmean(l["lap_time"] for l in clean), 3) if clean else None,
                           "best": min((l["lap_time"] for l in clean), default=None),
                           "dropoff": round(slope, 3) if slope is not None else None,
                           "fuel_per_lap": round(statistics.fmean(fuel), 3) if fuel else None})
        out["stints"] = st_out

        fuel = [l["fuel_used"] for l in laps if l.get("fuel_used") and not l.get("pit")]
        saved = [l for l in laps if l.get("fuel_ok") is not None]
        out["fuel"] = {"avg": round(statistics.fmean(fuel), 3) if fuel else None,
                       "min": min(fuel) if fuel else None, "max": max(fuel) if fuel else None,
                       "total": round(sum(fuel), 2) if fuel else None,
                       "spare": round(self.fuel_end, 2) if self.fuel_end is not None else None,
                       "save_laps": len(saved), "save_ok": sum(1 for l in saved if l["fuel_ok"])}

        # tyres: wear per stint from pit-stop readings
        tyre_out = []
        prev_lap = 0
        for snap in self.tyres:
            n = max(1, snap["lap"] - prev_lap)
            row = {"lap": snap["lap"], "laps": n, "corners": {}}
            for c in CORNERS:
                t = (snap["tyres"] or {}).get(c) or {}
                wear = t.get("wear")
                row["corners"][c] = {
                    "wear_left": round(100 - min(wear), 1) if wear else None,     # % tread used (worst point)
                    "per_lap": round((100 - min(wear)) / n, 2) if wear else None,
                    "wear": wear, "temp": t.get("temp")}
            tyre_out.append(row)
            prev_lap = snap["lap"]
        out["tyres"] = tyre_out
        out["racecraft"] = racecraft

        # positions
        pos = [l["pos"] for l in laps if l.get("pos")]
        out["positions"] = pos
        out["takeaways"] = self._takeaways(out)
        return out

    @staticmethod
    def _takeaways(r: dict) -> list[str]:
        t = []
        s, f = r.get("start"), r.get("finish")
        if s and f:
            d = s["pos"] - f["pos"]
            cls = f" (class P{s['class_pos']} → P{f['class_pos']})" if s.get("class_pos") and f.get("class_pos") else ""
            t.append(f"Started P{s['pos']}, finished P{f['pos']}{cls}: "
                     + (f"{d} place{'s' if abs(d) != 1 else ''} gained." if d > 0 else
                        f"{-d} place{'s' if abs(d) != 1 else ''} lost." if d < 0 else "held position."))
        p = r["pace"]
        if p.get("within_pct") is not None:
            t.append(f"Consistency: {p['within_pct']}% of racing laps within 0.5 s of your typical "
                     f"{p['typical']:.3f} (spread ±{p['spread']:.2f} s).")
            if p.get("bad_laps"):
                worst = max(p["bad_laps"], key=lambda b: b["lost"])
                t.append(f"{len(p['bad_laps'])} lap{'s' if len(p['bad_laps']) > 1 else ''} more than 1 s off - "
                         f"worst lap {worst['lap']} (+{worst['lost']:.1f} s).")
        for st in r["stints"]:
            if st.get("dropoff") is not None and st["dropoff"] > 0.05:
                t.append(f"Stint {st['stint']}: pace dropped {st['dropoff']:.2f} s per lap - tyres going off "
                         f"(or fuel/track). Look after the rears on exits.")
        fu = r["fuel"]
        if fu.get("spare") is not None and fu.get("avg") and not r.get("finished"):
            t.append(f"Fuel in the tank now: {fu['spare']:.1f} L ({fu['spare'] / fu['avg']:.1f} laps at "
                     f"{fu['avg']:.2f} L per lap).")
        elif fu.get("spare") is not None and fu.get("avg"):
            spare_laps = fu["spare"] / fu["avg"]
            if spare_laps > 1.5:
                t.append(f"Finished with {fu['spare']:.1f} L spare ({spare_laps:.1f} laps) - you could start "
                         f"lighter or push harder.")
            elif spare_laps < 0.3:
                t.append(f"Only {fu['spare']:.1f} L left at the end - cutting it fine.")
        if fu.get("save_laps"):
            t.append(f"Fuel saving: {fu['save_ok']} of {fu['save_laps']} laps on target.")
        for row in r["tyres"]:
            worst = max(((c, v["per_lap"]) for c, v in row["corners"].items() if v["per_lap"] is not None),
                        key=lambda x: x[1], default=None)
            if worst:
                t.append(f"Tyres at the lap {row['lap']} stop: {worst[0]} wore most ({worst[1]:.2f} % per lap).")
        rc = r.get("racecraft")
        if rc:
            c = rc.get("counts") or {}
            def pl(k, word):
                v = c.get(k, 0)
                return f"{v} {word}{'' if v == 1 else ('es' if word.endswith('s') else 's')}"
            parts = [pl("clean_pass", "clean pass"), pl("clean_letby", "clean let-by")]
            if c.get("defended"):
                parts.append(f"defended {c['defended']}x")
            t.append("Racecraft: " + ", ".join(parts) + f", {rc.get('incidents', 0)}x incidents"
                     + (f" - score {rc['score']}." if rc.get("score") is not None else "."))
            if rc.get("traffic_lost_avg"):
                t.append(f"Traffic cost you {rc['traffic_lost_avg']:.2f} s per traffic lap.")
        return t

    # ----------------------------------------------------------------- disk
    def save(self, racecraft: dict | None = None) -> None:
        if not self.active or not self.laps or not self.id:
            return
        try:
            (races_dir() / f"{self.id}.json").write_text(json.dumps(self.report(racecraft)), encoding="utf-8")
            files = sorted(races_dir().glob("*.json"))
            for p in files[:-KEEP_REPORTS]:
                p.unlink(missing_ok=True)
        except OSError:
            log.warning("could not save race report")


def list_reports() -> list[dict]:
    out = []
    for p in sorted(races_dir().glob("*.json"), reverse=True):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"id": r.get("id") or p.stem, "date": r.get("date"), "track": r.get("track"), "car": r.get("car"),
                    "laps": r.get("lap_count"), "finish": r.get("finish")})
    return out


def load_report(rid: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_]+", rid or ""):
        raise ValueError("bad id")
    return json.loads((races_dir() / f"{rid}.json").read_text(encoding="utf-8"))
