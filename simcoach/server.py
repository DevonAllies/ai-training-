"""Local web server: REST API + WebSocket live stream + the dashboard UI.

Runs on http://127.0.0.1:8061 by default and is only reachable from this PC.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, demo
from .analysis import compare_laps, detect_corners
from .config import Config, cache_dir, laps_dir
from .garage61 import Garage61Client, Garage61Error, _tokens, describe_lap
from .lap import Lap, fmt_time, parse_csv
from .live import LiveEngine

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


class TokenIn(BaseModel):
    garage61_token: str | None = None
    units: str | None = None
    include_following: bool | None = None
    record_laps: bool | None = None
    extra_drivers: list[str] | None = None


class RefIn(BaseModel):
    lap: str                     # "g61:<id>", "local:<file>", "demo:ref" or "session_best"


def create_app(engine: LiveEngine, config: Config, demo_mode: bool = False) -> FastAPI:
    app = FastAPI(title="SimCoach", version=__version__)
    state = {"g61": Garage61Client(config.garage61_token)}

    def g61() -> Garage61Client:
        return state["g61"]

    def g61_call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Garage61Error as exc:
            raise HTTPException(status_code=exc.status or 502, detail=str(exc)) from exc

    # ------------------------------------------------------------ loading laps
    def load_lap(key: str) -> Lap:
        kind, _, ident = key.partition(":")
        if kind == "demo":
            if ident == "ref":
                return demo.reference_lap()
            return demo.make_lap(demo.YOU_STYLE, "Demo - you", jitter=1.0, seed=7)
        if kind == "local":
            path = (laps_dir() / ident).resolve()
            if path.parent != laps_dir().resolve() or not path.exists():
                raise HTTPException(404, "Lap file not found")
            return Lap.load(path)
        if kind == "g61":
            return load_g61_lap(ident)
        if key == "session_best" and engine.session_best is not None:
            return engine.session_best
        if key == "last" and engine.last_lap is not None:
            return engine.last_lap
        if key == "live_ref" and engine.reference is not None:
            return engine.reference
        if key in ("session_best", "last", "live_ref"):
            raise HTTPException(404, "No such lap yet - drive a full lap first.")
        raise HTTPException(400, f"Unknown lap reference: {key}")

    def load_g61_lap(lap_id: str) -> Lap:
        info = g61_call(g61().get_lap, lap_id)
        d = describe_lap(info)
        safe = hashlib.sha1(lap_id.encode()).hexdigest()[:16]
        cache = cache_dir() / f"g61_{safe}.csv"
        if cache.exists():
            text = cache.read_text(encoding="utf-8")
        else:
            text = g61_call(g61().lap_csv, lap_id)
            cache.write_text(text, encoding="utf-8")
        track_len = 0.0
        sess = engine.session
        if sess.get("track_length") and d.get("track") and _same_track(sess, d["track"]):
            track_len = sess["track_length"]
        try:
            lap = parse_csv(text, lap_time=d.get("lap_time"), track_length=track_len)
        except ValueError as exc:
            cache.unlink(missing_ok=True)
            raise HTTPException(422, f"Could not read telemetry for this lap: {exc}") from exc
        lap.label = f"{d['driver']} {fmt_time(d.get('lap_time') or lap.lap_time)}"
        lap.meta = {"track": d.get("track"), "car": d.get("car"), "source": "garage61",
                    "g61_id": lap_id, "driver": d["driver"], "date": d.get("date")}
        return lap

    # ------------------------------------------------------------------ routes
    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        return {"version": __version__, "demo": demo_mode, "live": engine.snapshot(),
                "config": config.public()}

    @app.get("/api/config")
    def get_config():
        return config.public()

    @app.post("/api/config")
    def set_config(body: TokenIn):
        if body.garage61_token is not None:
            config.garage61_token = body.garage61_token.strip()
            state["g61"] = Garage61Client(config.garage61_token)
        if body.units in ("metric", "imperial"):
            config.units = body.units
        if body.include_following is not None:
            config.include_following = body.include_following
        if body.record_laps is not None:
            config.record_laps = body.record_laps
        if body.extra_drivers is not None:
            config.extra_drivers = [s.strip() for s in body.extra_drivers if s.strip()]
        config.save()
        return config.public()

    # --------------------------------------------------------------- garage61
    @app.get("/api/g61/me")
    def g61_me():
        return g61_call(g61().me)

    @app.get("/api/g61/cars")
    def g61_cars():
        return sorted(g61_call(g61().cars), key=lambda c: c.get("name", ""))

    @app.get("/api/g61/tracks")
    def g61_tracks():
        return sorted(g61_call(g61().tracks),
                      key=lambda t: (t.get("name", ""), t.get("variant", "")))

    @app.get("/api/g61/match")
    def g61_match():
        """Guess the Garage 61 car/track for the current iRacing session."""
        sess = engine.session
        if not sess:
            return {"car": None, "track": None}
        track = g61_call(g61().match_track, sess.get("track", ""), sess.get("track_config", ""))
        car = g61_call(g61().match_car, sess.get("car", ""))
        return {"car": car, "track": track}

    @app.get("/api/g61/laps")
    def g61_laps(car: int | None = None, track: int | None = None, scope: str = "all",
                 group: str = "driver", age: int | None = None):
        """scope: 'me', 'team' (me + teammates), 'all' (me + teammates + following)."""
        drivers = None
        teams = None
        extra = config.extra_drivers or None
        if scope == "me":
            drivers, extra = ["me"], None
        elif scope == "all":
            drivers = ["me"] + (["following"] if config.include_following else [])
            teams = [t.get("slug") or t.get("id") for t in g61_call(g61().teams)] or None
        # scope == "team": no drivers/teams params -> Garage 61 returns me + all teammates
        laps = g61_call(g61().find_laps, cars=[car] if car else None,
                        tracks=[track] if track else None, drivers=drivers, teams=teams,
                        extra_drivers=extra, group=group, age=age)
        out = [describe_lap(l) for l in laps]
        out.sort(key=lambda l: l["lap_time"] or 1e9)
        return out

    # ------------------------------------------------------------------ local
    @app.get("/api/local/laps")
    def local_laps():
        out = []
        for p in sorted(laps_dir().glob("*.csv"), reverse=True)[:500]:
            try:
                with p.open(encoding="utf-8") as f:
                    head = f.readline()
                meta = json.loads(head[1:]) if head.startswith("#") else {}
            except (OSError, ValueError):
                meta = {}
            out.append({"file": p.name, "label": meta.get("label", p.stem),
                        "lap_time": meta.get("lap_time"), "track": meta.get("track"),
                        "car": meta.get("car"), "date": meta.get("date"),
                        "valid": meta.get("valid", True)})
        return out

    @app.delete("/api/local/laps/{name}")
    def delete_local(name: str):
        path = (laps_dir() / name).resolve()
        if path.parent != laps_dir().resolve() or not path.exists():
            raise HTTPException(404, "Not found")
        path.unlink()
        return {"ok": True}

    # ---------------------------------------------------------------- analyse
    @app.get("/api/lap")
    def get_lap(key: str):
        lap = load_lap(key)
        d = lap.to_json()
        d["corners"] = [{"name": c.name, "start": c.start, "apex": c.apex, "end": c.end}
                        for c in detect_corners(lap)]
        return d

    @app.get("/api/compare")
    def compare(mine: str, ref: str):
        me_lap = load_lap(mine)
        ref_lap = load_lap(ref)
        corners = detect_corners(ref_lap)
        cmp = compare_laps(me_lap, ref_lap, corners, config.units)
        return {
            "me": me_lap.to_json(),
            "ref": ref_lap.to_json(),
            "comparison": cmp.to_dict(),
            "corners": [{"name": c.name, "start": c.start, "apex": c.apex, "end": c.end}
                        for c in corners],
        }

    # ------------------------------------------------------------------- live
    @app.post("/api/live/reference")
    def set_reference(body: RefIn):
        if body.lap == "none":
            engine.set_reference(None)
            return {"reference": None}
        lap = load_lap(body.lap)
        engine.set_reference(lap, session_best=(body.lap == "session_best"))
        d = lap.to_json()
        return {"reference": lap.label, "lap": d}

    @app.get("/api/live/reference")
    def get_reference():
        ref = engine.reference
        if ref is None:
            return {"reference": None}
        return {"reference": ref.label, "lap": ref.to_json(),
                "corners": [{"name": c.name, "start": c.start, "apex": c.apex, "end": c.end}
                            for c in engine.ref_corners]}

    @app.get("/api/live/last")
    def last_lap():
        if engine.last_lap is None:
            return {"lap": None}
        return {"lap": engine.last_lap.to_json(), "comparison": engine.last_comparison}

    @app.websocket("/ws/live")
    async def ws_live(ws: WebSocket):
        await ws.accept()
        tick = 0
        try:
            while True:
                msg = {"type": "snap", **engine.snapshot()}
                if tick % 5 == 0:
                    msg["trace"] = engine.trace()
                await ws.send_json(msg)
                tick += 1
                await asyncio.sleep(0.05)   # 20 Hz to the UI
        except (WebSocketDisconnect, RuntimeError):
            return

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def _same_track(sess: dict, g61_track_name: str) -> bool:
    a = _tokens(f"{sess.get('track', '')} {sess.get('track_config', '')}")
    b = _tokens(g61_track_name)
    return bool(a and b) and len(a & b) / len(a | b) >= 0.5
