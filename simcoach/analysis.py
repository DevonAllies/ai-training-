"""Lap comparison: where am I losing time, and why?

The reference lap is split into corner segments (one per speed minimum).
For each segment we compare braking point, brake pressure, minimum speed,
throttle pick-up, coasting and exit speed, and convert the differences into
plain-language coaching tips ranked by time lost.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .lap import GRID, N_BINS, Lap

MS_TO_KMH = 3.6


@dataclass
class Corner:
    index: int
    name: str
    start: int   # bin where the segment starts (previous straight's top speed)
    apex: int    # bin of the reference minimum speed
    end: int     # bin where the segment ends (next top speed)

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
    coast_m_diff: float                   # + = I coasted more
    tips: list[str] = field(default_factory=list)

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


# ------------------------------------------------------------------ compare
def compare_corner(me: Lap, ref: Lap, c: Corner, bin_m: float) -> CornerReport:
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

    def coast(l: Lap):
        seg = slice(a, b + 1)
        return float(np.sum((l.throttle[seg] < 0.05) & (l.brake[seg] < 0.05))) * bin_m
    coast_diff = coast(me) - coast(ref)

    rep = CornerReport(
        name=c.name, start_pct=float(GRID[a]), apex_pct=float(GRID[m]), end_pct=float(GRID[b]),
        time_lost=time_lost, entry_lost=entry_lost, exit_lost=exit_lost,
        brake_point_m=brake_point_m, peak_brake_diff=peak_brake_diff,
        min_speed_diff_kmh=min_speed_diff, exit_speed_diff_kmh=exit_speed_diff,
        throttle_point_m=throttle_point_m, coast_m_diff=coast_diff,
    )
    rep.tips = coaching_tips(rep)
    return rep


def coaching_tips(r: CornerReport, units: str = "metric") -> list[str]:
    tips: list[str] = []
    if r.time_lost < 0.02:
        if r.time_lost < -0.05:
            tips.append(f"Good: {-r.time_lost:.2f}s faster than the reference here.")
        return tips

    def dist(m: float) -> str:
        return f"{abs(m):.0f} m" if units == "metric" else f"{abs(m) * 3.281:.0f} ft"

    def spd(k: float) -> str:
        return f"{abs(k):.0f} km/h" if units == "metric" else f"{abs(k) / 1.609:.0f} mph"

    if r.brake_point_m is not None and r.brake_point_m < -8 and r.entry_lost > 0.02:
        tips.append(f"Braking {dist(r.brake_point_m)} too early - move your brake point later.")
    if r.brake_point_m is not None and r.brake_point_m > 8 and r.min_speed_diff_kmh < -3:
        tips.append(f"Braking {dist(r.brake_point_m)} later than the reference but overslowing "
                    f"- brake earlier and release smoother to carry speed.")
    if r.peak_brake_diff is not None and r.peak_brake_diff < -0.12 and r.entry_lost > 0.02:
        tips.append(f"Brake harder initially (peak {abs(r.peak_brake_diff) * 100:.0f}% lower than "
                    f"the reference), then trail off.")
    if r.min_speed_diff_kmh < -2.5:
        tips.append(f"Apex speed {spd(r.min_speed_diff_kmh)} slower - release the brake earlier "
                    f"and carry more speed to the apex.")
    if r.coast_m_diff > 15:
        tips.append(f"Coasting {dist(r.coast_m_diff)} more than the reference - "
                    f"go from brake to throttle with less dead time.")
    if r.throttle_point_m is not None and r.throttle_point_m > 8 and r.exit_lost > 0.02:
        tips.append(f"Full throttle {dist(r.throttle_point_m)} later - "
                    f"open the throttle sooner on exit.")
    if r.exit_speed_diff_kmh < -3 and r.exit_lost > 0.02:
        tips.append(f"Exit speed {spd(r.exit_speed_diff_kmh)} lower - this costs time all the "
                    f"way down the next straight. Prioritise a good exit.")
    if not tips:
        part = "entry" if r.entry_lost >= r.exit_lost else "exit"
        tips.append(f"Losing {r.time_lost:.2f}s, mostly on corner {part}. "
                    f"Compare the speed traces to find the difference.")
    return tips


@dataclass
class Comparison:
    lap_time_me: float
    lap_time_ref: float
    delta: np.ndarray
    corners: list[CornerReport]

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
        }


def compare_laps(me: Lap, ref: Lap, corners: list[Corner] | None = None,
                 units: str = "metric") -> Comparison:
    corners = corners if corners is not None else detect_corners(ref)
    L = ref.track_length or me.track_length or 4000.0
    bin_m = L / N_BINS
    reports = [compare_corner(me, ref, c, bin_m) for c in corners]
    d = delta_trace(me, ref)
    if reports:
        # Time won/lost on the start/finish straight belongs to the last corner's exit.
        first, last = corners[0], corners[-1]
        carry = float(d[-1] - d[last.end]) + (float(d[first.start - 1]) if first.start > 0 else 0.0)
        reports[-1].time_lost += carry
        reports[-1].exit_lost += carry
        reports[-1].tips = coaching_tips(reports[-1], units)
    if units != "metric":
        for r in reports:
            r.tips = coaching_tips(r, units)
    return Comparison(me.lap_time, ref.lap_time, d, reports)
