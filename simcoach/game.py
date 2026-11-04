"""Training game: XP, levels, combos, a daily challenge and badges.

Training is repetitive on purpose, so this layer gives the repetition a score:

* **XP** for the things that make you faster - clean laps, drill attempts on
  target, finished drills and plan steps ("quests"), laps inside the
  consistency window, fuel-save laps on target, the weekly goal.
* **Combo** - attempts/laps on target in a row multiply the XP (x2 from 3,
  x3 from 6, x4 from 10). A miss resets the combo, like any arcade game.
* **Levels** with titles from Rookie to Alien.
* **Daily challenge** - one task per day, picked from the date, bonus XP.
* **Badges** for milestones (first drill, brake ladder, 10-lap streak...).

The state is a small JSON file in the app folder, written at most once per lap
(or on a badge), and every list in it is capped so it can't grow forever.
"""

from __future__ import annotations

import collections
import datetime as _dt
import json
import logging
import threading
import time
from pathlib import Path

from .config import app_dir

log = logging.getLogger(__name__)

XP = {
    "clean_lap": 10,
    "session_best": 25,
    "beat_reference": 60,
    "drill_hit": 6,
    "drill_done": 50,
    "plan_step": 40,
    "plan_complete": 150,
    "cons_lap": 8,
    "cons_goal": 80,
    "fuel_lap": 15,
    "weekly_goal": 200,
    "daily": 75,
}

TITLES = ["Rookie", "Club Racer", "Amateur", "Pro-Am", "Semi-Pro", "Pro", "Works Driver", "Champion",
          "Legend", "Alien"]

BADGES = {
    "first_lap": ("First lap", "Drive your first clean lap with SimCoach"),
    "first_drill": ("Drill sergeant", "Finish your first corner drill"),
    "ladder": ("Late braker", "Finish a brake ladder drill"),
    "combo5": ("On a roll", "Combo of 5"),
    "combo10": ("Unstoppable", "Combo of 10"),
    "cons5": ("Metronome", "5 laps in a row inside the consistency window"),
    "cons10": ("Robot", "10 laps in a row inside the consistency window"),
    "plan": ("Quest complete", "Finish every step of a practice plan"),
    "fuel5": ("Fuel whisperer", "5 fuel-save laps on target in one session"),
    "beat_ref": ("Giant killer", "Beat your reference lap"),
    "week": ("Committed", "Reach your weekly training goal"),
    "daily3": ("Daily grinder", "Finish 3 daily challenges"),
    "laps100": ("Century", "100 clean laps"),
    "level5": ("Moving up", "Reach level 5"),
}

# Daily challenges: (id, text, event counted, how many)
DAILIES = [
    ("hits", "Hit the drill target 8 times", "drill_hit", 8),
    ("clean", "Drive 10 clean laps", "clean_lap", 10),
    ("cons", "5 laps inside the consistency window", "cons_lap", 5),
    ("steps", "Finish 2 practice plan steps", "plan_step", 2),
    ("drills", "Finish 2 corner drills", "drill_done", 2),
    ("combo", "Reach a combo of 6", "combo", 6),
    ("fuel", "3 fuel-save laps on target", "fuel_lap", 3),
]

MAX_FEED = 25
MAX_LOG = 200


