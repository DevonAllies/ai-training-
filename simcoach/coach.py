"""Session coaching: stint/session report, corner drill mode and voice cues.

* **Session report** - aggregates every completed lap of the session: average
  and best time lost per corner, consistency, the issue you repeat most often
  in each corner, technique grade trends and the top things to work on.
* **Corner drill (focus mode)** - work on one corner at a time. The coach picks
  the corner where you lose most (or you choose), shows only that corner's
  feedback, and moves on once you are within the target for N laps in a row.
* **Voice cues** - instead of commenting after every mistake, the coach speaks
  *one* short reminder before the corner, based on what you did there last
  lap ("C3, brake later"), and praises you when you fix it.

All history is kept in fixed-size containers so long sessions can't grow memory.
"""

from __future__ import annotations

import collections
import statistics

from .analysis import ISSUE_LABELS, SHORT_CUES
from .voice import VoiceCoach, spoken_seconds

MAX_LAPS = 100


class FocusDrill:
    def __init__(self, target: float = 0.05, needed: int = 3):
        self.active = False
        self.auto = True
        self.corner: int | None = None
        self.name = ""
        self.title = ""
        self.target = target
        self.needed = needed
        self.streak = 0
        self.attempts = 0
        self.last_loss: float | None = None
        self.last_issue = ""
        self.completed: list[str] = []
        self.message = ""

    def status(self) -> dict:
        return {"active": self.active, "auto": self.auto, "corner": self.corner, "name": self.name,
                "title": self.title or self.name,
                "target": self.target, "needed": self.needed, "streak": self.streak,
                "attempts": self.attempts, "last_loss": self.last_loss, "last_issue": self.last_issue,
                "completed": list(self.completed), "message": self.message}


