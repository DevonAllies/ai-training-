"""A synthetic track + driver model.

Used for ``--demo`` mode (try the app without iRacing running) and for tests.
The reference driver is near optimal; the "you" driver brakes early, over-slows
and gets on the throttle late in a few specific corners, so the coaching output
is predictable.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from .lap import GRID, N_BINS, Lap, from_samples

TRACK_LENGTH = 4200.0
V_MAX = 78.0          # m/s top speed
BRAKE_DECEL = 13.0    # m/s^2
ACCEL = 4.5           # m/s^2

# (pct of lap, apex speed m/s)
CORNERS = [(0.12, 22.0), (0.27, 38.0), (0.41, 17.0), (0.55, 45.0),
           (0.66, 28.0), (0.80, 33.0), (0.93, 20.0)]


@dataclass
class DriverStyle:
    brake_early_m: dict      # corner index -> metres braking earlier than optimal
    apex_loss: dict          # corner index -> m/s lower apex speed
    accel_factor: dict       # corner index -> fraction of optimal acceleration on exit
    decel_factor: float = 1.0


REFERENCE_STYLE = DriverStyle({}, {}, {})
YOU_STYLE = DriverStyle(
    brake_early_m={2: 20.0, 4: 10.0},
    apex_loss={2: 2.0, 6: 2.0},
    accel_factor={6: 0.85, 0: 0.95},
    decel_factor=0.97,
)


def speed_profile(style: DriverStyle, jitter: float = 0.0, seed: int | None = None) -> np.ndarray:
    rng = random.Random(seed)
    x = GRID * TRACK_LENGTH
    v = np.full(N_BINS, V_MAX)
    for i, (pct, vmin) in enumerate(CORNERS):
        apex_x = pct * TRACK_LENGTH
        vmin = vmin - style.apex_loss.get(i, 0.0) + rng.uniform(-jitter, jitter)
        dec = BRAKE_DECEL * style.decel_factor
        acc = ACCEL * style.accel_factor.get(i, 1.0)
        early = style.brake_early_m.get(i, 0.0)
        for off in (-TRACK_LENGTH, 0.0, TRACK_LENGTH):   # wrap around the lap
            dx = x - (apex_x + off)
            # braking side: hold apex speed for `early` metres before the apex
            before = np.where(dx < 0, np.maximum(-dx - early, 0.0), np.inf)
            vb = np.sqrt(vmin ** 2 + 2 * dec * before)
            after = np.where(dx >= 0, dx, np.inf)
            va = np.sqrt(vmin ** 2 + 2 * acc * after)
            v = np.minimum(v, np.minimum(vb, va))
    return v


def controls_from_speed(v: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dv = np.gradient(np.concatenate([v[-1:], v, v[:1]]))[1:-1]
    throttle = np.where(dv > 0.005, 1.0, np.where(dv > -0.005, np.where(v >= V_MAX - 0.1, 1.0, 0.0), 0.0))
    brake = np.clip(-dv / 0.19, 0.0, 1.0) * (dv < -0.005)
    gear = np.clip(np.ceil(v / (V_MAX / 6)), 1, 6)
    return throttle, brake, gear


def track_map() -> tuple[np.ndarray, np.ndarray]:
    """A closed, wiggly loop in lat/lon degrees."""
    th = GRID * 2 * math.pi
    r = 1 + 0.18 * np.sin(3 * th) + 0.08 * np.cos(5 * th)
    lat = 50.33 + 0.006 * r * np.sin(th)
    lon = 6.94 + 0.010 * r * np.cos(th)
    return lat, lon


def make_lap(style: DriverStyle, label: str, jitter: float = 0.0, seed: int | None = None) -> Lap:
    v = speed_profile(style, jitter, seed)
    thr, brk, gear = controls_from_speed(v)
    lat, lon = track_map()
    lap = from_samples(GRID, v, thr, brk, track_length=TRACK_LENGTH, gear=gear,
                       steer=np.zeros(N_BINS), lat=lat, lon=lon)
    lap.label = label
    lap.meta = {"track": "Demo Ring - GP", "car": "Demo GT3", "source": "demo"}
    return lap


def reference_lap() -> Lap:
    return make_lap(REFERENCE_STYLE, "Demo reference (Alex Fast)")


def demo_ref_csv() -> str:
    """The reference lap as a Garage 61-style CSV (no time column)."""
    lap = reference_lap()
    rows = ["Speed,LapDistPct,Throttle,Brake,Gear,SteeringWheelAngle,Lat,Lon"]
    for i in range(N_BINS):
        rows.append(f"{lap.speed[i]:.4f},{GRID[i]:.5f},{lap.throttle[i]:.3f},{lap.brake[i]:.3f},"
                    f"{int(lap.gear[i])},0,{lap.lat[i]:.7f},{lap.lon[i]:.7f}")
    return "\n".join(rows)
