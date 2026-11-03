"""Build an 'optimal lap' from your own best corners.

The lap is split into segments at the straights between corners (the speed peaks
of a base lap, where everyone is flat out, so joins are smooth). For every
segment the fastest clean lap through it is chosen, and the segments are stitched
into one composite reference lap with full telemetry: brake points, apex speeds,
lines and inputs you have actually driven.

Teammate laps (imported .ibt files) can be included too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .analysis import detect_corners
from .lap import CHANNELS, N_BINS, Lap, fmt_time


@dataclass
class Segment:
    start: int
    end: int          # exclusive
    source: int       # index into the candidate laps
    duration: float


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def same_track(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def boundaries(base: Lap) -> list[int]:
    """Segment boundaries: 0, the top-speed point between consecutive corners, N."""
    corners = detect_corners(base)
    cuts = sorted({c.start for c in corners if 0 < c.start < N_BINS})
    return [0] + cuts + [N_BINS]


def _seg_time(lap: Lap, a: int, b: int) -> float:
    t0 = lap.time[a - 1] if a > 0 else 0.0
    t1 = lap.time[b - 1] if b < N_BINS else lap.lap_time
    return float(t1 - t0)


def build_optimal(laps: list[Lap], base: Lap | None = None) -> tuple[Lap, list[Segment]]:
    """Composite lap from the fastest segment of each candidate lap."""
    if len(laps) < 2:
        raise ValueError("Need at least two laps on this track to build an optimal lap.")
    base = base if base is not None else min(laps, key=lambda l: l.lap_time)
    cuts = boundaries(base)
    segs: list[Segment] = []
    for a, b in zip(cuts, cuts[1:]):
        times = [_seg_time(l, a, b) for l in laps]
        k = int(np.argmin(times))
        segs.append(Segment(a, b, k, times[k]))
    # stitch channels; time is rebuilt so each segment keeps its own duration
    out: dict[str, np.ndarray | None] = {}
    for ch in CHANNELS:
        if all(getattr(l, ch) is not None for l in laps):
            arr = np.empty(N_BINS)
            for s in segs:
                arr[s.start:s.end] = getattr(laps[s.source], ch)[s.start:s.end]
            out[ch] = arr
        else:
            out[ch] = None
    t = np.empty(N_BINS)
    elapsed = 0.0
    for s in segs:
        src = laps[s.source]
        t0 = src.time[s.start - 1] if s.start > 0 else 0.0
        t[s.start:s.end] = elapsed + (src.time[s.start:s.end] - t0)
        elapsed += s.duration
    lap = Lap(speed=out["speed"], throttle=out["throttle"], brake=out["brake"], time=t,
              gear=out["gear"], steer=out["steer"], lat=out["lat"], lon=out["lon"],
              yaw=out["yaw"], latacc=out["latacc"], rpm=out["rpm"], abs=out["abs"], fuel=None,
              track_length=base.track_length)
    # rescale so lap_time (extrapolated from the last bin) equals the sum of segment times
    if lap.lap_time > 0:
        lap.time = lap.time * (elapsed / lap.lap_time)
    used = sorted({s.source for s in segs})
    lap.label = f"Optimal lap {fmt_time(lap.lap_time)} ({len(used)} laps)"
    lap.meta = {"track": base.meta.get("track", ""), "car": base.meta.get("car", ""), "source": "optimal",
                "segments": [{"start": s.start, "end": s.end, "from": laps[s.source].label,
                              "duration": round(s.duration, 3)} for s in segs],
                "best_single_lap": round(min(l.lap_time for l in laps), 3)}
    return lap, segs
