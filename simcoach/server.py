"""Local web server: REST API + WebSocket live stream + the dashboard UI.

Runs on http://127.0.0.1:8061 by default and is only reachable from this PC.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path

import tempfile

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, corners as cmap, demo, sessions
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
    overlay_mode: str | None = None
    overlay_scale: float | None = None
    overlay_opacity: float | None = None
    voice_mode: str | None = None
    voice_native: bool | None = None
    voice_practice_only: bool | None = None
    focus_target: float | None = None
    start_with_windows: bool | None = None
    update_mode: str | None = None


class CornerMapIn(BaseModel):
    track: str
    corners: list[dict]


class FocusIn(BaseModel):
    action: str = "auto"               # "auto" | "corner" | "stop"
    corner: int | None = None


class TargetsIn(BaseModel):
    session_id: str | None = None      # imported session id; None = clear (use session best)


class RefIn(BaseModel):
    lap: str                     # "g61:<id>", "local:<file>", "demo:ref" or "session_best"


def create_app(engine: LiveEngine, config: Config, demo_mode: bool = False, updater=None) -> FastAPI:
    app = FastAPI(title="SimCoach", version=__version__)
    state = {"g61": Garage61Client(config.garage61_token)}
    if engine.on_session_change is None:
        engine.on_session_change = auto_sector_targets

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
            _prune_cache()
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

    @app.get("/favicon.ico")
    def favicon():
        return FileResponse(STATIC / "icon.png")

    @app.get("/api/status")
    def status():
        return {"version": __version__, "demo": demo_mode, "live": engine.snapshot(),
                "config": public_config()}

    def public_config():
        from . import autostart
        d = config.public()
        d["start_with_windows"] = autostart.is_enabled()
        d["autostart_supported"] = autostart.supported()
        return d

    @app.get("/api/config")
    def get_config():
        return public_config()

    @app.post("/api/config")
    def set_config(body: TokenIn):
        if body.garage61_token is not None:
            config.garage61_token = body.garage61_token.strip()
            state["g61"].close()
            state["g61"] = Garage61Client(config.garage61_token)
        if body.units in ("metric", "imperial"):
            config.units = body.units
        if body.include_following is not None:
            config.include_following = body.include_following
        if body.record_laps is not None:
            config.record_laps = body.record_laps
        if body.extra_drivers is not None:
            config.extra_drivers = [s.strip() for s in body.extra_drivers if s.strip()]
        if body.overlay_mode in ("practice", "always", "off"):
            config.overlay_mode = body.overlay_mode
        if body.overlay_scale is not None:
            config.overlay_scale = max(0.6, min(2.0, body.overlay_scale))
        if body.overlay_opacity is not None:
            config.overlay_opacity = max(0.3, min(1.0, body.overlay_opacity))
        if body.voice_mode in ("off", "cues", "detailed"):
            config.voice_mode = body.voice_mode
        if body.voice_native is not None:
            config.voice_native = body.voice_native
            engine.coach.voice.native = body.voice_native
        if body.voice_practice_only is not None:
            config.voice_practice_only = body.voice_practice_only
        if body.focus_target is not None:
            config.focus_target = max(0.0, min(1.0, body.focus_target))
            engine.coach.focus.target = config.focus_target
        if body.update_mode in ("auto", "notify", "off"):
            config.update_mode = body.update_mode
            if updater and body.update_mode != "off":
                updater.check_soon()
        if body.start_with_windows is not None:
            from . import autostart
            try:
                autostart.set_enabled(body.start_with_windows)
            except OSError as exc:
                raise HTTPException(500, f"Could not change startup setting: {exc}") from exc
        config.save()
        return public_config()

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
        d["corners"] = [cmap.corner_dict(c) for c in named_corners(lap)]
        return d

    @app.get("/api/compare")
    def compare(mine: str, ref: str):
        me_lap = load_lap(mine)
        ref_lap = load_lap(ref)
        corners = named_corners(ref_lap)
        cmp = compare_laps(me_lap, ref_lap, corners, config.units)
        return {
            "me": me_lap.to_json(),
            "ref": ref_lap.to_json(),
            "comparison": cmp.to_dict(),
            "corners": [cmap.corner_dict(c) for c in corners],
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
                "corners": [cmap.corner_dict(c) for c in engine.ref_corners]}

    @app.get("/api/live/last")
    def last_lap():
        if engine.last_lap is None:
            return {"lap": None}
        return {"lap": engine.last_lap.to_json(), "comparison": engine.last_comparison}

    # --------------------------------------------------- imported sessions
    @app.post("/api/sessions/import")
    async def import_session(request: Request, filename: str = "export.xlsx"):
        body = await request.body()
        if not body:
            raise HTTPException(400, "Empty upload")
        if len(body) > 20_000_000:
            raise HTTPException(413, "File too large")
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(body)
            tmp = Path(f.name)
        try:
            slug = sessions.import_file(tmp)
        except Exception as exc:  # openpyxl raises many different errors on bad files
            raise HTTPException(422, f"Could not read {filename}: {exc}") from exc
        finally:
            tmp.unlink(missing_ok=True)
        auto_sector_targets(engine)
        return {"id": slug}

    @app.get("/api/sessions")
    def list_sessions():
        return sessions.list_imports()

    @app.get("/api/sessions/{sid}")
    def get_session(sid: str):
        try:
            data = sessions.load_import(sid)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Session not found") from exc
        out = sessions.analyse_export(data)
        out["id"] = sid
        return out

    @app.delete("/api/sessions/{sid}")
    def delete_session(sid: str):
        p = (sessions.sessions_dir() / f"{sid}.json").resolve()
        if p.parent != sessions.sessions_dir().resolve() or not p.exists():
            raise HTTPException(404, "Session not found")
        p.unlink()
        return {"ok": True}

    @app.post("/api/live/sector_targets")
    def set_sector_targets(body: TargetsIn):
        if not body.session_id:
            engine.set_sector_targets(None)
            return {"targets": None}
        try:
            a = sessions.analyse_export(sessions.load_import(body.session_id))
        except FileNotFoundError as exc:
            raise HTTPException(404, "Session not found") from exc
        if not a.get("best_sectors"):
            raise HTTPException(422, "That session has no complete laps with sector times")
        label = f"best sectors – {a.get('track')} ({(a.get('date') or '')[:10]})"
        engine.set_sector_targets(a["best_sectors"], label)
        return {"targets": a["best_sectors"], "label": label}

    # --------------------------------------------------------------- corners
    def lap_track(lap: Lap) -> str:
        return (lap.meta or {}).get("track") or engine.track_name(lap)

    def named_corners(lap: Lap):
        return cmap.apply_names(detect_corners(lap), lap_track(lap))

    @app.get("/api/corners")
    def get_corners(ref: str = "live_ref"):
        """Detected corners of a lap + their current names, for the Corners editor."""
        lap = load_lap(ref)
        track = lap_track(lap)
        cs = named_corners(lap)
        L = lap.track_length or engine.track_length()
        out = []
        for c in cs:
            d = cmap.corner_dict(c)
            d["distance_m"] = round(c.pct * L)
            d["min_speed_kmh"] = round(float(lap.speed[c.apex]) * 3.6)
            out.append(d)
        m = cmap.find_map(track)
        j = lap.to_json()
        return {"track": track, "map_track": m["track"] if m else None, "corners": out,
                "lap": {k: j[k] for k in ("label", "speed", "lat", "lon", "track_length")}}

    @app.post("/api/corners")
    def save_corners(body: CornerMapIn):
        if not body.track.strip():
            raise HTTPException(400, "Track name is required")
        data = cmap.save_map(body.track.strip(), body.corners)
        engine.refresh_corner_names()
        return data

    @app.get("/api/corners/maps")
    def corner_maps():
        return cmap.list_maps()

    @app.get("/api/corners/export")
    def export_corners(track: str):
        m = cmap.find_map(track)
        if not m:
            raise HTTPException(404, "No corner map for this track yet")
        from fastapi.responses import JSONResponse
        return JSONResponse(m, headers={"Content-Disposition":
                                        f'attachment; filename="corners_{cmap.track_key(m["track"])}.json"'})

    @app.post("/api/corners/import")
    def import_corners(body: CornerMapIn):
        data = cmap.save_map(body.track.strip(), body.corners)
        engine.refresh_corner_names()
        return data

    # --------------------------------------------------------------- updates
    @app.get("/api/update")
    def update_status():
        if updater is None:
            return {"status": "disabled", "current": __version__, "mode": config.update_mode}
        return updater.status()

    @app.post("/api/update/check")
    def update_check():
        if updater is None:
            raise HTTPException(400, "Updater not running")
        try:
            return updater.run_once()
        except Exception as exc:
            raise HTTPException(502, f"Update check failed: {exc}") from exc

    @app.post("/api/update/install")
    def update_install():
        if updater is None:
            raise HTTPException(400, "Updater not running")
        st = updater.status()
        if st["status"] == "available":
            updater.download()
        return updater.install(force=True)

    # ----------------------------------------------------------------- coach
    @app.get("/api/coach/report")
    def coach_report():
        with engine.lock:
            rep = engine.coach.report()
            rep["focus_drill"] = engine.coach.focus.status()
        return rep

    @app.post("/api/coach/focus")
    def coach_focus(body: FocusIn):
        with engine.lock:
            if body.action == "stop":
                engine.coach.stop_focus()
            elif body.action == "corner" and body.corner is not None:
                engine.coach.start_focus(body.corner)
            else:
                engine.coach.start_focus(None)
            return engine.coach.focus.status()

    @app.post("/api/voice/test")
    def voice_test():
        engine.coach.voice.say("SimCoach voice check. Brake later into turn one.", min_repeat_s=0)
        return {"backend": engine.coach.voice.backend}

    # --------------------------------------------------------------- overlay
    @app.get("/overlay")
    def overlay_page():
        return FileResponse(STATIC / "overlay.html")

    @app.get("/api/overlay")
    def overlay_state():
        return engine.overlay()

    @app.websocket("/ws/overlay")
    async def ws_overlay(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.send_json(engine.overlay())
                await asyncio.sleep(0.05)
        except Exception:          # client went away (any transport error) - end the loop
            return

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
        except Exception:          # client went away (any transport error) - end the loop
            return

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def _prune_cache(keep: int = 200) -> None:
    """Keep the downloaded-telemetry cache from growing forever on disk."""
    files = sorted(cache_dir().glob("g61_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[keep:]:
        p.unlink(missing_ok=True)


def auto_sector_targets(engine: LiveEngine) -> None:
    """Use best sectors from an imported Garage 61 session for this car/track, if any."""
    sess = engine.session
    if not sess or not engine.sector_targets_auto:
        return
    n = len(sess.get("sectors") or [])
    best = None
    for item in sessions.list_imports():
        if not item.get("track") or not _same_track(sess, item["track"], 0.3):
            continue
        if item.get("car") and sess.get("car") and not (_tokens(item["car"]) & _tokens(sess["car"])):
            continue
        try:
            a = sessions.analyse_export(sessions.load_import(item["id"]))
        except (OSError, ValueError):
            continue
        bs = a.get("best_sectors")
        if bs and (not n or len(bs) == n) and (best is None or sum(bs) < sum(best[0])):
            best = (bs, f"best sectors – Garage 61 {(a.get('date') or '')[:10]}")
    if best:
        engine.set_sector_targets(best[0], best[1], auto=True)


def _same_track(sess: dict, g61_track_name: str, min_score: float = 0.5) -> bool:
    a = _tokens(f"{sess.get('track', '')} {sess.get('track_config', '')}")
    b = _tokens(g61_track_name)
    return bool(a and b) and len(a & b) / len(a | b) >= min_score