def level_for(xp: int) -> dict:
    """Level n needs 100 + 75*(n-1) more XP than level n-1."""
    lvl, need, floor = 1, 100, 0
    while xp >= floor + need:
        floor += need
        lvl += 1
        need = 100 + 75 * (lvl - 1)
    return {"level": lvl, "title": TITLES[min(len(TITLES) - 1, (lvl - 1) // 2)],
            "into": xp - floor, "need": need, "pct": round(100 * (xp - floor) / need)}


def combo_mult(combo: int) -> int:
    return 4 if combo >= 10 else 3 if combo >= 6 else 2 if combo >= 3 else 1


def daily_for(day: _dt.date) -> dict:
    cid, text, event, goal = DAILIES[day.toordinal() % len(DAILIES)]
    return {"id": cid, "text": text, "event": event, "goal": goal}


class TrainingGame:
    def __init__(self, path: Path | None = None, today=None):
        self.path = path or (app_dir() / "game.json")
        self._today = today or _dt.date.today
        self.lock = threading.RLock()
        self.xp = 0
        self.badges: dict[str, str] = {}            # id -> date earned
        self.stats: dict[str, int] = collections.Counter()
        self.daily_day = ""
        self.daily_count = 0
        self.daily_done = False
        self.dailies_done = 0
        self.best_combo = 0
        self.week_awarded = ""                       # ISO week the weekly-goal XP was given
        # per session (not saved)
        self.combo = 0
        self.session_xp = 0
        self.session_fuel_laps = 0
        self.feed: collections.deque[dict] = collections.deque(maxlen=MAX_FEED)
        self.say = None                              # callback(text) for the voice coach
        self._dirty = False
        self._load()

    # ----------------------------------------------------------- persistence
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.xp = int(raw.get("xp", 0))
        self.badges = {k: v for k, v in (raw.get("badges") or {}).items() if k in BADGES}
        self.stats = collections.Counter({k: int(v) for k, v in (raw.get("stats") or {}).items()})
        self.daily_day = raw.get("daily_day", "")
        self.daily_count = int(raw.get("daily_count", 0))
        self.daily_done = bool(raw.get("daily_done", False))
        self.dailies_done = int(raw.get("dailies_done", 0))
        self.best_combo = int(raw.get("best_combo", 0))
        self.week_awarded = str(raw.get("week_awarded", ""))

    def save(self, force: bool = False) -> None:
        with self.lock:
            if not (self._dirty or force):
                return
            data = {"xp": self.xp, "badges": self.badges, "stats": dict(self.stats),
                    "daily_day": self.daily_day, "daily_count": self.daily_count,
                    "daily_done": self.daily_done, "dailies_done": self.dailies_done,
                    "best_combo": self.best_combo, "week_awarded": self.week_awarded}
            try:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data), encoding="utf-8")
                tmp.replace(self.path)
                self._dirty = False
            except OSError:
                log.warning("could not save training game progress")

    def new_session(self) -> None:
        with self.lock:
            self.combo = 0
            self.session_xp = 0
            self.session_fuel_laps = 0

    # ---------------------------------------------------------------- events
    def _daily(self) -> dict:
        day = self._today()
        if self.daily_day != day.isoformat():
            self.daily_day, self.daily_count, self.daily_done = day.isoformat(), 0, False
        return daily_for(day)

    def _award(self, amount: int, why: str, kind: str) -> None:
        before = level_for(self.xp)["level"]
        self.xp += amount
        self.session_xp += amount
        self._dirty = True
        self.feed.append({"t": time.time(), "xp": amount, "text": why, "kind": kind})
        after = level_for(self.xp)
        if after["level"] > before:
            self.feed.append({"t": time.time(), "xp": 0, "kind": "level",
                              "text": f"Level {after['level']} - {after['title']}!"})
            self._speak(f"Level up. Level {after['level']}")
            if after["level"] >= 5:
                self._badge("level5")

    def _badge(self, bid: str) -> None:
        if bid in self.badges or bid not in BADGES:
            return
        self.badges[bid] = self._today().isoformat()
        self._dirty = True
        self.feed.append({"t": time.time(), "xp": 0, "kind": "badge", "text": f"Badge: {BADGES[bid][0]}"})
        self._speak(f"Badge unlocked. {BADGES[bid][0]}")

    def _speak(self, text: str) -> None:
        if self.say:
            try:
                self.say(text)
            except Exception:                         # never let the voice break scoring
                log.debug("game voice failed", exc_info=True)

    def _count_daily(self, event: str, value: int | None = None) -> None:
        d = self._daily()
        if self.daily_done or d["event"] != event:
            return
        self.daily_count = max(self.daily_count, value) if value is not None else self.daily_count + 1
        self._dirty = True
        if self.daily_count >= d["goal"]:
            self.daily_done = True
            self.dailies_done += 1
            self._award(XP["daily"], f"Daily challenge: {d['text']}", "daily")
            self._speak("Daily challenge complete")
            if self.dailies_done >= 3:
                self._badge("daily3")

    def _hit(self) -> int:
        self.combo += 1
        if self.combo > self.best_combo:
            self.best_combo = self.combo
        if self.combo >= 5:
            self._badge("combo5")
        if self.combo >= 10:
            self._badge("combo10")
        self._count_daily("combo", self.combo)
        return combo_mult(self.combo)

    def _miss(self) -> None:
        self.combo = 0

    def on(self, event: str, **kw) -> None:
        """Feed a training event into the game."""
        with self.lock:
            self.stats[event] += 1
            if event == "clean_lap":
                self._award(XP["clean_lap"], "Clean lap", event)
                self._badge("first_lap")
                if self.stats["clean_lap"] >= 100:
                    self._badge("laps100")
            elif event == "session_best":
                self._award(XP["session_best"], "New session best", event)
            elif event == "beat_reference":
                self._award(XP["beat_reference"], "Faster than the reference!", event)
                self._badge("beat_ref")
            elif event == "drill_attempt":
                if kw.get("ok"):
                    m = self._hit()
                    self._award(XP["drill_hit"] * m, f"{kw.get('corner', 'Drill')} on target"
                                + (f" x{m}" if m > 1 else ""), "drill_hit")
                    self.stats["drill_hit"] += 1
                    self._count_daily("drill_hit")
                else:
                    self._miss()
            elif event == "drill_done":
                self._award(XP["drill_done"], f"Drill complete: {kw.get('corner', '')}".rstrip(": "), event)
                self._badge("first_drill")
                if kw.get("kind") == "brake_ladder":
                    self._badge("ladder")
            elif event == "plan_step":
                self._award(XP["plan_step"], f"Quest done: {kw.get('title', 'plan step')}", event)
                if kw.get("all_done"):
                    self._award(XP["plan_complete"], "Practice plan complete!", "plan_complete")
                    self._badge("plan")
                    self._speak("Practice plan complete. Boss cleared")
            elif event == "cons_lap":
                if kw.get("inside"):
                    m = self._hit()
                    self._award(XP["cons_lap"] * m, "In the window" + (f" x{m}" if m > 1 else ""), event)
                    streak = kw.get("streak") or 0
                    if streak >= 5:
                        self._badge("cons5")
                    if streak >= 10:
                        self._badge("cons10")
                else:
                    self.stats[event] -= 1           # only count laps inside the window
                    self._miss()
                    return
            elif event == "cons_goal":
                self._award(XP["cons_goal"], "Consistency goal reached", event)
            elif event == "fuel_lap":
                if kw.get("ok"):
                    self.session_fuel_laps += 1
                    m = self._hit()
                    self._award(XP["fuel_lap"] * m, "Fuel target hit" + (f" x{m}" if m > 1 else ""), event)
                    if self.session_fuel_laps >= 5:
                        self._badge("fuel5")
                else:
                    self.stats[event] -= 1
                    self._miss()
                    return
            elif event == "weekly_goal":
                y, w, _ = self._today().isocalendar()
                week = f"{y}-W{w:02d}"
                if self.week_awarded == week:          # once per week, even across restarts
                    self.stats[event] -= 1
                    return
                self.week_awarded = week
                self._award(XP["weekly_goal"], "Weekly goal reached", event)
                self._badge("week")
            if event not in ("drill_attempt",):
                self._count_daily(event)
            # keep counters bounded in size (only known keys) and value
            if len(self.stats) > MAX_LOG:
                self.stats = collections.Counter(dict(self.stats.most_common(MAX_LOG)))

    # ---------------------------------------------------------------- status
    def overlay(self, now: float | None = None) -> dict:
        """Tiny state for the in-game overlay (called 20x per second, so keep it cheap)."""
        now = time.time() if now is None else now
        with self.lock:
            pop = self.feed[-1] if self.feed and now - self.feed[-1]["t"] < 4.0 else None
            lv = level_for(self.xp)
            return {"level": lv["level"], "pct": lv["pct"], "combo": self.combo, "mult": combo_mult(self.combo),
                    "pop": dict(pop) if pop else None}

    def status(self) -> dict:
        with self.lock:
            d = self._daily()
            lv = level_for(self.xp)
            return {
                "xp": self.xp, **lv, "session_xp": self.session_xp,
                "combo": self.combo, "mult": combo_mult(self.combo), "best_combo": self.best_combo,
                "daily": {**d, "count": min(self.daily_count, d["goal"]), "done": self.daily_done,
                          "xp": XP["daily"]},
                "badges": [{"id": k, "name": n, "how": h, "earned": self.badges.get(k)}
                           for k, (n, h) in BADGES.items()],
                "badge_count": len(self.badges),
                "feed": list(self.feed)[-8:],
                "xp_table": XP,
            }
