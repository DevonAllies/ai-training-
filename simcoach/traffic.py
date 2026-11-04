"""Racecraft: clean passes, clean let-bys, defending and faster-car warnings.

Uses real traffic from iRacing (every car's lap position, class, the spotter's
left/right flag and your incident count) - in a race, an AI race or open practice.

* **Pass / let-by detection** - a car close to you on track that changes from
  ahead to behind (or the other way) and stays there for a few seconds.
* **Clean or not** - no new incident points and nobody off track around the
  move, and what it cost you compared with your usual time through that stretch.
* **Defending** - a same-class car within 0.6 s behind you for 20 s that
  doesn't get by.
* **Faster-car warning** - a faster class closing from behind: how far back
  and the corner where it will catch you, so you can plan where to let it by.
* **Traffic time** - laps spent in traffic vs your clean laps.

Everything is kept in fixed-size containers.
"""

from __future__ import annotations

import collections
import statistics

ON_TRACK = 3
NEAR_LAP = 0.03          # |relative position| (laps) that counts as "close" for a pass
CONFIRM_S = 3.0          # a pass must hold this long
WINDOW_BEFORE = 5.0      # seconds before / after a pass that judge it
WINDOW_AFTER = 3.0
LETBY_OK_S = 0.5
LAPPING_OK_S = 0.3
DEFEND_GAP_S = 0.6
DEFEND_HOLD_S = 20.0
WARN_GAP_S = 3.0


def _rel(other: float, me: float) -> float:
    """On-track position of another car relative to me, in laps (-0.5..0.5, + = ahead)."""
    return ((other - me + 0.5) % 1.0) - 0.5


