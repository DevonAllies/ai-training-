"""Racing line and car-control analysis.

Everything here compares *you* with the reference lap at the same place on
track, so it needs no car parameters (steering ratio, wheelbase, gear ratios):

Racing line (needs GPS - Lat/Lon, which iRacing and .ibt files provide)
  * lateral offset from the reference line along the whole lap
  * per corner: how far wide / tight you were at turn-in, apex and exit
    (sign uses the track's curvature, so "wide" = towards the outside)

Car control
  * understeer : more steering lock than the reference for the same or less
                 rotation (yaw rate)                            [needs yaw]
  * oversteer  : opposite lock (countersteer) where the reference had none
  * corrections: more steering reversals than the reference ("busy hands")
  * wheelspin  : RPM rising above the gear's normal RPM/speed ratio on exit
  * ABS        : metres with ABS working in the braking zone vs the reference
  * gear       : gear at the apex vs the reference; upshift RPM (short-shifting)
"""

from __future__ import annotations

import math

import numpy as np

from .lap import N_BINS, Lap


# ------------------------------------------------------------------ racing line
def _xy(lat: np.ndarray, lon: np.ndarray, lat0: float, lon0: float):
    x = (lon - lon0) * math.cos(math.radians(lat0)) * 111320.0
    y = (lat - lat0) * 110540.0
    return x, y


def _circ_grad(a: np.ndarray) -> np.ndarray:
    return np.gradient(np.r_[a[-1], a, a[0]])[1:-1]


def _smooth(a: np.ndarray, w: int) -> np.ndarray:
    k = np.ones(w) / w
    pad = w // 2
    return np.convolve(np.r_[a[-pad:], a, a[:pad]], k, mode="valid")[: len(a)]