class SessionCoach:
    def __init__(self, voice: VoiceCoach | None = None):
        self.voice = voice or VoiceCoach(native=False)
        self.history: collections.deque[dict] = collections.deque(maxlen=MAX_LAPS)
        self.last_corner: dict[int, dict] = {}      # idx -> latest corner summary
        self.corner_names: dict[int, str] = {}
        self.corner_titles: dict[int, str] = {}
        self.focus = FocusDrill()
        self._cued: set[int] = set()
        self.voice_mode = "cues"                    # off | cues | detailed
        self.voice_allowed = True                   # e.g. only in practice sessions

    # ------------------------------------------------------------- lifecycle
    def reset(self) -> None:
        """New reference or new car/track: corner numbering changes."""
        self.history.clear()
        self.last_corner.clear()
        self.corner_names.clear()
        self.corner_titles.clear()
        self._cued.clear()
        was_active, auto, target = self.focus.active, self.focus.auto, self.focus.target
        self.focus = FocusDrill(target=target)
        self.focus.active, self.focus.auto = was_active, auto

    def new_lap(self) -> None:
        self._cued.clear()

    def _say(self, text: str, important: bool = False) -> None:
        if self.voice_mode == "off" or not self.voice_allowed:
            return
        self.voice.say(text, min_repeat_s=8.0 if not important else 3.0)

    # ------------------------------------------------------------ live hooks
    def pre_corner(self, idx: int, name: str, spoken: str | None = None) -> str | None:
        """Called once per lap ~150-350 m before a corner. Returns the cue (if any)."""
        if idx in self._cued:
            return None
        self._cued.add(idx)
        self.corner_names[idx] = name
        f = self.focus
        if f.active and f.corner is not None and idx != f.corner:
            return None
        last = self.last_corner.get(idx)
        if not last:
            return None
        say_name = spoken or name
        if last["time_lost"] > 0.05 and last.get("issues"):
            cue = f"{say_name}, {SHORT_CUES[last['issues'][0]]}"
        elif f.active and idx == f.corner:
            cue = f"{say_name}, same again"
        else:
            return None
        self._say(cue)
        return cue

    def on_corner(self, idx: int, rep: dict) -> None:
        """Called when a corner is completed with its comparison report."""
        prev = self.last_corner.get(idx)
        self.last_corner[idx] = {"time_lost": rep["time_lost"], "issues": rep.get("issues", [])}
        self.corner_names[idx] = rep["name"]
        self.corner_titles[idx] = rep.get("title") or rep["name"]
        f = self.focus
        name = rep.get("spoken") or rep["name"]          # spoken form for the voice
        if f.active and f.corner == idx:
            f.attempts += 1
            f.last_loss = rep["time_lost"]
            f.last_issue = ISSUE_LABELS.get(rep["issues"][0], "") if rep.get("issues") else ""
            if rep["time_lost"] <= f.target:
                f.streak += 1
                f.message = f"{rep.get('title') or rep['name']}: on target ({f.streak}/{f.needed})"
                if f.streak >= f.needed:
                    f.completed.append(rep["name"])
                    f.message = f"{rep.get('title') or rep['name']} mastered! " + \
                        ("Moving to the next corner." if f.auto else "")
                    self._say(f"{name} done. Nice work.", important=True)
                    if f.auto:
                        self._pick_focus(exclude=set(f.completed))
                    else:
                        f.streak = 0
                    return
                self._say(f"{name}, good. {f.streak} of {f.needed}", important=True)
            else:
                f.streak = 0
                f.message = f"{rep.get('title') or rep['name']}: {rep['time_lost']:+.2f}s - " \
                            f"{f.last_issue or 'keep working'}"
                if self.voice_mode == "detailed":
                    self._say(f"{name}, {spoken_seconds(rep['time_lost'])} lost", important=True)
            return
        if f.active:
            return
        # praise a fixed mistake (only if it was a real loss last time)
        if prev and prev["time_lost"] > 0.08 and rep["time_lost"] < prev["time_lost"] - 0.05 \
                and rep["time_lost"] < 0.05:
            self._say(f"{name}, better")
        elif self.voice_mode == "detailed" and abs(rep["time_lost"]) >= 0.1:
            word = "lost" if rep["time_lost"] > 0 else "gained"
            self._say(f"{name}, {spoken_seconds(rep['time_lost'])} {word}")

    def add_lap(self, lap_no: int, lap_time: float, valid: bool, comparison: dict | None) -> None:
        if comparison is None:
            return
        self.history.append({
            "lap": lap_no, "lap_time": lap_time, "valid": valid, "gap": comparison["gap"],
            "scores": comparison.get("scores", {}),
            "corners": [{"name": c["name"], "title": c.get("title") or c["name"],
                         "spoken": c.get("spoken") or c["name"],
                         "time_lost": c["time_lost"], "issues": c.get("issues", [])}
                        for c in comparison["corners"]],
        })
        for i, c in enumerate(comparison["corners"]):
            self.corner_names[i] = c["name"]
        f = self.focus
        if f.active and f.auto and f.corner is None:
            self._pick_focus(exclude=set(f.completed))

    # ------------------------------------------------------------- focus mode
    def start_focus(self, corner: int | None = None, target: float | None = None) -> dict:
        f = self.focus
        f.active = True
        f.auto = corner is None
        f.streak = f.attempts = 0
        f.last_loss = None
        if target:
            f.target = target
        if corner is None:
            self._pick_focus(exclude=set(f.completed))
        else:
            f.corner = corner
            f.name = self.corner_names.get(corner, f"C{corner + 1}")
            f.title = self.corner_titles.get(corner, f.name)
            f.message = f"Focus on {f.title}"
        return f.status()

    def stop_focus(self) -> None:
        self.focus.active = False
        self.focus.message = ""

    def _pick_focus(self, exclude: set[str]) -> None:
        f = self.focus
        rep = self.report()
        cand = [c for c in rep["corners"] if c["name"] not in exclude and c["avg_loss"] > f.target]
        f.streak = f.attempts = 0
        f.last_loss = None
        if not cand:
            f.corner = None
            f.name = ""
            f.message = ("All corners within target - great session!" if rep["corners"]
                         else "Drive a lap - the coach will pick the corner to work on.")
            return
        best = max(cand, key=lambda c: c["avg_loss"])
        f.corner, f.name = best["index"], best["name"]
        f.title = best["title"]
        f.message = f"Focus on {best['title']}: {best['main_issue'] or 'losing time'} " \
                    f"(avg {best['avg_loss']:+.2f}s)"
        self._say(f"Focus on {best['spoken']}", important=True)

    # ----------------------------------------------------------------- report
    def report(self) -> dict:
        laps = [h for h in self.history if h["valid"]] or list(self.history)
        out: dict = {"laps": len(laps), "corners": [], "focus": [], "summary": [], "trend": []}
        if not laps:
            return out
        n = max(len(h["corners"]) for h in laps)
        for i in range(n):
            vals = [h["corners"][i] for h in laps if i < len(h["corners"])]
            losses = [v["time_lost"] for v in vals]
            counts = collections.Counter(code for v in vals for code in v["issues"][:2])
            main, k = counts.most_common(1)[0] if counts else ("", 0)
            out["corners"].append({
                "index": i, "name": vals[0]["name"], "title": vals[-1].get("title") or vals[-1]["name"],
                "spoken": vals[-1].get("spoken") or vals[-1]["name"],
                "avg_loss": round(statistics.fmean(losses), 3),
                "best_loss": round(min(losses), 3),
                "spread": round(statistics.pstdev(losses), 3) if len(losses) > 1 else 0.0,
                "main_issue": ISSUE_LABELS.get(main, ""), "main_issue_code": main,
                "main_issue_laps": k, "laps": len(vals),
            })
        ranked = sorted(out["corners"], key=lambda c: c["avg_loss"], reverse=True)
        out["focus"] = [c["name"] for c in ranked if c["avg_loss"] > 0.05][:3]
        out["trend"] = [{"lap": h["lap"], "lap_time": h["lap_time"], "gap": h["gap"], **h["scores"]}
                        for h in laps]
        out["best_lap"] = min(h["lap_time"] for h in laps)
        out["avg_gap"] = round(statistics.fmean(h["gap"] for h in laps), 3)
        out["potential"] = round(sum(max(0.0, c["avg_loss"]) for c in out["corners"]), 3)
        out["own_potential"] = round(sum(c["avg_loss"] - c["best_loss"] for c in out["corners"]), 3)

        s = out["summary"]
        for c in ranked[:3]:
            if c["avg_loss"] <= 0.05:
                break
            why = f" - mostly {c['main_issue'].lower()} ({c['main_issue_laps']} of {c['laps']} laps)" \
                if c["main_issue"] else ""
            s.append(f"{c['title']}: losing {c['avg_loss']:.2f}s per lap on average{why}.")
        if out["own_potential"] > 0.1:
            s.append(f"Repeating your own best in every corner is worth {out['own_potential']:.2f}s per lap "
                     f"- consistency first, then chase the reference.")
        if len(out["corners"]) > 2 and len(laps) > 2:
            worst = max(out["corners"], key=lambda c: c["spread"])
            if worst["spread"] > 0.08:
                s.append(f"Least consistent corner: {worst['title']} (±{worst['spread']:.2f}s).")
        if len(laps) >= 3:
            first, last = laps[0]["scores"], laps[-1]["scores"]
            for key, label in (("braking", "Braking"), ("min_speed", "Minimum speed"),
                               ("turn_in", "Turn-in"), ("throttle", "Throttle")):
                a, b = first.get(key), last.get(key)
                if a is not None and b is not None and abs(b - a) >= 5:
                    s.append(f"{label} grade {'improved' if b > a else 'dropped'}: {a} → {b}.")
        return out
