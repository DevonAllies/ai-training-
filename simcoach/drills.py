"""Drill library: targeted exercises with live feedback.

Each drill works on one corner and judges every attempt on the metric that
matters for that exercise (not just "time lost"):

  time          Match the reference      within the target of the reference, 3 laps in a row
  brake_ladder  Brake-point ladder       brake 5 m later each lap until you reach the reference
                                         - or overshoot, then lock in the last good point (2 laps)
  trail_brake   Trail braking            stay on the brake into the turn like the reference
  min_speed     Minimum speed            apex speed within 2 km/h of the reference
  turn_in       Turn-in point            turn in within 5 m of the reference
  throttle      Throttle pick-up         full throttle as early as the reference, no wheelspin
  consistency   Consistency              3 laps in a row within 0.08 s of each other

The coach picks the drill from the mistake you make most in that corner.
"""

from __future__ import annotations

DRILLS = {
    "time": {"title": "Match the reference", "needed": 3,
             "how": "Drive the corner within the target of the reference, 3 laps in a row."},
    "brake_ladder": {"title": "Brake-point ladder", "needed": 2,
                     "how": "Brake 5 m later every lap. When you overshoot (slow apex or time lost), "
                            "the last good point is your brake point - hit it twice."},
    "trail_brake": {"title": "Trail braking", "needed": 3,
                    "how": "Keep some brake on while you turn in, releasing it gradually towards the apex."},
    "min_speed": {"title": "Minimum speed", "needed": 3,
                  "how": "Release the brake earlier and smoother - carry apex speed within 2 km/h of the reference."},
    "turn_in": {"title": "Turn-in point", "needed": 3,
                "how": "Pick a marker and turn in within 5 m of the reference turn-in point."},
    "throttle": {"title": "Throttle pick-up", "needed": 3,
                 "how": "Squeeze to full throttle as early as the reference, without wheelspin."},
    "consistency": {"title": "Consistency", "needed": 3,
                    "how": "Same line, same brake point - 3 laps in a row within 0.08 s of each other."},
}

DRILL_FOR_ISSUE = {
    "brake_early": "brake_ladder", "no_trail": "trail_brake", "brake_soft": "trail_brake",
    "overslow": "min_speed", "low_min_speed": "min_speed", "understeer": "min_speed",
    "turn_in_late": "turn_in", "turn_in_early": "turn_in", "tight_entry": "turn_in", "wide_apex": "turn_in",
    "late_throttle": "throttle", "low_exit": "throttle", "wheelspin": "throttle", "coasting": "trail_brake",
    "busy_steering": "consistency", "oversteer": "consistency", "abs_heavy": "trail_brake",
}


def drill_for(issue_code: str | None) -> str:
    return DRILL_FOR_ISSUE.get(issue_code or "", "time")


def _m(v: float | None) -> str:
    return "–" if v is None else f"{v:+.0f} m"


