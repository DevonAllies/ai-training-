"""Consistency trainer: race pace inside a lap-time window.

Pick a target lap time (or let the trainer suggest ~99 % of your recent pace)
and a window (e.g. +/-0.3 s). Every lap lands inside or outside the window;
the overlay shows the streak and the voice calls it.

Faster is fine (default): a lap quicker than the window still counts - race pace
only punishes slow laps. With fuel saving on, a faster lap counts only if it also
hit the fuel target (not bought with extra fuel). Three faster laps in a row move
the target down to your new pace. When a lap falls out, the
trainer compares it with *your own usual lap* (the median of your recent laps,
not the reference) and names the corner and the habit that changed, e.g.
"T3: braked 12 m earlier than usual".

All history is bounded (last 60 laps).
"""

from __future__ import annotations

import statistics

MAX_LAPS = 60
HABITS = (  # metric in the corner report, label, unit, threshold to call it a change
    ("brake_point_m", "braked {v:.0f} m {dir} than usual", "m", 6.0, ("earlier", "later")),
    ("turn_in_m", "turned in {v:.0f} m {dir} than usual", "m", 6.0, ("earlier", "later")),
    ("min_speed_diff_kmh", "apex speed {v:.0f} km/h {dir} than usual", "kmh", 3.0, ("lower", "higher")),
    ("throttle_point_m", "full throttle {v:.0f} m {dir} than usual", "m", 6.0, ("earlier", "later")),
)


