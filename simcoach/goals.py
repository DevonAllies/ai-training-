"""Weekly training goal and streak.

Goal types (Settings / Progress tab):
  minutes   time on track per week (default 180 = 3 hours)
  sessions  driving sessions per week
  laps      completed laps per week

Weeks are ISO weeks (Monday-Sunday, local time). The streak counts consecutive
weeks with the goal met, ending with the current week if it's already met or
the previous week otherwise - so an unfinished current week never breaks it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

GOAL_TYPES = {"minutes": "minutes on track", "sessions": "sessions", "laps": "laps"}


def _session_date(s: dict) -> date | None:
    d = str(s.get("date") or s.get("id") or "")[:8]
    try:
        return datetime.strptime(d, "%Y%m%d").date()
    except ValueError:
        return None


def session_amounts(s: dict) -> dict:
    """minutes / laps for one saved session (drive time if recorded, else the sum of lap times)."""
    laps = s.get("laps") or []
    seconds = s.get("drive_s")
    if not seconds:
        seconds = sum(l.get("lap_time") or 0 for l in laps)
    return {"minutes": (seconds or 0) / 60.0, "laps": s.get("lap_count", len(laps)), "sessions": 1}


def week_key(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return iso[0], iso[1]


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_summary(sessions: list[dict], goal_type: str = "minutes", goal_value: float = 180,
                   today: date | None = None, weeks_back: int = 8, live: dict | None = None) -> dict:
    """Totals per week, this week's progress and the streak.

    live: amounts from the session in progress that isn't saved yet ({"minutes", "laps", "sessions"}).
    """
    goal_type = goal_type if goal_type in GOAL_TYPES else "minutes"
    goal_value = max(1.0, float(goal_value or 1))
    today = today or date.today()
    totals: dict[tuple[int, int], dict] = {}
    for s in sessions:
        d = _session_date(s)
        if d is None or d > today:
            continue
        k = week_key(d)
        t = totals.setdefault(k, {"minutes": 0.0, "laps": 0, "sessions": 0})
        for key, v in session_amounts(s).items():
            t[key] += v
    cur = week_key(today)
    if live:
        t = totals.setdefault(cur, {"minutes": 0.0, "laps": 0, "sessions": 0})
        for key in ("minutes", "laps", "sessions"):
            t[key] += live.get(key, 0) or 0

    def met(k):
        return totals.get(k, {}).get(goal_type, 0) >= goal_value

    # streak: consecutive met weeks ending this week (if met) or last week
    def prev_week(k):
        y, w = k
        d = date.fromisocalendar(y, w, 1) - timedelta(days=7)
        return week_key(d)
    k = cur if met(cur) else prev_week(cur)
    streak = 0
    while met(k):
        streak += 1
        k = prev_week(k)
    # best streak over all history
    best, run = 0, 0
    if totals:
        first = min(totals)
        k = first
        guard = 0
        while k <= cur and guard < 1000:
            run = run + 1 if met(k) else 0
            best = max(best, run)
            y, w = k
            k = week_key(date.fromisocalendar(y, w, 1) + timedelta(days=7))
            guard += 1
    weeks = []
    k = cur
    for _ in range(weeks_back):
        y, w = k
        t = totals.get(k, {"minutes": 0.0, "laps": 0, "sessions": 0})
        weeks.append({"week": f"{y}-W{w:02d}", "start": date.fromisocalendar(y, w, 1).isoformat(),
                      "minutes": round(t["minutes"], 1), "laps": int(t["laps"]), "sessions": int(t["sessions"]),
                      "value": round(t[goal_type], 1), "met": met(k)})
        k = prev_week(k)
    weeks.reverse()
    now_val = totals.get(cur, {}).get(goal_type, 0)
    days_left = 6 - today.weekday()
    return {"goal_type": goal_type, "goal_label": GOAL_TYPES[goal_type], "goal_value": goal_value,
            "this_week": round(now_val, 1), "progress": round(min(1.0, now_val / goal_value), 3),
            "met": met(cur), "remaining": round(max(0.0, goal_value - now_val), 1), "days_left": days_left,
            "streak": streak, "best_streak": max(best, streak), "weeks": weeks}