def evaluate(kind: str, rep: dict, state: dict, target: float) -> dict:
    """Judge one attempt. Returns {ok, done, text, say, value}; `state` is the drill's memory."""
    lost = rep.get("time_lost") or 0.0
    hist = state.setdefault("history", [])
    if kind == "brake_ladder":
        bp = rep.get("brake_point_m")
        if bp is None:
            return {"ok": False, "done": False, "value": None, "text": "No braking detected in this corner.",
                    "say": None}
        best = state.get("best_time")
        overshoot = (rep.get("min_speed_diff_kmh") or 0) < -4 or (best is not None and lost > best + 0.08) \
            or "overslow" in (rep.get("issues") or [])
        hist.append(round(bp, 1))
        if "target" not in state:                         # first attempt sets the start of the ladder
            state["target"] = min(0.0, round(bp / 5) * 5 + 5)
            state["best_time"] = lost
            return {"ok": False, "done": False, "value": bp,
                    "text": f"Ladder start at {bp:+.0f} m. Next lap brake at {state['target']:+.0f} m "
                            f"({abs(state['target'] - bp):.0f} m later).",
                    "say": f"Brake {abs(state['target'] - bp):.0f} metres later next lap"}
        if "locked" in state:                             # holding the brake point found by the ladder
            ok = abs(bp - state["locked"]) <= 4 and not overshoot
            return {"ok": ok, "done": False, "value": bp,
                    "text": f"Brake point {bp:+.0f} m (yours: {state['locked']:+.0f} m) - "
                            + ("on it." if ok else "hit your marker."),
                    "say": "Good, hold that" if ok else "Hit your brake marker"}
        if overshoot and bp >= state["target"] - 4:
            state["locked"] = state["target"] - 5
            return {"ok": False, "done": False, "value": bp,
                    "text": f"Overshot at {bp:+.0f} m. Your brake point is {state['locked']:+.0f} m "
                            f"(reference 0) - hit it twice.", "say": "Too far. Back off 5 metres"}
        if bp >= state["target"] - 2:
            state["best_time"] = min(state.get("best_time", lost), lost)
            if state["target"] >= 0:                      # reached the reference brake point
                state["locked"] = state["target"]
                return {"ok": True, "done": False, "value": bp,
                        "text": f"Reference brake point reached ({bp:+.0f} m). Hold it.",
                        "say": "That's the reference brake point. Hold it"}
            state["target"] = min(0.0, state["target"] + 5)
            return {"ok": False, "done": False, "value": bp,
                    "text": f"Good: {bp:+.0f} m. Next lap {state['target']:+.0f} m.",
                    "say": "Good. 5 metres later again"}
        return {"ok": False, "done": False, "value": bp,
                "text": f"Braked at {bp:+.0f} m - target {state['target']:+.0f} m.",
                "say": f"Brake later, target {abs(state['target']):.0f} metres early"}
    if kind == "trail_brake":
        v = rep.get("trail_m_diff")
        ok = v is not None and v >= -8
        return {"ok": ok, "done": False, "value": v,
                "text": f"Trail braking {_m(v)} vs the reference - " + ("good." if ok else "stay on the brake longer."),
                "say": "Good trail" if ok else "Trail the brake deeper"}
    if kind == "min_speed":
        v = rep.get("min_speed_diff_kmh")
        ok = v is not None and v >= -2
        return {"ok": ok, "done": False, "value": v, "text": f"Apex speed {v:+.1f} km/h vs reference.",
                "say": "Good speed" if ok else "Carry more speed"}
    if kind == "turn_in":
        v = rep.get("turn_in_m")
        ok = v is not None and abs(v) <= 5
        hint = "" if ok or v is None else (" Turn in earlier." if v > 0 else " Turn in later.")
        return {"ok": ok, "done": False, "value": v, "text": f"Turn-in {_m(v)} vs reference.{hint}",
                "say": "Good turn in" if ok else ("Turn in earlier" if (v or 0) > 0 else "Turn in later")}
    if kind == "throttle":
        v, spin = rep.get("throttle_point_m"), rep.get("wheelspin_m_diff") or 0
        ok = v is not None and v <= 4 and spin < 6
        say = "Good exit" if ok else ("Smoother on the throttle" if spin >= 6 else "Throttle earlier")
        return {"ok": ok, "done": False, "value": v,
                "text": f"Full throttle {_m(v)} vs reference" + (" (wheelspin)" if spin >= 6 else "") + ".",
                "say": say}
    if kind == "consistency":
        hist.append(round(lost, 3))
        del hist[:-10]
        last3 = hist[-3:]
        spread = max(last3) - min(last3) if len(last3) == 3 else None
        done = spread is not None and spread <= 0.08
        return {"ok": done, "done": done, "value": spread,
                "text": (f"Last 3 laps within {spread:.2f}s" if spread is not None else
                         f"{len(last3)} of 3 laps logged") + (" - consistent!" if done else "."),
                "say": "Consistent. Nice" if done else None}
    ok = lost <= target                                   # "time": match the reference
    return {"ok": ok, "done": False, "value": lost, "text": f"{lost:+.2f}s vs reference.",
            "say": None}