class ConsistencyTrainer:
    def __init__(self):
        self.active = False
        self.target: float | None = None      # lap time (s); None = suggest after a few laps
        self.auto_target = True
        self.window = 0.3
        self.goal = 10                         # laps in a row inside the window
        self.streak = 0
        self.best_streak = 0
        self.completed = False
        self.laps: list[dict] = []             # {lap_time, inside, delta, corners:[{metrics}], why}
        self.message = ""
        self.faster_ok = True                  # laps faster than the window count
        self._fast_run: list[float] = []       # consecutive faster laps (to move the target)

    # ------------------------------------------------------------- control
    def start(self, target: float | None = None, window: float | None = None, goal: int | None = None,
              faster_ok: bool | None = None) -> dict:
        self.active = True
        if faster_ok is not None:
            self.faster_ok = bool(faster_ok)
        self._fast_run = []
        self.target = target
        self.auto_target = target is None
        if window:
            self.window = max(0.05, min(3.0, float(window)))
        if goal:
            self.goal = max(2, min(50, int(goal)))
        self.streak = self.best_streak = 0
        self.completed = False
        self.laps = []
        self.message = ("Drive 3 laps - the trainer will set a target from your pace." if self.target is None
                        else f"Target {self.target:.3f}s ±{self.window:.2f}s - {self.goal} laps in a row.")
        return self.status()

    def stop(self) -> None:
        self.active = False

    # ------------------------------------------------------------ per lap
    def add_lap(self, lap_time: float, valid: bool, corners: list[dict] | None,
                fuel_ok: bool | None = None, fuel_over: float | None = None) -> dict | None:
        """Judge a completed lap. Returns the result (or None when not active / lap not counted).
        fuel_ok: in fuel-save mode, whether the lap hit the fuel target (None = not fuel saving)."""
        if not self.active or not valid or lap_time <= 0:
            return None
        corners = corners or []
        rec = {"lap_time": round(lap_time, 3), "corners": [
            {k: c.get(k) for k in ("name", "title", "spoken", "time_lost", "brake_point_m", "turn_in_m",
                                    "min_speed_diff_kmh", "throttle_point_m")} for c in corners]}
        if self.target is None:                # suggest a target once there are 3 laps
            self.laps.append(dict(rec, inside=None, delta=None, why=None))
            self._trim()
            times = [l["lap_time"] for l in self.laps]
            if len(times) >= 3:
                self.target = round(statistics.median(times[-5:]) * 1.0, 3)
                self.message = f"Target set from your pace: {self.target:.3f}s ±{self.window:.2f}s."
            return {"inside": None, "target_set": self.target}
        delta = lap_time - self.target
        faster = delta < -self.window
        retarget = None
        fuel_miss = False
        if faster and self.faster_ok:
            if fuel_ok is False:                   # quicker, but only by burning more fuel
                inside, fuel_miss = False, True
            else:
                inside = True
                self._fast_run.append(lap_time)
                if len(self._fast_run) >= 3:       # you've found real pace: judge against it now
                    retarget = round(statistics.median(self._fast_run[-3:]), 3)
                    self.target = retarget
                    self._fast_run = []
        else:
            inside = abs(delta) <= self.window
            if not faster:
                self._fast_run = []
        if fuel_miss:
            over = f"{fuel_over:.2f} L " if fuel_over else ""
            why = {"corner": None, "spoken": None, "cost": 0.0, "habit": None, "fuel": True,
                   "text": f"Faster, but {over}over the fuel target - it has to be fast on the same fuel."}
        else:
            why = None if inside else self._why(rec)
        self.streak = self.streak + 1 if inside else 0
        self.best_streak = max(self.best_streak, self.streak)
        rec.update(inside=inside, delta=round(delta, 3), why=why, faster=faster and inside)
        self.laps.append(rec)
        self._trim()
        if self.streak >= self.goal and not self.completed:
            self.completed = True
            self.message = f"Goal reached: {self.goal} laps in a row inside ±{self.window:.2f}s!"
        elif retarget:
            self.message = (f"Three faster laps in a row - new target {retarget:.3f}s ±{self.window:.2f}s. "
                            f"{self.streak} in a row.")
        elif inside and faster:
            self.message = f"Faster ({delta:+.2f}s) - still counts. {self.streak} in a row."
        elif inside:
            self.message = f"In the window ({delta:+.2f}s) - {self.streak} in a row."
        else:
            self.message = f"Outside ({delta:+.2f}s)." + (f" {why['text']}" if why else "")
        return {"inside": inside, "delta": delta, "streak": self.streak, "why": why, "completed": self.completed,
                "faster": faster and inside, "retarget": retarget, "fuel_miss": fuel_miss}

    def _trim(self):
        del self.laps[:-MAX_LAPS]

    def _why(self, rec: dict) -> dict | None:
        """Which corner cost this lap, against your own usual lap, and which habit changed."""
        prev = [l for l in self.laps if l.get("inside") is not False][-8:] or self.laps[-8:]
        if len(prev) < 2 or not rec["corners"]:
            return None
        worst = None
        for i, c in enumerate(rec["corners"]):
            usual = [l["corners"][i]["time_lost"] for l in prev
                     if i < len(l["corners"]) and l["corners"][i].get("time_lost") is not None]
            if not usual or c.get("time_lost") is None:
                continue
            cost = c["time_lost"] - statistics.median(usual)
            if worst is None or cost > worst[0]:
                worst = (cost, i, c)
        if worst is None or worst[0] < 0.05:
            return None
        cost, i, c = worst
        habit = None
        for key, text, _, thr, words in HABITS:
            usual = [l["corners"][i].get(key) for l in prev if i < len(l["corners"])]
            usual = [u for u in usual if u is not None]
            if c.get(key) is None or not usual:
                continue
            diff = c[key] - statistics.median(usual)
            if abs(diff) >= thr:
                word = words[0] if diff < 0 else words[1]
                habit = text.format(v=abs(diff), dir=word)
                break
        name = c.get("title") or c.get("name")
        return {"corner": name, "spoken": c.get("spoken") or c.get("name"), "cost": round(cost, 3),
                "habit": habit, "text": f"{name} cost {cost:.2f}s" + (f" - {habit}." if habit else ".")}

    # ------------------------------------------------------------- results
    def score(self) -> int | None:
        judged = [l for l in self.laps if l.get("inside") is not None]
        if len(judged) < 3:
            return None
        inside_pct = 100 * sum(l["inside"] for l in judged) / len(judged)
        sd = statistics.pstdev([l["lap_time"] for l in judged])
        spread_score = max(0.0, 100 - 100 * sd / max(self.window * 2, 0.1))
        return round(0.6 * inside_pct + 0.4 * spread_score)

    def status(self) -> dict:
        judged = [l for l in self.laps if l.get("inside") is not None]
        times = [l["lap_time"] for l in judged]
        return {"active": self.active, "target": self.target, "auto_target": self.auto_target,
                "faster_ok": self.faster_ok,
                "window": self.window, "goal": self.goal, "streak": self.streak, "best_streak": self.best_streak,
                "completed": self.completed, "message": self.message, "score": self.score(),
                "laps": len(judged), "inside": sum(1 for l in judged if l["inside"]),
                "stdev": round(statistics.pstdev(times), 3) if len(times) > 1 else None,
                "recent": [{k: l.get(k) for k in ("lap_time", "inside", "delta", "faster")} | {"why": (l.get("why") or {}).get("text")}
                           for l in self.laps[-12:]]}

    def spoken(self, res: dict) -> str | None:
        if not res or res.get("inside") is None:
            return "Target set" if res and res.get("target_set") else None
        if res.get("completed") and res["streak"] == self.goal:
            return f"Goal reached. {self.goal} laps in the window"
        if res.get("retarget"):
            return f"New pace. Target {res['retarget']:.1f}"
        if res["inside"] and res.get("faster"):
            return f"Faster, still counts. {res['streak']} in a row"
        if res["inside"]:
            return f"In the window, {res['streak']} in a row"
        if res.get("fuel_miss"):
            return "Faster, but over the fuel target"
        w = res.get("why")
        tail = f". {w['spoken']} cost {w['cost']:.1f}" if w else ""
        return f"Outside, {'plus' if res['delta'] > 0 else 'minus'} {abs(res['delta']):.1f}{tail}"