class TrafficTracker:
    def __init__(self):
        self.drivers: dict[int, dict] = {}
        self.my_class: int | None = None
        self._me: int | None = None
        self._pct = 0.0
        self.typical = None          # callback(pct_a, pct_b) -> your usual time over that stretch
        self.track_length = 4000.0
        self.reset()

    def reset(self) -> None:
        self._rel: dict[int, float] = {}
        self._pending: dict[int, dict] = {}       # idx -> pass waiting for confirmation
        self._pressure: dict[int, float] = {}     # idx -> time a same-class car started pressing
        self._warned: set[int] = set()
        self._gap_hist: dict[int, collections.deque] = {}
        self._hist: collections.deque = collections.deque(maxlen=120)   # (t, incidents, off, elapsed, sbs, lap, pct)
        self._last_ev: dict[int, float] = {}       # idx -> time of the last judged move with that car
        self.incidents = 0
        self._inc0: int | None = None
        self.events: collections.deque[dict] = collections.deque(maxlen=50)
        self.counts = collections.Counter()
        self.side_by_side_s = 0.0
        self.nearby: list[dict] = []
        self.warning: dict | None = None
        self.left_right = 1
        self.lap_traffic_s = 0.0
        self.laps: collections.deque[dict] = collections.deque(maxlen=60)
        self._t = None
        self._lap_id = 0
        self._me = None

    # ---------------------------------------------------------- setup
    def set_drivers(self, drivers: dict[int, dict], me: int | None) -> None:
        self.drivers = drivers or {}
        d = self.drivers.get(me) if me is not None else None
        self.my_class = d.get("class_id") if d else None

    def _info(self, idx: int) -> dict:
        return self.drivers.get(idx) or {"name": f"Car {idx}", "number": str(idx), "class": "", "class_id": None,
                                         "est_lap": None}

    def _faster(self, idx: int) -> bool | None:
        """Is this car in a faster class than mine? None = same class / unknown."""
        me = self.drivers.get(self._me) if self._me is not None else None
        o = self.drivers.get(idx)
        if not me or not o or o.get("class_id") == me.get("class_id"):
            return None
        a, b = o.get("est_lap"), me.get("est_lap")
        if not a or not b:
            return None
        return a < b * 0.98

    # ---------------------------------------------------------- per tick
    def update(self, t: float, me: int, my_pct: float, my_speed: float, my_surface: int,
               cars: dict, left_right: int, incidents: int | None, elapsed: float | None,
               corner_at=None, lap_id: int = 0) -> list[dict]:
        """Feed one traffic sample (~10 Hz). Returns new events."""
        self._me = me
        new: list[dict] = []
        dt = 0.0 if self._t is None else max(0.0, min(1.0, t - self._t))
        self._t = t
        L = self.track_length or 4000.0
        v = max(my_speed, 15.0)
        # incidents
        if incidents is not None:
            if self._inc0 is None:
                self._inc0 = incidents
            if incidents > self.incidents + self._inc0:
                pts = incidents - self._inc0 - self.incidents
                self.incidents += pts
                sbs = any(h[4] for h in self._hist if t - h[0] < 2.0) or left_right >= 2
                kind = "contact" if (pts >= 4 or (pts >= 2 and sbs)) else "incident"
                txt = {"contact": f"Contact ({pts}x)" + (" in a battle" if sbs else ""),
                       "incident": f"Incident {pts}x"}[kind]
                new.append(self._ev(t, kind, txt, ok=False, say="Contact. Give them room" if kind == "contact"
                                    else None))
        self.left_right = left_right
        sbs = left_right >= 2
        if sbs:
            self.side_by_side_s += dt
        self._hist.append((t, self.incidents, my_surface == 0, elapsed, sbs, lap_id, my_pct))
        self._pct = my_pct
        self._lap_id = lap_id

        pct, surf, pit = cars.get("pct", []), cars.get("surface", []), cars.get("pit", [])
        nearby, in_traffic = [], False
        seen = set()
        for idx in range(len(pct)):
            if idx == me:
                continue
            p = pct[idx]
            on = (p is not None and p >= 0 and (surf[idx] if idx < len(surf) else ON_TRACK) == ON_TRACK
                  and not (pit[idx] if idx < len(pit) else False))
            info = self.drivers.get(idx)
            if info and (info.get("pace") or info.get("spectator")):
                continue
            if not on:
                self._rel.pop(idx, None)
                continue
            seen.add(idx)
            r = _rel(p, my_pct)
            gap_m = r * L
            gap_s = gap_m / v
            hist = self._gap_hist.setdefault(idx, collections.deque(maxlen=12))
            hist.append((t, gap_s))
            closing = None
            if len(hist) >= 6 and hist[-1][0] - hist[0][0] > 0.4:
                closing = -(hist[-1][1] - hist[0][1]) / (hist[-1][0] - hist[0][0])   # + = gap shrinking
                if gap_s < 0:
                    closing = -closing                                               # car behind gaining
            if abs(gap_s) < 1.0:
                in_traffic = True
            if abs(gap_s) < 4.0:
                i = self._info(idx)
                nearby.append({"idx": idx, "name": i.get("name"), "number": i.get("number"), "class": i.get("class"),
                               "gap_s": round(gap_s, 2), "gap_m": round(gap_m), "faster": self._faster(idx),
                               "closing": None if closing is None else round(closing, 3)})
            prev = self._rel.get(idx)
            self._rel[idx] = r
            # --- pass detection (sign flip while close)
            if prev is not None and abs(r) < NEAR_LAP and abs(prev) < NEAR_LAP and (prev > 0) != (r > 0):
                pend = self._pending.get(idx)
                if pend:                                  # flipped back - re-pass or side-by-side wobble
                    self._pending.pop(idx)
                else:
                    self._pending[idx] = {"t": t, "mine": prev > 0, "lap": lap_id,
                                          "at0": self._at(t - WINDOW_BEFORE),
                                          "inc0": self._inc_at(t - WINDOW_BEFORE),
                                          "corner": corner_at(my_pct) if corner_at else None}
            # --- defending (same class, close behind)
            if self._faster(idx) is None and -DEFEND_GAP_S < gap_s < 0:
                self._pressure.setdefault(idx, t)
            elif idx in self._pressure and (gap_s < -1.5 or gap_s > 0):
                start = self._pressure.pop(idx)
                if gap_s < -1.5 and t - start >= DEFEND_HOLD_S:
                    self.counts["defended"] += 1
                    new.append(self._ev(t, "defended", f"Defended against #{self._info(idx).get('number')} "
                                        f"for {t - start:.0f}s", ok=True, say="Good defence"))
            # --- faster car warning
            fast = self._faster(idx)
            if fast and gap_s < 0:
                if -WARN_GAP_S < gap_s and (closing or 0) > 0.02 and idx not in self._warned:
                    self._warned.add(idx)
                    ttc = -gap_s / closing
                    where = corner_at((my_pct + v * ttc / L) % 1.0) if corner_at else None
                    i = self._info(idx)
                    self.warning = {"idx": idx, "t": t, "class": i.get("class"), "gap_s": round(-gap_s, 1),
                                    "corner": where}
                    txt = f"Faster car ({i.get('class') or 'other class'}) {-gap_s:.1f}s behind" + \
                          (f" - catches you at {where}" if where else "")
                    new.append(self._ev(t, "warning", txt, ok=None,
                                        say=f"Faster car, {-gap_s:.0f} seconds" + (f", at {where}" if where else "")))
                elif gap_s < -WARN_GAP_S - 2:
                    self._warned.discard(idx)
        for idx in list(self._rel):
            if idx not in seen:
                self._rel.pop(idx, None)
        if len(self._last_ev) > 128:
            self._last_ev = dict(sorted(self._last_ev.items(), key=lambda kv: kv[1])[-64:])
        for idx in list(self._gap_hist):
            if idx not in seen:
                self._gap_hist.pop(idx)
        if self.warning and t - self.warning["t"] > 8:
            self.warning = None
        if in_traffic:
            self.lap_traffic_s += dt
        nearby.sort(key=lambda c: -c["gap_s"])
        self.nearby = nearby[:8]
        # --- confirm pending passes
        for idx, pend in list(self._pending.items()):
            if t - pend["t"] >= CONFIRM_S:
                self._pending.pop(idx)
                ev = self._judge(idx, pend, t, elapsed)
                if ev:
                    new.append(ev)
        return new

    def _at(self, t: float) -> tuple | None:
        """(lap time so far, lap position) at time t - or the first sample of the current lap
        if t is before it (lap time restarts at the line)."""
        lap = self._lap_id
        best = None
        for h in self._hist:
            if h[5] != lap or h[3] is None:
                continue
            if h[0] <= t or best is None:
                best = (h[3], h[6])
            if h[0] > t:
                break
        return best

    def _inc_at(self, t: float) -> int:
        best = self._hist[0][1] if self._hist else self.incidents
        for h in self._hist:
            if h[0] <= t:
                best = h[1]
        return best

    def _judge(self, idx: int, pend: dict, t: float, elapsed: float | None) -> dict | None:
        i = self._info(idx)
        who = f"#{i.get('number')}" + (f" {i.get('class')}" if i.get("class") else "")
        inc = self.incidents - pend["inc0"]
        went_off = any(h[2] for h in self._hist if pend["t"] - WINDOW_BEFORE <= h[0] <= pend["t"] + WINDOW_AFTER)
        cost = None
        a = pend["at0"]
        if elapsed is not None and a is not None and pend.get("lap") == self._lap_id and self.typical:
            usual = self.typical(a[1], self._pct)        # your usual time over the same stretch
            if usual is not None:
                cost = round((elapsed - a[0]) - usual, 2)
        # swapping places with the same car again and again is one battle, not many passes
        battle = t - self._last_ev.get(idx, -1e9) < 30.0
        self._last_ev[idx] = t
        if battle and inc == 0 and not went_off:
            self.counts["battle_swap"] += 1
            return self._ev(t, "battle_swap", f"Battle with {self._info(idx).get('number') and '#' + self._info(idx)['number']}"
                            f" - {'back ahead' if pend['mine'] else 'they are back ahead'}", ok=None)
        clean = inc == 0 and not went_off
        fast = self._faster(idx)
        where = f" at {pend['corner']}" if pend.get("corner") else ""
        cost_txt = "" if cost is None else f" ({cost:+.2f}s)"
        if pend["mine"]:                                   # I went past
            kind = "lapped" if fast is False or (fast is None and self._slower(idx)) else "overtake"
            if not clean:
                self.counts["dirty_pass"] += 1
                return self._ev(t, "dirty_pass", f"Pass on {who}{where} - not clean"
                                + (f" ({inc}x)" if inc else " (off track)"), ok=False, say="Pass, not clean")
            if kind == "lapped" and cost is not None and cost > LAPPING_OK_S:
                self.counts["slow_lapping"] += 1
                return self._ev(t, "slow_lapping", f"Lapped {who}{where} but lost {cost:.2f}s - "
                                f"set it up earlier, pass on a straight", ok=False)
            self.counts["clean_pass"] += 1
            return self._ev(t, "clean_pass", f"Clean {'pass' if kind == 'overtake' else 'lapping pass'} on {who}"
                            f"{where}{cost_txt}", ok=True, say="Clean pass")
        # they went past me
        if fast:
            if clean and (cost is None or cost <= LETBY_OK_S):
                self.counts["clean_letby"] += 1
                return self._ev(t, "clean_letby", f"Clean let-by: {who}{where}{cost_txt}", ok=True,
                                say="Nice let-by")
            self.counts["costly_letby"] += 1
            why = f"{inc}x" if inc else "off track" if went_off else f"lost {cost:.2f}s"
            return self._ev(t, "costly_letby", f"Let-by {who}{where} cost you ({why}) - hold your line and "
                            f"lift a little on the straight", ok=False)
        self.counts["lost_position"] += 1
        return self._ev(t, "lost_position", f"Passed by {who}{where}" + ("" if clean else f" - contact {inc}x"),
                        ok=None if clean else False)

    def _slower(self, idx: int) -> bool:
        me, o = self.drivers.get(self._me), self.drivers.get(idx)
        if not me or not o or o.get("class_id") == me.get("class_id"):
            return False
        a, b = o.get("est_lap"), me.get("est_lap")
        return bool(a and b and a > b * 1.02)

    def _ev(self, t: float, kind: str, text: str, ok, say: str | None = None) -> dict:
        e = {"t": round(t, 2), "kind": kind, "text": text, "ok": ok, "say": say}
        self.events.append(e)
        return e

    # ------------------------------------------------------------- per lap
    def lap_done(self, lap_no: int, lap_time: float, valid: bool) -> dict:
        rec = {"lap": lap_no, "lap_time": round(lap_time, 3), "valid": valid,
               "traffic_s": round(self.lap_traffic_s, 1), "in_traffic": self.lap_traffic_s > 3.0}
        clean = [l["lap_time"] for l in self.laps if l["valid"] and not l["in_traffic"]]
        if rec["in_traffic"] and valid and len(clean) >= 2:
            rec["lost_s"] = round(lap_time - statistics.median(clean), 2)
        self.laps.append(rec)
        self.lap_traffic_s = 0.0
        return rec

    # -------------------------------------------------------------- status
    def score(self) -> int | None:
        good = self.counts["clean_pass"] + self.counts["clean_letby"] + self.counts["defended"]
        bad = self.counts["dirty_pass"] + self.counts["costly_letby"] + self.counts["slow_lapping"]
        if good + bad == 0 and not self.incidents:
            return None
        rate = good / (good + bad) if good + bad else 1.0
        return max(0, round(100 * rate - 4 * self.incidents))

    def status(self) -> dict:
        traffic_laps = [l for l in self.laps if l.get("lost_s") is not None]
        return {
            "nearby": self.nearby, "warning": self.warning, "left_right": self.left_right,
            "events": list(self.events)[-12:], "counts": dict(self.counts), "incidents": self.incidents,
            "side_by_side_s": round(self.side_by_side_s), "score": self.score(),
            "traffic_laps": len([l for l in self.laps if l["in_traffic"]]), "laps": len(self.laps),
            "traffic_lost_avg": round(statistics.fmean(l["lost_s"] for l in traffic_laps), 2) if traffic_laps else None,
        }