def line_offset(me: Lap, ref: Lap) -> dict | None:
    """Lateral offset of your line from the reference line (metres).

    Returns {"offset": left-positive offset per bin, "outside": offset towards the
    outside of the corner (+ = wide) per bin, "curv_sign": +1 left-hander / -1 right}
    or None when either lap has no GPS.
    """
    if not (me.has_map() and ref.has_map()):
        return None
    lat0, lon0 = float(np.mean(ref.lat)), float(np.mean(ref.lon))
    rx, ry = _xy(ref.lat, ref.lon, lat0, lon0)
    mx, my = _xy(me.lat, me.lon, lat0, lon0)
    tx, ty = _circ_grad(rx), _circ_grad(ry)
    norm = np.hypot(tx, ty)
    ok = norm > 1e-6
    nx = np.where(ok, -ty / np.where(ok, norm, 1), 0.0)
    ny = np.where(ok, tx / np.where(ok, norm, 1), 0.0)
    offset = (mx - rx) * nx + (my - ry) * ny               # + = left of the reference line
    # curvature sign of the reference path (+ = turning left), smoothed over ~2 % of the lap
    ddx, ddy = _circ_grad(tx), _circ_grad(ty)
    curv = (tx * ddy - ty * ddx) / np.maximum(norm ** 3, 1e-9)
    curv_s = _smooth(curv, max(5, N_BINS // 50))
    sign = np.sign(curv_s)
    outside = -offset * sign                                # + = towards the outside of the turn
    return {"offset": offset, "outside": outside, "curv_sign": sign}


def corner_line(line: dict | None, a: int, turn_in: int | None, apex: int, b: int) -> dict:
    """Wide (+) / tight (-) at turn-in, apex and exit for one corner (metres)."""
    if line is None:
        return {"line_entry_m": None, "line_apex_m": None, "line_exit_m": None}
    # use the corner's dominant direction for all three points (a chicane flips sign mid-way)
    sign_c = np.sign(np.mean(line["curv_sign"][max(a, apex - 10): apex + 11]) or 1.0)
    off = line["offset"]

    def at(i: int) -> float:
        lo, hi = max(0, i - 3), min(N_BINS, i + 4)
        return float(np.mean(-off[lo:hi] * sign_c))
    ti = turn_in if turn_in is not None else (a + apex) // 2
    exit_i = min(b, apex + max(5, (b - apex) * 2 // 3))
    return {"line_entry_m": at(ti), "line_apex_m": at(apex), "line_exit_m": at(exit_i)}


# ------------------------------------------------------------------ car control
def _reversals(steer: np.ndarray, amp: float) -> int:
    """Number of steering direction changes larger than `amp` (radians)."""
    count, last_ext, direction = 0, steer[0] if len(steer) else 0.0, 0
    for v in steer[1:]:
        if direction >= 0 and v < last_ext - amp:
            if direction == 1:
                count += 1
            direction, last_ext = -1, v
        elif direction <= 0 and v > last_ext + amp:
            if direction == -1:
                count += 1
            direction, last_ext = 1, v
        elif (direction == 1 and v > last_ext) or (direction == -1 and v < last_ext):
            last_ext = v
    return count


def gear_ratios(lap: Lap) -> dict[int, float]:
    """Typical RPM per m/s for each gear (from bins with real throttle and grip)."""
    if lap.rpm is None or lap.gear is None:
        return {}
    out = {}
    g = np.round(lap.gear).astype(int)
    for gear in np.unique(g):
        if gear < 1:
            continue
        m = (g == gear) & (lap.throttle > 0.5) & (lap.speed > 10)
        if m.sum() >= 5:
            out[int(gear)] = float(np.median(lap.rpm[m] / lap.speed[m]))
    return out


def corner_control(me: Lap, ref: Lap, a: int, apex_me: int, apex_ref: int, b: int,
                   turn_in: int | None, steer_thr: float | None, bin_m: float,
                   ratios_me: dict | None = None, ratios_ref: dict | None = None) -> dict:
    out = {"understeer": None, "oversteer_m": None, "corrections_diff": None,
           "wheelspin_m_diff": None, "abs_m_diff": None, "gear_apex_diff": None,
           "gear_apex": None, "gear_apex_ref": None}
    ti = turn_in if turn_in is not None else a
    seg_mid = slice(ti, max(ti + 1, apex_ref + 1))
    if me.steer is not None and ref.steer is not None:
        s_me, s_ref = float(np.mean(np.abs(me.steer[seg_mid]))), float(np.mean(np.abs(ref.steer[seg_mid])))
        # understeer: more lock for the same or less rotation
        if me.yaw is not None and ref.yaw is not None and s_ref > 1e-3:
            y_me, y_ref = float(np.mean(np.abs(me.yaw[seg_mid]))), float(np.mean(np.abs(ref.yaw[seg_mid])))
            if y_ref > 1e-3:
                ratio = (s_me / s_ref) / max(y_me / y_ref, 1e-3)
                out["understeer"] = round(ratio, 2)            # >1.25 = understeer, <0.8 = loose
        # oversteer: opposite lock where the reference turns the normal way
        peak = float(np.max(np.abs(ref.steer[a:b + 1]))) if b > a else 0.0
        if peak > 1e-3:
            dom = np.sign(np.mean(ref.steer[seg_mid])) or 1.0
            seg = slice(ti, b + 1)
            counter = (np.sign(me.steer[seg]) == -dom) & (np.abs(me.steer[seg]) > 0.25 * peak) & \
                      (np.sign(ref.steer[seg]) != -dom)
            out["oversteer_m"] = round(float(counter.sum()) * bin_m, 1)
            amp = max(0.02, 0.06 * peak)
            out["corrections_diff"] = _reversals(me.steer[a:b + 1], amp) - _reversals(ref.steer[a:b + 1], amp)
    # wheelspin on exit: RPM above the normal ratio for that gear
    if me.rpm is not None and me.gear is not None:
        rm = ratios_me if ratios_me is not None else gear_ratios(me)

        def spin(l: Lap, ratios: dict, apex: int) -> float:
            if not ratios or l.rpm is None or l.gear is None:
                return 0.0
            seg = slice(apex, b + 1)
            g = np.round(l.gear[seg]).astype(int)
            normal = np.array([ratios.get(int(x), np.nan) for x in g])
            ratio = l.rpm[seg] / np.maximum(l.speed[seg], 1.0)
            m = (l.throttle[seg] > 0.3) & np.isfinite(normal) & (ratio > normal * 1.08)
            return float(m.sum()) * bin_m
        rr = ratios_ref if ratios_ref is not None else gear_ratios(ref)
        out["wheelspin_m_diff"] = round(spin(me, rm, apex_me) - spin(ref, rr, apex_ref), 1)
    if me.abs is not None:
        seg = slice(a, apex_me + 1)
        mine = float((me.abs[seg] > 0.5).sum()) * bin_m
        theirs = float((ref.abs[a:apex_ref + 1] > 0.5).sum()) * bin_m if ref.abs is not None else 0.0
        out["abs_m_diff"] = round(mine - theirs, 1)
    if me.gear is not None and ref.gear is not None:
        gm, gr = int(round(me.gear[apex_me])), int(round(ref.gear[apex_ref]))
        out.update(gear_apex=gm, gear_apex_ref=gr, gear_apex_diff=gm - gr)
    return out


def shift_points(lap: Lap) -> list[float]:
    """RPM just before each upshift."""
    if lap.rpm is None or lap.gear is None:
        return []
    g = np.round(lap.gear).astype(int)
    idx = np.flatnonzero(np.diff(g) == 1)
    return [float(lap.rpm[i]) for i in idx if g[i] >= 1]


def shift_summary(me: Lap, ref: Lap) -> dict | None:
    a, b = shift_points(me), shift_points(ref)
    if not a or not b:
        return None
    ma, mb = float(np.median(a)), float(np.median(b))
    return {"me_rpm": round(ma), "ref_rpm": round(mb), "diff_rpm": round(ma - mb)}
