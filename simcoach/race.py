"""Race pace, stints, endurance planning and fuel saving.

Stint tracking (live)
  laps per stint, lap-time drop-off (s/lap), consistency, fuel per lap, laps of
  fuel left, laps to go, fuel needed to finish, stops needed and the pit window.

Endurance planner
  race length (time or laps) + lap time + fuel per lap + tank size + pit loss ->
  number of stops, laps per stint, fuel per stop, and what saving fuel buys you:
  one stop fewer, or an extra lap per stint.

Fuel saving without losing (much) time - lift and coast
  Lifting off before a braking zone saves the fuel you'd burn at full throttle,
  and costs little time because you'd be braking soon anyway. How much time it
  costs depends on the car's coasting deceleration and the speed there. Both are
  measured from your own lap: the coast-down rate is fitted to the samples where
  you were off both pedals, the fuel flow to the fuel channel at full throttle.
  Each braking zone is simulated for lift distances of 25-300 m, and the planner
  picks the cheapest combination (most fuel per tenth lost) that reaches your
  target saving per lap. All figures are estimates and labelled as such.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

import numpy as np

from .analysis import _brake_on, detect_corners
from .lap import N_BINS, Lap

FUEL_DENSITY = 0.75          # kg per litre (iRacing reports FuelUsePerHour in kg/h)


# ------------------------------------------------------------------ stints (live)
@dataclass
class LapRecord:
    lap: int
    lap_time: float
    fuel_used: float | None
    valid: bool
    pit: bool
    stint: int


@dataclass
class RaceTracker:
    laps: list[LapRecord] = field(default_factory=list)
    stint: int = 1
    max_laps: int = 500

    def add(self, lap_no: int, lap_time: float, fuel_used: float | None, valid: bool, pit: bool) -> None:
        self.laps.append(LapRecord(lap_no, lap_time, fuel_used, valid, pit, self.stint))
        if pit:                                    # lap that ended in / passed through the pits
            self.stint += 1
        del self.laps[:-self.max_laps]

    def reset(self) -> None:
        self.laps.clear()
        self.stint = 1

    def green_laps(self, stint: int | None = None) -> list[LapRecord]:
        return [l for l in self.laps if l.valid and not l.pit and (stint is None or l.stint == stint)]

    def fuel_per_lap(self) -> float | None:
        vals = [l.fuel_used for l in self.green_laps() if l.fuel_used and l.fuel_used > 0][-5:]
        return round(statistics.fmean(vals), 3) if vals else None

    def avg_lap(self) -> float | None:
        vals = [l.lap_time for l in self.green_laps()][-5:]
        return statistics.fmean(vals) if vals else None

    def status(self, fuel_level: float | None, time_remain: float, laps_remain: float,
               tank: float | None, current_lap: int) -> dict:
        cur = self.green_laps(self.stint)
        times = [l.lap_time for l in cur]
        out = {"stint": self.stint, "stint_laps": len([l for l in self.laps if l.stint == self.stint]),
               "stint_best": min(times) if times else None,
               "stint_avg": round(statistics.fmean(times), 3) if times else None,
               "consistency": round(statistics.pstdev(times), 3) if len(times) > 1 else None,
               "dropoff": None, "fuel_level": fuel_level, "fuel_per_lap": self.fuel_per_lap(),
               "laps_of_fuel": None, "laps_to_go": None, "fuel_to_finish": None, "stops_needed": None,
               "pit_window": None, "tank": tank,
               "laps": [{"lap": l.lap, "lap_time": round(l.lap_time, 3), "fuel": l.fuel_used,
                         "valid": l.valid, "pit": l.pit, "stint": l.stint} for l in self.laps[-40:]]}
        if len(times) >= 3:                        # lap-time trend inside the stint (tyre wear, fuel burn)
            slope = float(np.polyfit(np.arange(len(times)), times, 1)[0])
            out["dropoff"] = round(slope, 3)
        fpl, avg = out["fuel_per_lap"], self.avg_lap()
        if fpl and fuel_level is not None:
            out["laps_of_fuel"] = round(fuel_level / fpl, 2)
        if laps_remain is not None and laps_remain >= 0 and laps_remain < 30000:
            out["laps_to_go"] = float(laps_remain)
        elif time_remain is not None and time_remain > 0 and avg:
            out["laps_to_go"] = float(math.ceil(time_remain / avg))   # timed race: finish the lap in progress
        if out["laps_to_go"] is not None and fpl and fuel_level is not None:
            need = out["laps_to_go"] * fpl - fuel_level
            out["fuel_to_finish"] = round(max(0.0, need), 2)
            if tank:
                out["stops_needed"] = int(math.ceil(max(0.0, need) / tank)) if need > 0 else 0
                if need > 0:
                    laps_per_tank = math.floor(tank / fpl)
                    last_possible = current_lap + int(fuel_level // fpl)
                    earliest = current_lap + max(0, int(math.ceil(out["laps_to_go"] - laps_per_tank * out["stops_needed"])))
                    out["pit_window"] = {"open": min(earliest, last_possible), "close": last_possible}
        return out


# ------------------------------------------------------------------ endurance plan
def plan_race(avg_lap: float, fuel_per_lap: float, tank: float, race_time_s: float | None = None,
              race_laps: int | None = None, pit_loss_s: float = 60.0, refuel_rate_lps: float | None = None,
              lift_cost_per_litre: float | None = None) -> dict:
    """Stint plan + what fuel saving would buy.

    lift_cost_per_litre: seconds lost per litre saved by lift-and-coast (from lift_plan),
    used to estimate whether saving fuel beats making the extra stop.
    """
    if avg_lap <= 0 or fuel_per_lap <= 0 or tank <= 0:
        raise ValueError("Lap time, fuel per lap and tank size must be positive.")
    if race_laps:
        total = int(race_laps)
    elif race_time_s:
        total = int(math.ceil(race_time_s / avg_lap))
    else:
        raise ValueError("Give the race length in laps or minutes.")
    per_tank = max(1, math.floor(tank / fuel_per_lap))
    stints_n = int(math.ceil(total / per_tank))
    stops = stints_n - 1
    base = total // stints_n
    extra = total % stints_n
    stints = [base + (1 if i < extra else 0) for i in range(stints_n)]
    fuel_stops = [round(min(tank, laps * fuel_per_lap + 0.5 * fuel_per_lap), 1) for laps in stints[1:]]
    out = {"total_laps": total, "laps_per_tank": per_tank, "stops": stops, "stints": stints,
           "fuel_per_stop": fuel_stops, "fuel_per_lap": fuel_per_lap, "tank": tank,
           "pit_loss_s": pit_loss_s, "options": []}
    if refuel_rate_lps:
        out["refuel_time_s"] = [round(f / refuel_rate_lps, 1) for f in fuel_stops]

    def option(name: str, target_fpl: float, saves_stop: bool, extra_laps: int = 0):
        save = fuel_per_lap - target_fpl
        if save <= 0:
            return
        o = {"name": name, "target_fuel_per_lap": round(target_fpl, 3), "save_per_lap": round(save, 3),
             "save_pct": round(100 * save / fuel_per_lap, 1)}
        if lift_cost_per_litre is not None:
            cost_lap = save * lift_cost_per_litre
            o["time_cost_per_lap_s"] = round(cost_lap, 3)
            o["time_cost_race_s"] = round(cost_lap * total, 1)
            if saves_stop:
                o["net_gain_s"] = round(pit_loss_s - cost_lap * total, 1)
        o["saves_stop"] = saves_stop
        if extra_laps:
            o["extra_laps_per_stint"] = extra_laps
        out["options"].append(o)

    if stops >= 1:                                     # one stop fewer
        need_per_tank = math.ceil(total / stops)
        option(f"One stop fewer ({stops - 1} stops)", tank / need_per_tank, True)
    option("One extra lap per tank", tank / (per_tank + 1), False, 1)
    return out


# ------------------------------------------------------------------ lift & coast
def coast_model(lap: Lap) -> tuple[float, float, bool]:
    """Fit coast-down deceleration a(v) = c0 + c2*v^2 (m/s^2) to off-pedal samples.

    Returns (c0, c2, measured). Falls back to typical race-car values if the lap
    has too little coasting to fit.
    """
    v = lap.speed
    bin_m = (lap.track_length or 4000.0) / N_BINS
    dv = np.diff(np.r_[v, v[0]])
    dt = bin_m / np.maximum(v, 1.0)
    a = -dv / dt
    m = (lap.throttle < 0.05) & (lap.brake < 0.05) & (v > 15) & (a > 0) & (a < 15)
    if m.sum() >= 15:
        X = np.c_[np.ones(m.sum()), v[m] ** 2]
        coef, *_ = np.linalg.lstsq(X, a[m], rcond=None)
        c0, c2 = float(coef[0]), float(coef[1])
        if c2 > 0 and c0 > -1:
            return max(c0, 0.2), c2, True
    return 0.8, 0.00045, False


def full_throttle_flow(lap: Lap, fuel_per_lap: float | None = None) -> float | None:
    """Fuel flow at full throttle in litres per second."""
    bin_m = (lap.track_length or 4000.0) / N_BINS
    dt = bin_m / np.maximum(lap.speed, 1.0)
    if lap.fuel is not None:
        burn = -np.diff(np.r_[lap.fuel, lap.fuel[-1]])
        m = (lap.throttle > 0.95) & (burn >= 0) & (burn < 1)
        if m.sum() > 20 and dt[m].sum() > 0:
            return float(burn[m].sum() / dt[m].sum())
    if fuel_per_lap:
        weighted = float(np.sum(np.clip(lap.throttle, 0, 1) * dt))
        return fuel_per_lap / weighted if weighted > 0 else None
    return None


def _simulate_lift(lap: Lap, bb: int, d_m: float, c0: float, c2: float, flow: float) -> tuple[float, float, int]:
    """Lift `d_m` metres before brake bin `bb`: (seconds lost, litres saved, lift bin)."""
    bin_m = (lap.track_length or 4000.0) / N_BINS
    n = max(1, int(round(d_m / bin_m)))
    start = bb - n
    v = float(lap.speed[start % N_BINS])
    lost = saved = 0.0
    i = start
    while i < bb + 400:                          # coast until we meet the original speed trace
        j = i % N_BINS
        v_orig = float(lap.speed[j])
        if i >= bb and v <= v_orig:              # back on the original braking curve
            break
        v_eff = min(v, v_orig) if i >= bb else v
        lost += bin_m * (1.0 / max(v_eff, 1.0) - 1.0 / max(v_orig, 1.0))
        saved += flow * float(np.clip(lap.throttle[j], 0, 1)) * bin_m / max(v_eff, 1.0)
        a = c0 + c2 * v * v
        v = math.sqrt(max(v * v - 2 * a * bin_m, 1.0))
        i += 1
    return max(lost, 0.0), max(saved, 0.0), start % N_BINS


def lift_plan(lap: Lap, target_save_per_lap: float | None = None, fuel_per_lap: float | None = None,
              corners=None) -> dict:
    """Best lift-and-coast points to save fuel at the lowest time cost."""
    flow = full_throttle_flow(lap, fuel_per_lap)
    if not flow:
        return {"available": False, "reason": "No fuel data for this lap yet - drive a full lap first."}
    c0, c2, measured = coast_model(lap)
    corners = corners if corners is not None else detect_corners(lap)
    bin_m = (lap.track_length or 4000.0) / N_BINS
    zones = []
    for idx, c in enumerate(corners):
        bb = _brake_on(lap.brake, max(0, c.start - 15), c.apex)
        if bb is None:
            continue
        prev_apex = corners[idx - 1].apex - (N_BINS if idx == 0 else 0)   # wrap for the first corner
        room = bb - prev_apex - 15                  # bins of straight after the previous corner
        # only straights where you're flat out before braking
        pre = np.take(lap.throttle, np.arange(bb - 40, bb), mode="wrap")
        if room < 3 or float(np.mean(pre > 0.9)) < 0.8:
            continue
        opts = []
        for d in range(25, 325, 25):
            if d / bin_m > room:                    # don't lift before the previous corner's exit
                break
            lost, saved, lift_bin = _simulate_lift(lap, bb, d, c0, c2, flow)
            opts.append({"d_m": d, "lost_s": round(lost, 4), "saved_l": round(saved, 4), "lift_bin": lift_bin})
        if opts:
            zones.append({"index": idx, "corner": c.name, "title": c.title, "brake_bin": bb,
                          "speed_kmh": round(float(lap.speed[bb]) * 3.6), "options": opts})
    # greedy: add 25 m steps where they buy the most fuel per second lost
    chosen = {z["index"]: 0 for z in zones}         # index into options (+1), 0 = no lift
    total_save = total_lost = 0.0
    steps = []
    while True:
        if target_save_per_lap is not None and total_save >= target_save_per_lap:
            break
        best = None
        for z in zones:
            k = chosen[z["index"]]
            if k >= len(z["options"]):
                continue
            nxt = z["options"][k]
            prev = z["options"][k - 1] if k else {"lost_s": 0.0, "saved_l": 0.0}
            d_save, d_lost = nxt["saved_l"] - prev["saved_l"], nxt["lost_s"] - prev["lost_s"]
            if d_save <= 1e-6:
                continue
            eff = d_save / max(d_lost, 1e-4)
            if best is None or eff > best[0]:
                best = (eff, z, d_save, d_lost)
        if best is None or (target_save_per_lap is None and len(steps) >= 2 * len(zones)):
            break
        _, z, d_save, d_lost = best
        chosen[z["index"]] += 1
        total_save += d_save
        total_lost += d_lost
        steps.append(z["index"])
    plan = []
    for z in zones:
        k = chosen[z["index"]]
        if k:
            o = z["options"][k - 1]
            plan.append({"index": z["index"], "corner": z["corner"], "title": z["title"], "lift_m": o["d_m"],
                         "lift_bin": o["lift_bin"], "brake_bin": z["brake_bin"], "saved_l": o["saved_l"],
                         "lost_s": o["lost_s"], "speed_kmh": z["speed_kmh"]})
    plan.sort(key=lambda p: p["index"])
    reached = target_save_per_lap is None or total_save >= target_save_per_lap - 1e-6
    return {"available": True, "plan": plan, "total_saved_l": round(total_save, 3),
            "total_lost_s": round(total_lost, 3), "target_l": target_save_per_lap, "reached": reached,
            "cost_per_litre_s": round(total_lost / total_save, 3) if total_save > 0 else None,
            "flow_lps": round(flow, 4), "coast_model": {"c0": round(c0, 3), "c2": round(c2, 6),
                                                        "measured": measured},
            "zones": [{k: z[k] for k in ("index", "corner", "title", "speed_kmh")} for z in zones]}


def extra_lap_target(fuel_level: float, fuel_per_lap: float, laps_planned: int | None = None) -> dict:
    """Fuel saving needed per lap to stretch the tank by one lap."""
    laps_now = fuel_level / fuel_per_lap if fuel_per_lap else 0.0
    goal = (math.floor(laps_now) + 1) if laps_planned is None else laps_planned + 1
    target = fuel_level / goal if goal else fuel_per_lap
    return {"laps_now": round(laps_now, 2), "laps_goal": goal, "target_fuel_per_lap": round(target, 3),
            "save_per_lap": round(max(0.0, fuel_per_lap - target), 3)}


def lift_cue_points(plan: dict) -> dict[int, int]:
    """corner index -> lift bin, for the overlay's LIFT cue."""
    return {p["index"]: p["lift_bin"] for p in (plan.get("plan") or [])}


