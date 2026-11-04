"""Local web server: REST API + WebSocket live stream + the dashboard UI.

Runs on http://127.0.0.1:8061 by default and is only reachable from this PC.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
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
    lan_access: bool | None = None
    features: dict | None = None
    goal_type: str | None = None
    goal_value: float | None = None


class CornerMapIn(BaseModel):
    track: str
    corners: list[dict]


class OptimalIn(BaseModel):
    track: str | None = None
    include_teammates: bool = True
    set_reference: bool = False


class RacePlanIn(BaseModel):
    race_minutes: float | None = None
    race_laps: int | None = None
    avg_lap: float | None = None
    fuel_per_lap: float | None = None
    tank: float | None = None
    pit_loss_s: float = 60.0
    fuel_now: float | None = None      # plan from now: fuel already in the tank


class FuelSaveIn(BaseModel):
    mode: str = "off"                  # "off" | "target" | "extra_lap"
    save_per_lap: float | None = None


class LapImportIn(BaseModel):
    upload_id: str
    index: int = 0
    driver: str | None = None          # override the teammate's name
    set_reference: bool = False


class ConsistencyIn(BaseModel):
    target: float | None = None        # lap time in seconds; None = set from your pace
    window: float | None = None
    goal: int | None = None


class FocusIn(BaseModel):
    action: str = "auto"               # "auto" | "corner" | "stop"
    corner: int | None = None
    kind: str | None = None            # drill type (drills.DRILLS); None = coach picks from the main issue


class TrainingIn(BaseModel):
    mode: str                          # "free" | "plan" | "drill" | "consistency" | "fuel"
    step: int | None = None            # plan: which step (None = next one not done)
    minutes: int = 45                  # plan: session length when a new plan is made
    corner: int | None = None          # drill: corner index (None = coach picks)
    kind: str | None = None            # drill: drill type
    window: float | None = None        # consistency
    goal: int | None = None
    fuel_mode: str = "extra_lap"       # fuel: "extra_lap" | "target"
    save_per_lap: float | None = None


class FeaturesIn(BaseModel):
    features: dict


class TargetsIn(BaseModel):
    session_id: str | None = None      # imported session id; None = clear (use session best)


class RefIn(BaseModel):
    lap: str                     # "g61:<id>", "local:<file>", "demo:ref" or "session_best"


def create_app(engine: LiveEngine, config: Config, demo_mode: bool = False, updater=None,
               on_quit=None, on_restart_live=None, on_restart=None, bind_host: str = "127.0.0.1",
               port: int = 8061) -> FastAPI:
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

    from . import lan

    @app.middleware("http")
    async def lan_guard(request: Request, call_next):
        """Tablets/phones on the network may use the coaching screens, not change settings."""
        host = request.client.host if request.client else ""
        if not lan.is_local(host) and not lan.allowed_remote(request.method, request.url.path):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Only allowed on the SimCoach PC"}, status_code=403)
        return await call_next(request)

    def _local_only(request: Request):
        if not lan.is_local(request.client.host if request.client else ""):
            raise HTTPException(403, "Only allowed from this PC")

    @app.get("/api/lan")
    def lan_status(request: Request):
        active = bind_host not in ("127.0.0.1", "localhost", "::1")
        return {"enabled": config.lan_access, "active": active, "needs_restart": config.lan_access != active,
                "urls": lan.lan_urls(port) if (active or config.lan_access) else [], "port": port,
                "viewer_is_remote": not lan.is_local(request.client.host if request.client else "")}

    @app.get("/api/lan/qr.svg")
    def lan_qr(url: str):
        from fastapi.responses import Response
        if not url.startswith("http://") or len(url) > 200:
            raise HTTPException(400, "Bad address")
        return Response(lan.qr_svg(url), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})

    @app.post("/api/restart")
    def restart(request: Request):
        _local_only(request)
        if on_restart is None:
            raise HTTPException(400, "Not available")
        on_restart()
        return {"ok": True}

    @app.post("/api/quit")
    def quit_app(request: Request):
        _local_only(request)
        if on_quit is None:
            raise HTTPException(400, "Not available")
        on_quit()
        return {"ok": True}

    @app.post("/api/exit_demo")
    def exit_demo(request: Request):
        """Leave demo mode: start SimCoach in live (iRacing) mode and close this instance."""
        _local_only(request)
        if not demo_mode:
            return {"ok": True, "demo": False}
        if on_restart_live is None:
            raise HTTPException(400, "Not available")
        on_restart_live()
        return {"ok": True, "restarting": True}

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
        if body.voice_mode in ("off", "cues", "detailed", "full"):
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
        if body.lan_access is not None:
            config.lan_access = body.lan_access
        if body.goal_type in ("minutes", "sessions", "laps"):
            config.goal_type = body.goal_type
        if body.goal_value is not None:
            config.goal_value = max(1.0, min(10000.0, float(body.goal_value)))
            engine._goal_announced = False
        if body.features is not None:
            apply_features(body.features)
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
    # ------------------------------------------------- teammate lap files
    uploads: dict[str, dict] = {}       # bounded: last 3 uploads only

    @app.post("/api/laps/upload")
    async def upload_lap_file(request: Request, filename: str = "lap.ibt", lap_time: float | None = None):
        """Upload a teammate's .ibt telemetry file or a lap CSV; returns the laps found."""
        import re as _re
        import uuid
        ext = Path(filename).suffix.lower()
        if ext in (".blap", ".olap"):
            raise HTTPException(415, "iRacing .blap/.olap ghost files use a private format that can't be read "
                                     "reliably. Ask your teammate for the .ibt telemetry file of that session "
                                     "instead (Alt+L in the car turns telemetry logging on; files are in "
                                     "Documents\\iRacing\\telemetry). It contains the same lap and more.")
        if ext not in (".ibt", ".csv"):
            raise HTTPException(415, "Supported files: iRacing .ibt telemetry, or a lap .csv "
                                     "(Garage 61 export or SimCoach lap file).")
        fd, tmp_name = tempfile.mkstemp(suffix=ext, prefix="upload_")
        os.close(fd)                    # mkstemp returns an open handle - close it (Windows locks open files)
        tmp = Path(tmp_name)
        size = 0
        try:
            with open(tmp, "wb") as f:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 4_000_000_000:
                        raise HTTPException(413, "File too large")
                    f.write(chunk)
            if size == 0:
                raise HTTPException(400, "Empty upload")
            if ext == ".ibt":
                from .ibt import IBTError, extract_laps
                try:
                    info, found = await asyncio.to_thread(extract_laps, tmp)
                except IBTError as exc:
                    raise HTTPException(422, str(exc)) from exc
                laps = [x.lap for x in found]
                if not laps:
                    raise HTTPException(422, "No complete laps found in this telemetry file.")
            else:
                text = tmp.read_text(encoding="utf-8", errors="replace")
                is_simcoach = text.startswith("#")
                if is_simcoach:
                    lap = Lap.load(tmp)
                else:
                    has_time = bool(_re.search(r"(?im)^[^\n]*\b(lapcurrentlaptime|sessiontime|time)\b", text.split("\n", 1)[0]))
                    if not lap_time and not has_time:
                        raise HTTPException(422, "This CSV has no time column - enter the lap time and upload again.")
                    try:
                        lap = parse_csv(text, lap_time=lap_time)
                    except ValueError as exc:
                        raise HTTPException(422, f"Could not read this CSV: {exc}") from exc
                    lap.label = f"Teammate {fmt_time(lap.lap_time)}"
                    lap.meta = {"source": "csv", "track": engine.track_name() or ""}
                info = {"track": lap.meta.get("track", ""), "car": lap.meta.get("car", ""),
                        "driver": lap.meta.get("driver", "")}
                laps = [lap]
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError as exc:      # e.g. antivirus still scanning it - the OS temp cleanup will get it
                log.warning("could not remove upload temp file %s: %s", tmp, exc)
        uid = uuid.uuid4().hex[:12]
        uploads[uid] = {"info": info, "laps": laps}
        while len(uploads) > 3:
            uploads.pop(next(iter(uploads)))
        return {"upload_id": uid, "info": info, "laps": [
            {"index": i, "number": l.meta.get("lap"), "lap_time": round(l.lap_time, 3),
             "valid": l.meta.get("valid", True), "label": l.label} for i, l in enumerate(laps)]}

    @app.post("/api/laps/import")
    def import_lap(body: LapImportIn):
        up = uploads.get(body.upload_id)
        if not up or not (0 <= body.index < len(up["laps"])):
            raise HTTPException(404, "Upload expired - please upload the file again.")
        lap = up["laps"][body.index]
        driver = (body.driver or lap.meta.get("driver") or "Teammate").strip()[:40]
        lap.label = f"{driver} {fmt_time(lap.lap_time)}"
        lap.meta = dict(lap.meta, driver=driver, source="teammate:" + str(lap.meta.get("source", "")))
        import datetime as _dt
        import re as _re
        safe = _re.sub(r"[^A-Za-z0-9]+", "_", f"{driver}_{lap.meta.get('track', '')}").strip("_")[:80]
        name = f"{_dt.datetime.now():%Y%m%d_%H%M%S}_teammate_{safe}_{lap.lap_time:.3f}.csv"
        lap.meta.setdefault("date", _dt.datetime.now().isoformat(timespec="seconds"))
        lap.save(laps_dir() / name)
        if body.set_reference:
            engine.set_reference(lap)
        return {"file": name, "label": lap.label, "reference": engine.ref_label if body.set_reference else None}

    # ------------------------------------------------------- optimal lap
    @app.post("/api/optimal")
    def build_optimal_lap(body: OptimalIn):
        from .optimal import build_optimal, same_track
        track = (body.track or engine.track_name() or "").strip()
        cands, files_old = [], []
        for p in sorted(laps_dir().glob("*.csv"), reverse=True)[:400]:
            try:
                lap = Lap.load(p)
            except (OSError, ValueError):
                continue
            src = str(lap.meta.get("source", ""))
            if src == "optimal":
                if same_track(lap.meta.get("track", ""), track):
                    files_old.append(p)
                continue
            if not lap.meta.get("valid", True) or (src.startswith("teammate") and not body.include_teammates):
                continue
            if track and not same_track(lap.meta.get("track", ""), track):
                continue
            cands.append(lap)
        if not track and cands:
            track = cands[0].meta.get("track", "")
            cands = [l for l in cands if same_track(l.meta.get("track", ""), track)]
        try:
            lap, segs = build_optimal(cands)
        except ValueError as exc:
            raise HTTPException(422, f"{exc} (found {len(cands)} clean lap(s) for '{track or 'this track'}')") from exc
        for p in files_old:                       # keep one optimal lap per track
            p.unlink(missing_ok=True)
        import datetime as _dt
        import re as _re
        name = f"{_dt.datetime.now():%Y%m%d_%H%M%S}_optimal_{_re.sub(r'[^A-Za-z0-9]+', '_', track)[:60]}.csv"
        lap.meta["date"] = _dt.datetime.now().isoformat(timespec="seconds")
        lap.save(laps_dir() / name)
        if body.set_reference:
            engine.set_reference(lap)
        return {"file": name, "label": lap.label, "lap_time": round(lap.lap_time, 3),
                "best_single_lap": lap.meta["best_single_lap"], "laps_used": len({s.source for s in segs}),
                "candidates": len(cands), "segments": lap.meta["segments"], "track": track}

    # ------------------------------------------------------------ progress
    @app.get("/api/progress/combos")
    def progress_combos():
        from . import history
        return history.combos()

    @app.get("/api/progress")
    def progress(track: str = "", car: str = ""):
        from . import history
        track = track or engine.track_name()
        car = car or engine.session.get("car", "")
        if not track:
            combos = history.combos()
            if combos:
                track, car = combos[0]["track"], combos[0]["car"]
        return history.progress(track, car)

    @app.get("/api/practice_plan")
    def practice_plan(track: str = "", car: str = "", minutes: int = 45):
        need("practice")
        return make_plan(track, car, minutes)

    def make_plan(track: str = "", car: str = "", minutes: int = 45) -> dict:
        from . import history
        with engine.lock:
            rep = engine.coach.report()
            grades = (engine.last_comparison or {}).get("scores")
        source = "this session"
        if not rep.get("laps"):
            sessions = history.load_sessions(track or engine.track_name(), car or engine.session.get("car", ""))
            if not sessions:
                sessions = history.load_sessions()
            if not sessions:
                return {"plan": [], "source": None,
                        "note": "Drive a session against a reference first - the plan is built from it."}
            last = sessions[-1]
            rep, grades, source = last["report"], last.get("grades"), f"your last session ({last['date'][:8]})"
        plan = history.practice_plan(rep, grades, minutes)
        with engine.lock:
            engine.coach.set_plan(plan)
        return {"plan": engine.coach.plan, "source": source}

    @app.get("/report")
    def report_page():
        return FileResponse(STATIC / "report.html")

    @app.get("/api/report")
    def session_report():
        """Everything for the printable post-session report."""
        import datetime as _dt
        import statistics as _st
        from . import history
        with engine.lock:
            rep = engine.coach.report()
            comp = engine.last_comparison
            last, ref = engine.last_lap, engine.reference
            corners = list(engine.ref_corners)
            hist = list(engine.coach.history)
            plan = list(engine.coach.plan)
            track, car = engine.track_name(), engine.session.get("car", "")
            driver = engine.session.get("driver", "")
        source = "live"
        if not rep.get("laps"):                       # no laps this run: use the last saved session
            sessions = history.load_sessions(track, car) or history.load_sessions()
            if not sessions:
                raise HTTPException(404, "No session to report on yet - drive some laps against a reference.")
            s = sessions[-1]
            rep = dict(s["report"], laps=s.get("valid_laps"), best_lap=s.get("best"), trend=[])
            grades = s.get("grades", {})
            track, car, source = s.get("track", ""), s.get("car", ""), f"saved session {s['date']}"
            comp, last = None, None
        else:
            keys = {k for h in hist for k in (h.get("scores") or {})}
            grades = {k: round(_st.fmean([h["scores"][k] for h in hist if (h.get("scores") or {}).get(k) is not None]))
                      for k in keys if any((h.get("scores") or {}).get(k) is not None for h in hist)}
        if not plan:
            plan = history.practice_plan(rep, grades, 45)
        top = sorted([c for c in rep.get("corners", []) if (c.get("avg_loss") or 0) > 0.05],
                     key=lambda c: c["avg_loss"], reverse=True)[:3]
        details = []
        for c in top:
            d = {"corner": c}
            idx = c.get("index")
            if comp and idx is not None and idx < len(comp["corners"]):
                d["last_lap"] = comp["corners"][idx]
            if last is not None and ref is not None and idx is not None and idx < len(corners):
                k = corners[idx]
                a, b = max(0, k.start - 25), min(len(ref.speed), k.end + 25)
                seg = lambda arr: None if arr is None else [round(float(x), 6) for x in arr[a:b]]  # noqa: E731
                d["trace"] = {"start": a, "apex": k.apex - a, "me_speed": seg(last.speed), "ref_speed": seg(ref.speed),
                              "me_brake": seg(last.brake), "ref_brake": seg(ref.brake),
                              "me_throttle": seg(last.throttle), "ref_throttle": seg(ref.throttle),
                              "me_lat": seg(last.lat) if last.has_map() else None,
                              "me_lon": seg(last.lon) if last.has_map() else None,
                              "ref_lat": seg(ref.lat) if ref.has_map() else None,
                              "ref_lon": seg(ref.lon) if ref.has_map() else None}
            details.append(d)
        prog = history.progress(track, car) if track else {"recurring": []}
        return {"generated": _dt.datetime.now().isoformat(timespec="minutes"), "version": __version__,
                "source": source, "track": track, "car": car, "driver": driver,
                "reference": engine.ref_label, "report": rep, "grades": grades,
                "last_scores": (comp or {}).get("scores"), "top": details, "plan": plan,
                "recurring": prog.get("recurring", []), "units": config.units}

    @app.get("/api/plan")
    def current_plan():
        with engine.lock:
            return {"plan": engine.coach.plan, "focus": engine.coach.focus.status()}

    @app.post("/api/plan/{i}/start")
    def start_plan_step(i: int):
        need("practice")
        with engine.lock:
            if 0 <= i < len(engine.coach.plan):
                if engine.coach.plan[i].get("drill"):
                    need("drills")
                if engine.coach.plan[i].get("consistency"):
                    need("consistency")
            try:
                step = engine.coach.start_plan_step(i)
            except IndexError as exc:
                raise HTTPException(404, "No such plan step - make a new plan") from exc
            if step.get("consistency"):
                engine.consistency.start(None, step["consistency"].get("window"), step["consistency"].get("goal"))
            return {"step": step, "plan": engine.coach.plan, "focus": engine.coach.focus.status()}

    @app.post("/api/plan/{i}/done")
    def done_plan_step(i: int, status: str = "done"):
        with engine.lock:
            engine.coach.mark_plan_step(i, status)
            return {"plan": engine.coach.plan}

    # --------------------------------------------------------- race / fuel
    @app.get("/api/race")
    def race_status():
        return engine.race_status()

    @app.post("/api/race/plan")
    def race_plan(body: RacePlanIn):
        need("endurance")
        from .race import lift_plan, plan_race
        st = engine.race_status()
        avg = body.avg_lap or st.get("stint_avg") or (engine.reference.lap_time if engine.reference else None)
        fpl = body.fuel_per_lap or st.get("fuel_per_lap")
        tank = body.tank or st.get("tank")
        if not (avg and fpl and tank):
            raise HTTPException(422, "Need lap time, fuel per lap and tank size - drive a few laps or enter them.")
        cost = None
        base = engine.last_lap or engine.session_best or engine.reference
        if base is not None:
            lp = lift_plan(base, target_save_per_lap=max(0.05, fpl * 0.05), fuel_per_lap=fpl)
            cost = lp.get("cost_per_litre_s")
        try:
            return plan_race(avg, fpl, tank, race_time_s=(body.race_minutes or 0) * 60 or None,
                             race_laps=body.race_laps, pit_loss_s=body.pit_loss_s, lift_cost_per_litre=cost,
                             fuel_now=body.fuel_now)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/race/sources")
    def race_sources(car: int | None = None, track: int | None = None, scope: str = "me"):
        """Lap time + fuel per lap for the planner from Garage 61, imported exports and the live session."""
        from .race import pace_stats
        out: dict = {"live": None, "garage61": None, "export": None}
        # live session: time left, fuel in the tank, current pace
        st = engine.race_status()
        s = engine.last_sample or {}
        tl = s.get("time_remain", -1.0)
        ll = s.get("laps_remain", -1.0)
        if engine.connected and s:
            out["live"] = {"time_left_s": tl if tl is not None and tl > 0 else None,
                           "laps_left": ll if ll is not None and 0 <= ll < 30000 else None,
                           "fuel_now": s.get("fuel") or None, "tank": st.get("tank"),
                           "lap_time": st.get("stint_avg"), "fuel_per_lap": st.get("fuel_per_lap"),
                           "session_type": st.get("session_type")}
        # Garage 61: your laps (or the team's) in this car at this track
        try:
            g = g61()
            car_id, track_id = car, track
            if (car_id is None or track_id is None) and engine.session:
                if car_id is None:
                    m = g.match_car(engine.session.get("car", ""))
                    car_id = m.get("id") if m else None
                if track_id is None:
                    m = g.match_track(engine.session.get("track", ""), engine.session.get("track_config", ""))
                    track_id = m.get("id") if m else None
            if car_id and track_id:
                laps = g.find_laps(cars=[car_id], tracks=[track_id], drivers=["me"] if scope == "me" else None,
                                   group="none", telemetry_required=False, limit=300)
                rows = [describe_lap(l) for l in laps]
                stats = pace_stats([{"lap_time": r["lap_time"], "fuel_used": r["fuel_used"],
                                     "clean": r.get("clean", True)} for r in rows])
                out["garage61"] = dict(stats, scope=scope, car_id=car_id, track_id=track_id,
                                       note=None if stats["fuel_per_lap"] else
                                       "Garage 61 returned lap times but no fuel figures for these laps.")
            else:
                out["garage61"] = {"error": "Pick the car and track on the Laps tab (or be in a session) "
                                            "to fetch Garage 61 laps."}
        except Garage61Error as exc:
            out["garage61"] = {"error": str(exc)}
        # imported Garage 61 session exports (have fuel used per lap)
        track_name = engine.track_name()
        best_exp = None
        for item in sessions.list_imports():
            if track_name and not _same_track(engine.session or {"track": track_name}, item.get("track", ""), 0.3):
                continue
            try:
                data = sessions.load_import(item["id"])
            except (OSError, ValueError):
                continue
            laps = [l for sess in data.get("sessions", []) for l in sess.get("laps", [])
                    if not l.get("pit_in") and not l.get("pit_out") and all(x is not None for x in l.get("sectors", []))]
            stats = pace_stats([{"lap_time": l["lap_time"], "fuel_used": l.get("fuel_used"),
                                 "clean": l.get("clean", True)} for l in laps])
            if stats["laps"] and (best_exp is None or stats["laps"] > best_exp["laps"]):
                best_exp = dict(stats, track=data.get("track"), car=data.get("car"), date=data.get("date"))
        out["export"] = best_exp
        return out

    @app.post("/api/fuelsave")
    def fuel_save(body: FuelSaveIn):
        if body.mode != "off":
            need("endurance")
        if body.mode == "off":
            engine.disable_fuel_save()
            return {"active": False}
        plan = engine.enable_fuel_save(save_per_lap=body.save_per_lap if body.mode == "target" else None,
                                       extra_lap=body.mode == "extra_lap")
        if not plan.get("available"):
            raise HTTPException(422, plan.get("reason", "Fuel saving plan not available"))
        return {"active": True, **plan}

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
    def need(feature: str):
        if not config.on(feature):
            from .config import FEATURES
            raise HTTPException(409, f"'{FEATURES[feature]}' is switched off in Settings → Training features.")

    def apply_features(changes: dict) -> None:
        from .config import FEATURES
        with engine.lock:
            for k, v in changes.items():
                if k in FEATURES:
                    config.features[k] = bool(v)
            if not config.on("drills"):
                engine.coach.stop_focus()
            if not config.on("consistency"):
                engine.consistency.stop()
            if not config.on("endurance"):
                engine.disable_fuel_save()

    @app.post("/api/features")
    def set_features(body: FeaturesIn):
        """Training features on/off - allowed from the phone too (no other settings)."""
        from .config import FEATURES
        apply_features(body.features)
        config.save()
        return {"features": dict(config.features), "labels": FEATURES}

    # -------------------------------------------------------------- training
    def training_state() -> dict:
        from . import drills
        from .config import FEATURES
        with engine.lock:
            rep = engine.coach.report()
            st = {
                "mode": engine.training_mode(),
                "features": dict(config.features),
                "feature_labels": FEATURES,
                "plan": engine.coach.plan,
                "focus": engine.coach.focus.status(),
                "consistency": engine.consistency.status(),
                "fuel": engine._fuel_overlay(),
                "fuel_save": bool(engine.fuel_save),
                "fuel_target": engine.fuel_target_per_lap(),
                "corners": [{"index": c["index"], "name": c["name"], "title": c["title"],
                             "avg_loss": c["avg_loss"], "main_issue": c["main_issue"]} for c in rep["corners"]],
                "drills": {k: d["title"] for k, d in drills.DRILLS.items()},
                "connected": engine.connected, "on_track": bool((engine.last_sample or {}).get("on_track")),
                "track": engine.track_name(), "car": engine.session.get("car", ""),
                "lap": engine.lap_count, "units": config.units,
                "last_laps": list(engine.laps_done)[-8:],
            }
        st["game"] = engine.game.status() if config.on("game") else None
        return st

    @app.get("/api/training")
    def training():
        return training_state()

    @app.post("/api/training/select")
    def training_select(body: TrainingIn):
        """Switch what you're training (from the dashboard or the phone)."""
        mode = body.mode
        if mode not in ("free", "plan", "drill", "consistency", "fuel"):
            raise HTTPException(422, "Unknown training mode")
        need_map = {"plan": "practice", "drill": "drills", "consistency": "consistency", "fuel": "endurance"}
        if mode in need_map:
            need(need_map[mode])
        if mode == "plan":
            with engine.lock:
                has_plan = bool(engine.coach.plan)
            if not has_plan or (body.step is None and all(p["status"] in ("done", "skipped")
                                                            for p in engine.coach.plan)):
                made = make_plan(minutes=body.minutes)
                if not made["plan"]:
                    raise HTTPException(422, made.get("note") or "No plan yet - drive a few laps first.")
            with engine.lock:
                i = body.step
                if i is None:
                    i = next((k for k, p in enumerate(engine.coach.plan) if p["status"] not in ("done", "skipped")), 0)
            engine.stop_training()
            start_plan_step(i)
        elif mode == "fuel":
            fuel_save(FuelSaveIn(mode="target" if body.fuel_mode == "target" else "extra_lap",
                                 save_per_lap=body.save_per_lap))      # raises if there's no plan yet
            engine.stop_training(keep_fuel=True)
        elif mode == "consistency":
            engine.stop_training()
            consistency_start(ConsistencyIn(window=body.window, goal=body.goal))
        elif mode == "drill":
            engine.stop_training()
            coach_focus(FocusIn(action="corner" if body.corner is not None else "auto",
                                corner=body.corner, kind=body.kind))
        else:
            engine.stop_training()
        return training_state()

    @app.get("/api/game")
    def game_status():
        need("game")
        return engine.game.status()

    @app.get("/api/widget")
    def widget_state():
        """Everything the small widgets need, in one poll."""
        st = training_state()
        st["race"] = engine.race_status() if config.on("endurance") else None
        with engine.lock:
            snap_s = engine.last_sample or {}
            st["session_type"] = engine.session_type
            st["time_left"] = snap_s.get("time_remain") if (snap_s.get("time_remain") or -1) > 0 else None
        return st

    @app.get("/train")
    def train_page():
        return FileResponse(STATIC / "train.html")

    @app.get("/widget/{name}")
    def widget_page(name: str):
        if name not in ("consistency", "endurance", "fuel", "plan"):
            raise HTTPException(404, "Widgets: consistency, endurance, fuel, plan")
        return FileResponse(STATIC / "widget.html")

    @app.get("/api/goals")
    def weekly_goal():
        need("goals")
        with engine.lock:
            return engine.weekly_goal()

    @app.get("/api/features")
    def features():
        from .config import FEATURES
        return {"features": dict(config.features), "labels": FEATURES}

    # ----------------------------------------------------------- consistency
    @app.get("/api/consistency")
    def consistency_status():
        return engine.consistency.status()

    @app.post("/api/consistency/start")
    def consistency_start(body: ConsistencyIn):
        need("consistency")
        with engine.lock:
            st = engine.consistency.start(body.target, body.window, body.goal)
        engine.coach._say("Consistency run. Same lap, every lap", important=True)
        return st

    @app.post("/api/consistency/stop")
    def consistency_stop():
        with engine.lock:
            engine.consistency.stop()
            return engine.consistency.status()

    @app.get("/api/coach/report")
    def coach_report():
        with engine.lock:
            rep = engine.coach.report()
            rep["focus_drill"] = engine.coach.focus.status()
        return rep

    @app.post("/api/coach/focus")
    def coach_focus(body: FocusIn):
        if body.action != "stop":
            need("drills")
        with engine.lock:
            if body.action == "stop":
                engine.coach.stop_focus()
            elif body.action == "corner" and body.corner is not None:
                engine.coach.start_focus(body.corner, kind=body.kind)
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
