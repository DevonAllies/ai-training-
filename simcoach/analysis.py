"""Lap comparison: where am I losing time, and why?

The reference lap is split into corner segments (one per speed minimum).
For each segment we compare braking point, brake pressure, minimum speed,
throttle pick-up, coasting and exit speed, and convert the differences into
plain-language coaching tips ranked by time lost.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .control import corner_control, corner_line, gear_ratios, line_offset, shift_summary
from .lap import GRID, N_BINS, Lap

MS_TO_KMH = 3.6


@dataclass
class Corner:
    index: int
    name: str
    start: int   # bin where the segment starts (previous straight's top speed)
    apex: int    # bin of the reference minimum speed
    end: int     # bin where the segment ends (next top speed)
    number: str = ""        # official turn number from the track's corner map, e.g. "1" or "4-5"
    label_name: str = ""    # official name, e.g. "Tertre Rouge"
    title: str = ""         # "T5 · Tertre Rouge" (falls back to name)
    spoken: str = ""        # what the voice coach says

    def __post_init__(self):
        self.title = self.title or self.name
        self.spoken = self.spoken or self.name

    @property
    def pct(self) -> float:
        return float(GRID[self.apex])


@dataclass
class CornerReport:
    name: str
    start_pct: float
    apex_pct: float
    end_pct: float
    time_lost: float                      # + = slower than reference
    entry_lost: float
    exit_lost: float
    brake_point_m: float | None           # + = I braked later than ref
    peak_brake_diff: float | None         # + = I braked harder (0..1 scale)
    min_speed_diff_kmh: float             # + = I was faster at the apex
    exit_speed_diff_kmh: float
    throttle_point_m: float | None        # + = I got on the throttle later
    turn_in_m: float | None               # + = I turned in later than ref
    coast_m_diff: float                   # + = I coasted more
    trail_m_diff: float | None = None     # + = I trail-braked further into the turn
    tips: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)   # issue codes, most important first
    title: str = ""
    spoken: str = ""
    # racing line (GPS): + = wide / towards the outside, - = tight / inside
    line_entry_m: float | None = None
    line_apex_m: float | None = None
    line_exit_m: float | None = None
    # car control
    understeer: float | None = None      # >1.25 = more lock for less rotation than the reference
    oversteer_m: float | None = None     # metres of opposite lock
    corrections_diff: int | None = None  # extra steering reversals vs the reference
    wheelspin_m_diff: float | None = None
    abs_m_diff: float | None = None
    gear_apex: int | None = None
    gear_apex_ref: int | None = None
    gear_apex_diff: int | None = None

    def to_dict(self) -> dict:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in asdict(self).items()}


# ------------------------------------------------------------------ helpers
def smooth(a: np.ndarray, w: int = 9) -> np.ndarray:
    """Circular moving average (laps wrap around the start/finish line)."""
    if w <= 1:
        return a
    k = np.ones(w) / w
    pad = w // 2
    ext = np.concatenate([a[-pad:], a, a[:pad]])
    return np.convolve(ext, k, mode="valid")[: len(a)]


def detect_corners(ref: Lap, min_drop_kmh: float = 10.0) -> list[Corner]:
    """Find corners as significant local minima of the reference speed trace."""
    s = smooth(ref.speed, 15)
    n = len(s)
    win = max(8, n // 80)          # ~1.25 % of the lap
    look = max(30, n // 15)        # how far back/forward to look for the straight
    drop = min_drop_kmh / MS_TO_KMH

    minima = []
    for i in range(n):
        lo, hi = max(0, i - win), min(n, i + win + 1)
        if s[i] > s[lo:hi].min() + 1e-9:
            continue
        before = s[max(0, i - look): i + 1].max()
        after = s[i: min(n, i + look + 1)].max()
        if before - s[i] >= drop and after - s[i] >= drop * 0.5:
            if minima and i - minima[-1] <= win:
                if s[i] < s[minima[-1]]:
                    minima[-1] = i
                continue
            minima.append(i)

    corners: list[Corner] = []
    for k, m in enumerate(minima):
        lo = minima[k - 1] if k > 0 else 0
        hi = minima[k + 1] if k + 1 < len(minima) else n - 1
        start = lo + int(np.argmax(s[lo:m + 1])) if m > lo else 0
        end = m + int(np.argmax(s[m:hi + 1])) if hi > m else n - 1
        corners.append(Corner(k, f"C{k + 1}", start, m, end))
    return corners


def delta_trace(me: Lap, ref: Lap) -> np.ndarray:
    """Running time delta at every bin (seconds, + = I'm behind)."""
    return me.time - ref.time


def _first(mask: np.ndarray) -> int | None:
    idx = np.flatnonzero(mask)
    return int(idx[0]) if len(idx) else None


def _brake_on(brake: np.ndarray, a: int, b: int, thr: float = 0.08) -> int | None:
    i = _first(brake[a:b + 1] > thr)
    return None if i is None else a + i


def _throttle_on(throttle: np.ndarray, a: int, b: int, thr: float = 0.9) -> int | None:
    """First bin after a (the apex) where the driver is (back) at near-full throttle."""
    seg = throttle[a:b + 1]
    i = _first(seg >= thr)
    return None if i is None else a + i


def steer_threshold(ref: Lap, a: int, b: int) -> float | None:
    """Steering angle that counts as 'turned in' for this corner (30% of ref peak)."""
    if ref.steer is None:
        return None
    peak = float(np.max(np.abs(ref.steer[a:b + 1])))
    if peak < 1e-3:
        return None
    return 0.3 * peak


def turn_in_bin(lap: Lap, a: int, limit: int, thr: float | None) -> int | None:
    if thr is None or lap.steer is None:
        return None
    i = _first(np.abs(lap.steer[a:limit + 1]) > thr)
    return None if i is None else a + i


# ------------------------------------------------------------------ compare
def compare_corner(me: Lap, ref: Lap, c: Corner, bin_m: float, line: dict | None = None,
                   ratios: tuple | None = None) -> CornerReport:
    a, m, b = c.start, c.apex, c.end
    d = delta_trace(me, ref)
    base = d[a - 1] if a > 0 else 0.0
    time_lost = float(d[b] - base)
    entry_lost = float(d[m] - base)
    exit_lost = float(d[b] - d[m])

    rb = _brake_on(ref.brake, a, m)
    mb = _brake_on(me.brake, a, m)
    brake_point_m = None
    peak_brake_diff = None
    if rb is not None and mb is not None:
        brake_point_m = (mb - rb) * bin_m
        peak_brake_diff = float(me.brake[a:m + 1].max() - ref.brake[a:m + 1].max())
    elif rb is not None and mb is None:
        peak_brake_diff = float(-ref.brake[a:m + 1].max())

    w = max(5, (b - a) // 4)
    lo, hi = max(a, m - w), min(b, m + w)
    my_apex = lo + int(np.argmin(me.speed[lo:hi + 1]))
    ref_apex = lo + int(np.argmin(ref.speed[lo:hi + 1]))
    min_speed_diff = float(me.speed[my_apex] - ref.speed[ref_apex]) * MS_TO_KMH
    exit_speed_diff = float(me.speed[b] - ref.speed[b]) * MS_TO_KMH

    rt = _throttle_on(ref.throttle, ref_apex, b)
    mt = _throttle_on(me.throttle, my_apex, b)
    throttle_point_m = None if (rt is None or mt is None) else (mt - rt) * bin_m

    thr = steer_threshold(ref, a, b)
    r_ti = turn_in_bin(ref, a, ref_apex, thr)
    m_ti = turn_in_bin(me, a, min(b, my_apex + w), thr)
    turn_in_m = None if (r_ti is None or m_ti is None) else (m_ti - r_ti) * bin_m

    def coast(l: Lap):
        seg = slice(a, b + 1)
        return float(np.sum((l.throttle[seg] < 0.05) & (l.brake[seg] < 0.05))) * bin_m
    coast_diff = coast(me) - coast(ref)

    # Trail braking: distance spent braking while already turned in, entry to apex.
    trail_diff = None
    if thr is not None and rb is not None:
        def trail(l: Lap, apex: int) -> float:
            seg = slice(a, apex + 1)
            return float(np.sum((l.brake[seg] > 0.05) & (np.abs(l.steer[seg]) > thr))) * bin_m
        if me.steer is not None:
            trail_diff = trail(me, my_apex) - trail(ref, ref_apex)

    rep = CornerReport(
        name=c.name, start_pct=float(GRID[a]), apex_pct=float(GRID[m]), end_pct=float(GRID[b]),
        time_lost=time_lost, entry_lost=entry_lost, exit_lost=exit_lost,
        brake_point_m=brake_point_m, peak_brake_diff=peak_brake_diff,
        min_speed_diff_kmh=min_speed_diff, exit_speed_diff_kmh=exit_speed_diff,
        throttle_point_m=throttle_point_m, turn_in_m=turn_in_m, coast_m_diff=coast_diff,
        trail_m_diff=trail_diff, title=c.title, spoken=c.spoken,
        **corner_line(line, a, r_ti, ref_apex, b),
        **corner_control(me, ref, a, my_apex, ref_apex, b, r_ti, thr, bin_m,
                         *(ratios if ratios else (None, None))),
    )
    rep.issues = detect_issues(rep)
    rep.tips = coaching_tips(rep)
    return rep


# Issue codes -> short voice phrase. Order in detect_issues() = priority.
SHORT_CUES = {
    "brake_early": "brake later",
    "overslow": "brake earlier, carry speed",
    "turn_in_late": "turn in earlier",
    "turn_in_early": "turn in later",
    "brake_soft": "brake harder",
    "no_trail": "trail the brake",
    "low_min_speed": "carry more speed",
    "coasting": "less coasting",
    "late_throttle": "throttle earlier",
    "low_exit": "better exit",
    "wide_apex": "hit the apex",
    "tight_entry": "use the outside",
    "understeer": "slow in, less lock",
    "oversteer": "smoother on exit",
    "busy_steering": "smooth hands",
    "wheelspin": "squeeze the throttle",
    "abs_heavy": "less brake pressure",
    "gear_apex": "check your gear",
}

ISSUE_LABELS = {
    "brake_early": "Braking too early",
    "overslow": "Braking late but over-slowing",
    "turn_in_late": "Turning in too late",
    "turn_in_early": "Turning in too early",
    "brake_soft": "Initial brake pressure too low",
    "no_trail": "Releasing the brake before turning in",
    "low_min_speed": "Minimum speed too low",
    "coasting": "Coasting between brake and throttle",
    "late_throttle": "Late on the throttle",
    "low_exit": "Slow corner exit",
    "wide_apex": "Missing the apex (line too wide)",
    "tight_entry": "Not using the outside on entry",
    "understeer": "Understeer (more lock, less rotation)",
    "oversteer": "Oversteer / catching slides",
    "busy_steering": "Too many steering corrections",
    "wheelspin": "Wheelspin on exit",
    "abs_heavy": "Leaning on ABS (too much brake pressure)",
    "gear_apex": "Different gear at the apex",
}


def detect_issues(r: CornerReport) -> list[str]:
    """Classify what went wrong in a corner (codes from SHORT_CUES), most important first."""
    if r.time_lost < 0.02:
        return []
    out = []
    if r.brake_point_m is not None and r.brake_point_m < -8 and r.entry_lost > 0.02:
        out.append("brake_early")
    if r.brake_point_m is not None and r.brake_point_m > 8 and r.min_speed_diff_kmh < -3:
        out.append("overslow")
    if r.turn_in_m is not None and r.turn_in_m > 8:
        out.append("turn_in_late")
    if r.turn_in_m is not None and r.turn_in_m < -8 and (r.exit_lost > 0.02 or r.min_speed_diff_kmh < -2):
        out.append("turn_in_early")
    if r.peak_brake_diff is not None and r.peak_brake_diff < -0.12 and r.entry_lost > 0.02:
        out.append("brake_soft")
    if r.trail_m_diff is not None and r.trail_m_diff < -15 and r.entry_lost > 0.02:
        out.append("no_trail")
    if r.min_speed_diff_kmh < -2.5 and "overslow" not in out:
        out.append("low_min_speed")
    if r.coast_m_diff > 15:
        out.append("coasting")
    if r.throttle_point_m is not None and r.throttle_point_m > 8 and r.exit_lost > 0.02:
        out.append("late_throttle")
    if r.exit_speed_diff_kmh < -3 and r.exit_lost > 0.02:
        out.append("low_exit")
    # racing line (GPS)
    if r.line_apex_m is not None and r.line_apex_m > 1.5 and (r.min_speed_diff_kmh < -1 or r.time_lost > 0.05):
        out.append("wide_apex")
    if r.line_entry_m is not None and r.line_entry_m < -1.5 and r.entry_lost > 0.02:
        out.append("tight_entry")
    # car control
    if r.oversteer_m is not None and r.oversteer_m >= 4:
        out.append("oversteer")
    if r.understeer is not None and r.understeer > 1.3 and (r.min_speed_diff_kmh < -1 or r.exit_lost > 0.02):
        out.append("understeer")
    if r.wheelspin_m_diff is not None and r.wheelspin_m_diff >= 6:
        out.append("wheelspin")
    if r.abs_m_diff is not None and r.abs_m_diff >= 10:
        out.append("abs_heavy")
    if r.corrections_diff is not None and r.corrections_diff >= 3:
        out.append("busy_steering")
    if r.gear_apex_diff and r.time_lost > 0.05:
        out.append("gear_apex")
    return out


def coaching_tips(r: CornerReport, units: str = "metric") -> list[str]:
    if r.time_lost < 0.02:
        if r.time_lost < -0.05:
            return [f"Good: {-r.time_lost:.2f}s faster than the reference here."]
        return []

    def dist(m: float) -> str:
        return f"{abs(m):.0f} m" if units == "metric" else f"{abs(m) * 3.281:.0f} ft"

    def spd(k: float) -> str:
        return f"{abs(k):.0f} km/h" if units == "metric" else f"{abs(k) / 1.609:.0f} mph"

    text = {
        "brake_early": lambda: f"Braking {dist(r.brake_point_m)} too early - move your brake point later.",
        "overslow": lambda: (f"Braking {dist(r.brake_point_m)} later than the reference but overslowing "
                             f"- brake earlier and release smoother to carry speed."),
        "turn_in_late": lambda: (f"Turning in {dist(r.turn_in_m)} late - start the turn earlier so you can "
                                 f"carry more speed to the apex."),
        "turn_in_early": lambda: (f"Turning in {dist(r.turn_in_m)} early - wait a moment longer; an early "
                                  f"turn-in forces you to slow down or run wide on exit."),
        "brake_soft": lambda: (f"Brake harder initially (peak {abs(r.peak_brake_diff) * 100:.0f}% lower than "
                               f"the reference), then trail off."),
        "no_trail": lambda: (f"Trail the brake into the turn - you are off the brake {dist(r.trail_m_diff)} "
                             f"earlier than the reference while turning in."),
        "low_min_speed": lambda: (f"Apex speed {spd(r.min_speed_diff_kmh)} slower - release the brake earlier "
                                  f"and carry more speed to the apex."),
        "coasting": lambda: (f"Coasting {dist(r.coast_m_diff)} more than the reference - "
                             f"go from brake to throttle with less dead time."),
        "late_throttle": lambda: (f"Full throttle {dist(r.throttle_point_m)} later - "
                                  f"open the throttle sooner on exit."),
        "low_exit": lambda: (f"Exit speed {spd(r.exit_speed_diff_kmh)} lower - this costs time all the "
                             f"way down the next straight. Prioritise a good exit."),
        "wide_apex": lambda: (f"Your line is {dist(r.line_apex_m)} wide of the reference at the apex - "
                              f"get closer to the inside kerb."),
        "tight_entry": lambda: (f"You start the corner {dist(r.line_entry_m)} inside the reference line - "
                                f"use the full track width on entry for a wider, faster arc."),
        "oversteer": lambda: (f"The rear stepped out: {dist(r.oversteer_m)} of opposite lock. Be smoother "
                              f"with throttle/brake release here, or adjust the car."),
        "understeer": lambda: ("Understeer: more steering lock than the reference for less rotation - "
                               "slow the entry slightly or trail the brake to load the front."),
        "wheelspin": lambda: (f"Wheelspin on exit for ~{dist(r.wheelspin_m_diff)} more than the reference - "
                              f"squeeze the throttle progressively."),
        "abs_heavy": lambda: (f"ABS working {dist(r.abs_m_diff)} more than the reference - brake pressure is "
                              f"too high, the tyres are locking."),
        "busy_steering": lambda: (f"{r.corrections_diff} more steering corrections than the reference - "
                                  f"one smooth input, the car is unsettled."),
        "gear_apex": lambda: (f"Gear {r.gear_apex} at the apex (reference uses {r.gear_apex_ref}) - "
                              f"{'try one lower for drive' if (r.gear_apex_diff or 0) > 0 else 'try one higher, less wheelspin'}."),
    }
    codes = r.issues or detect_issues(r)
    tips = [text[c]() for c in codes]
    if not tips and r.time_lost > 0.05:
        part = "entry" if r.entry_lost >= r.exit_lost else "exit"
        tips.append(f"Losing {r.time_lost:.2f}s, mostly on corner {part}. "
                    f"Compare the speed traces to find the difference.")
    return tips


# ------------------------------------------------------------ grading
def _clamp(v: float) -> float:
    return float(max(0.0, min(100.0, v)))


def technique_scores(reports: list[CornerReport], gap: float, ref_lap_time: float) -> dict:
    """0-100 grades per technique, plus overall pace. 100 = matches the reference."""
    def avg(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals)) if vals else None

    braking = avg([_clamp(100 - 2.5 * max(0.0, -r.brake_point_m) - 1.0 * max(0.0, r.brake_point_m - 5)
                          - 60 * max(0.0, -(r.peak_brake_diff or 0) - 0.05))
                   for r in reports if r.brake_point_m is not None])
    turn_in = avg([_clamp(100 - 2.5 * max(0.0, abs(r.turn_in_m) - 3))
                   for r in reports if r.turn_in_m is not None])
    min_speed = avg([_clamp(100 - 8 * max(0.0, -r.min_speed_diff_kmh - 1)) for r in reports])
    throttle = avg([_clamp(100 - 2.5 * max(0.0, r.throttle_point_m - 3) - 1.0 * max(0.0, r.coast_m_diff - 5))
                    for r in reports if r.throttle_point_m is not None])
    trail = avg([_clamp(100 - 1.5 * max(0.0, -r.trail_m_diff - 5))
                 for r in reports if r.trail_m_diff is not None])
    line = avg([_clamp(100 - 10 * max(0.0, abs(r.line_apex_m) - 0.5))
                for r in reports if r.line_apex_m is not None])
    control = avg([_clamp(100 - 3 * max(0.0, r.oversteer_m or 0) - 2 * max(0.0, r.wheelspin_m_diff or 0)
                          - 1 * max(0.0, r.abs_m_diff or 0) - 4 * max(0, r.corrections_diff or 0))
                   for r in reports if r.oversteer_m is not None or r.wheelspin_m_diff is not None])
    pace = _clamp(100 - (gap / ref_lap_time) * 100 * 20) if ref_lap_time else None
    parts = [x for x in (braking, turn_in, min_speed, throttle, trail, line, control) if x is not None]
    return {
        "braking": braking, "turn_in": turn_in, "min_speed": min_speed, "throttle": throttle,
        "trail_braking": trail, "line": line, "car_control": control,
        "pace": None if pace is None else round(pace),
        "technique": round(sum(parts) / len(parts)) if parts else None,
    }


@dataclass
class Comparison:
    lap_time_me: float
    lap_time_ref: float
    delta: np.ndarray
    corners: list[CornerReport]
    line: np.ndarray | None = None        # lateral offset from the reference line (m, + = left)
    shifts: dict | None = None

    def to_dict(self) -> dict:
        top = sorted([c for c in self.corners if c.time_lost > 0.02],
                     key=lambda c: c.time_lost, reverse=True)
        return {
            "lap_time_me": round(self.lap_time_me, 3),
            "lap_time_ref": round(self.lap_time_ref, 3),
            "gap": round(self.lap_time_me - self.lap_time_ref, 3),
            "delta": np.round(self.delta, 4).tolist(),
            "corners": [c.to_dict() for c in self.corners],
            "focus": [c.name for c in top[:3]],
            "potential_gain": round(sum(c.time_lost for c in top), 3),
            "scores": technique_scores(self.corners, self.lap_time_me - self.lap_time_ref,
                                       self.lap_time_ref),
            "line": None if self.line is None else np.round(self.line, 2).tolist(),
            "shifts": self.shifts,
        }


def compare_laps(me: Lap, ref: Lap, corners: list[Corner] | None = None,
                 units: str = "metric") -> Comparison:
    corners = corners if corners is not None else detect_corners(ref)
    L = ref.track_length or me.track_length or 4000.0
    bin_m = L / N_BINS
    line = line_offset(me, ref)
    ratios = (gear_ratios(me), gear_ratios(ref))
    reports = [compare_corner(me, ref, c, bin_m, line, ratios) for c in corners]
    d = delta_trace(me, ref)
    if reports:
        # Time won/lost on the start/finish straight belongs to the last corner's exit.
        first, last = corners[0], corners[-1]
        carry = float(d[-1] - d[last.end]) + (float(d[first.start - 1]) if first.start > 0 else 0.0)
        reports[-1].time_lost += carry
        reports[-1].exit_lost += carry
        reports[-1].issues = detect_issues(reports[-1])
        reports[-1].tips = coaching_tips(reports[-1], units)
    if units != "metric":
        for r in reports:
            r.tips = coaching_tips(r, units)
    cmp = Comparison(me.lap_time, ref.lap_time, d, reports)
    cmp.line = None if line is None else line["offset"]
    cmp.shifts = shift_summary(me, ref)
    return cmp
