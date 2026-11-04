import os
import tempfile

os.environ.setdefault("SIMCOACH_HOME", tempfile.mkdtemp(prefix="simcoach_test_"))
os.environ["SIMCOACH_NO_NATIVE_VOICE"] = "1"   # never talk out loud during tests

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from simcoach import demo  # noqa: E402
from simcoach.analysis import compare_laps, detect_corners  # noqa: E402
from simcoach.config import Config  # noqa: E402
from simcoach.garage61 import best_match, describe_lap  # noqa: E402
from simcoach.lap import GRID, N_BINS, Lap, estimate_track_length, parse_csv  # noqa: E402
from simcoach.live import DemoSource, LapBuffer, LiveEngine, parse_track_length  # noqa: E402


def test_detects_all_demo_corners():
    corners = detect_corners(demo.reference_lap())
    assert len(corners) == len(demo.CORNERS)
    for c, (pct, _) in zip(corners, demo.CORNERS):
        assert abs(c.pct - pct) < 0.01


def test_comparison_finds_planted_mistakes():
    ref = demo.reference_lap()
    me = demo.make_lap(demo.YOU_STYLE, "me")
    cmp = compare_laps(me, ref)
    d = cmp.to_dict()
    assert d["gap"] > 0.3
    by = {c.name: c for c in cmp.corners}
    # C3 (index 2): brakes 25 m early and 2.5 m/s slower apex
    c3 = by["C3"]
    assert c3.time_lost > 0.1
    assert c3.brake_point_m < -10
    assert c3.min_speed_diff_kmh < -5
    assert any("too early" in t for t in c3.tips)
    # C7 (index 6): slow apex + weak exit
    assert by["C7"].exit_lost > 0.05
    assert "C3" in d["focus"]
    # sum of corner losses ~= total gap
    assert abs(sum(c.time_lost for c in cmp.corners) - d["gap"]) < 0.05


def test_identical_laps_no_tips():
    ref = demo.reference_lap()
    cmp = compare_laps(ref, ref)
    assert abs(cmp.to_dict()["gap"]) < 1e-6
    assert all(not c.tips for c in cmp.corners)


def test_g61_style_csv_without_time_column():
    ref = demo.reference_lap()
    lap = parse_csv(demo.demo_ref_csv(), lap_time=ref.lap_time)
    assert abs(lap.lap_time - ref.lap_time) < 0.01
    assert abs(lap.track_length - demo.TRACK_LENGTH) / demo.TRACK_LENGTH < 0.01
    assert np.max(np.abs(lap.time - ref.time)) < 0.05
    assert lap.has_map()


def test_csv_kmh_and_percent_units():
    ref = demo.reference_lap()
    rows = ["Speed (km/h);LapDistPct;Throttle;Brake"]
    for i in range(N_BINS):
        rows.append(f"{ref.speed[i]*3.6:.3f};{GRID[i]*100:.4f};{ref.throttle[i]*100:.1f};{ref.brake[i]*100:.1f}")
    lap = parse_csv("\n".join(rows), lap_time=ref.lap_time)
    assert np.allclose(lap.speed, ref.speed, atol=0.05)
    assert lap.throttle.max() <= 1.0


def test_save_load_roundtrip(tmp_path):
    ref = demo.reference_lap()
    p = tmp_path / "x.csv"
    ref.save(p)
    back = Lap.load(p)
    assert abs(back.lap_time - ref.lap_time) < 0.01
    assert abs(back.track_length - ref.track_length) < 1
    assert back.label == ref.label


def test_estimate_track_length():
    ref = demo.reference_lap()
    assert abs(estimate_track_length(ref.speed, ref.lap_time) - demo.TRACK_LENGTH) < 5


def test_lap_buffer_and_engine_with_simulated_samples():
    cfg = Config(record_laps=False)
    eng = LiveEngine(cfg, DemoSource())
    eng.set_reference(demo.reference_lap())
    eng.session = eng.source.session()
    # feed 2.5 laps of synthetic samples at 60 Hz without real time passing
    src = eng.source
    for _ in range(int(60 * demo.reference_lap().lap_time * 2.6)):
        src._last -= 1 / 60  # pretend 1/60 s elapsed
        eng._process(src.read())
    assert len(eng.laps_done) >= 2
    lap_info = eng.laps_done[0]
    assert lap_info["gap"] > 0.2          # demo "you" driver is slower
    assert eng.last_comparison is not None
    snap = eng.snapshot()
    assert "delta" in snap and "pct" in snap
    assert eng.trace()["filled_to"] > 0


def test_parse_track_length():
    assert parse_track_length("5.51 km") == pytest.approx(5510)
    assert parse_track_length("2.50 mi") == pytest.approx(4023.36)
    assert parse_track_length("") == 0


def test_match_and_describe():
    tracks = [{"id": 1, "name": "Spa-Francorchamps", "variant": "Grand Prix"},
              {"id": 2, "name": "Monza", "variant": "Combined"}]
    m = best_match(tracks, "Circuit de Spa-Francorchamps Grand Prix",
                   lambda t: f"{t['name']} {t['variant']}")
    assert m["id"] == 1
    d = describe_lap({"id": "abc", "driver": {"firstName": "A", "lastName": "B"},
                      "lapTime": 90.1, "car": {"name": "GT3"}, "track": {"name": "Monza"}})
    assert d["driver"] == "A B" and d["lap_time"] == 90.1


def test_api_endpoints():
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    cfg = Config()
    eng = LiveEngine(cfg, DemoSource())
    eng.set_reference(demo.reference_lap())
    client = TestClient(create_app(eng, cfg, demo_mode=True))
    assert client.get("/").status_code == 200
    assert client.get("/api/status").json()["demo"] is True
    r = client.get("/api/compare", params={"mine": "demo:you", "ref": "demo:ref"}).json()
    assert r["comparison"]["gap"] > 0
    assert len(r["corners"]) == len(demo.CORNERS)
    assert client.get("/api/g61/laps").status_code == 401   # no token configured
    assert client.post("/api/live/reference", json={"lap": "demo:ref"}).status_code == 200
    assert client.get("/api/compare", params={"mine": "demo:you", "ref": "live_ref"}).status_code == 200
    assert client.get("/api/local/laps/../../etc").status_code in (404, 405)
    with client.websocket_connect("/ws/live") as ws:
        assert ws.receive_json()["type"] == "snap"


# ---------------------------------------------------------------- v2 features
from pathlib import Path  # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "Garage61_IMSA_LeMans_DallaraP217_export.xlsx"


def test_parse_garage61_session_export():
    from simcoach.sessions import analyse_export, parse_g61_export
    d = parse_g61_export(SAMPLE)
    assert d["car"] == "Dallara P217"
    assert "Mans" in d["track"]
    names = [s["name"] for s in d["sessions"]]
    assert names == ["Qualify", "Race"]
    race = d["sessions"][1]
    assert race["sector_count"] == 7 and len(race["laps"]) == 15
    a = analyse_export(d)
    r = a["sessions"][1]
    assert r["best_lap"]["lap_time"] == pytest.approx(218.637)
    assert r["theoretical_best"] < r["best_lap"]["lap_time"]
    assert len(a["best_sectors"]) == 7
    assert r["focus_sectors"]          # some sector flagged
    assert r["tips"]


def test_turn_in_detected():
    cmp = compare_laps(demo.make_lap(demo.YOU_STYLE, "me"), demo.reference_lap())
    c2 = {c.name: c for c in cmp.corners}["C2"]
    assert c2.turn_in_m == pytest.approx(demo.YOU_STYLE.turn_in_late_m[1], abs=6)
    assert any("Turning in" in t for t in c2.tips)


def _drive(eng, laps=2.3):
    src = eng.source
    eng.session = src.session()
    for _ in range(int(60 * demo.reference_lap().lap_time * laps)):
        src._last -= 1 / 60
        eng._process(src.read())


def test_live_phase_events_sectors_and_overlay():
    from simcoach.live import classify
    cfg = Config(record_laps=False)
    eng = LiveEngine(cfg, DemoSource())
    eng.set_reference(demo.reference_lap())
    _drive(eng, 2.6)
    kinds = {e["kind"] for e in eng.events}
    assert {"brake", "turn_in", "min_speed", "throttle"} <= kinds
    # C3 has a planted 20 m early brake
    early = [e for e in eng.events if e["corner"] == "C3" and e["kind"] == "brake"]
    assert early and early[-1]["value"] < -8 and early[-1]["severity"] == "bad"
    late_ti = [e for e in eng.events if e["corner"] == "C2" and e["kind"] == "turn_in"]
    assert late_ti and late_ti[-1]["value"] > 8
    # sectors: 4 demo sectors, session-best targets after the first full lap
    assert eng.laps_done[0]["sectors"] and len(eng.laps_done[0]["sectors"]) == 4
    assert abs(sum(eng.laps_done[0]["sectors"]) - eng.laps_done[0]["lap_time"]) < 0.05
    assert eng.cur_sectors and eng.cur_sectors[0]["delta"] is not None
    ov = eng.overlay()
    assert ov["visible"] is True and ov["session_type"] == "Practice"
    cfg.overlay_mode = "off"
    assert eng.overlay()["visible"] is False
    eng.session["session_types"] = {0: "Race"}
    cfg.overlay_mode = "practice"
    assert eng.overlay()["visible"] is False
    assert classify("min_speed", -6)[1] == "bad"
    assert classify("brake", -15)[0].startswith("Brake 15 m too early")


def test_sector_targets_from_import():
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    cfg = Config()
    eng = LiveEngine(cfg, DemoSource())
    client = TestClient(create_app(eng, cfg))
    r = client.post("/api/sessions/import", params={"filename": SAMPLE.name}, content=SAMPLE.read_bytes())
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert any(x["id"] == sid for x in client.get("/api/sessions").json())
    a = client.get(f"/api/sessions/{sid}").json()
    assert a["sessions"][1]["lap_list"]
    # auto-match: pretend iRacing is at Le Mans in the P217 with 7 sectors
    eng.session = {"track": "Circuit des 24 Heures du Mans", "track_config": "24 Heures du Mans",
                   "car": "Dallara P217", "sectors": [i / 7 for i in range(7)], "session_types": {}}
    from simcoach.server import auto_sector_targets
    auto_sector_targets(eng)
    assert eng.sector_targets and len(eng.sector_targets) == 7
    assert client.post("/api/live/sector_targets", json={"session_id": sid}).status_code == 200
    assert client.get("/overlay").status_code == 200
    assert "visible" in client.get("/api/overlay").json()
    assert client.post("/api/sessions/import", content=b"not a workbook").status_code == 422


# ------------------------------------------------------- v3: coach, voice, memory
def test_trail_braking_and_grades():
    cmp = compare_laps(demo.make_lap(demo.YOU_STYLE, "me"), demo.reference_lap())
    c3 = {c.name: c for c in cmp.corners}["C3"]
    assert c3.issues[0] == "brake_early" and "no_trail" in c3.issues
    sc = cmp.to_dict()["scores"]
    assert 0 <= sc["braking"] < 100 and sc["technique"] < 100
    perfect = compare_laps(demo.reference_lap(), demo.reference_lap()).to_dict()["scores"]
    assert perfect["technique"] == 100 and perfect["pace"] == 100


def test_voice_queue_is_bounded_and_deduped():
    from simcoach.voice import VoiceCoach, spoken_seconds
    v = VoiceCoach(native=False, log_size=5)
    assert v.say("C3, brake later")
    assert not v.say("C3, brake later")          # repeat suppressed
    for i in range(50):
        v.say(f"msg {i}", min_repeat_s=0)
    assert len(v.log) == 5 and len(v._recent) <= 65
    assert spoken_seconds(0.21) == "two tenths" and spoken_seconds(0.08) == "one tenth"


def test_session_coach_report_focus_and_cues():
    eng = LiveEngine(Config(record_laps=False, voice_native=False), DemoSource())
    eng.coach.voice.native = False
    eng.set_reference(demo.reference_lap())
    _drive(eng, 3.6)
    rep = eng.coach.report()
    assert rep["laps"] >= 2 and rep["corners"]
    worst = max(rep["corners"], key=lambda c: c["avg_loss"])
    assert worst["name"] in ("C3", "C7") and worst["main_issue"]
    assert rep["summary"]
    spoken = [v["text"] for v in eng.coach.voice.log]
    assert any(t.startswith("C3,") for t in spoken)       # pre-corner cue from last lap's mistake
    # drill mode picks the worst corner automatically
    st = eng.coach.start_focus(None)
    assert st["active"] and st["name"] == worst["name"]
    _drive(eng, 1.2)
    assert eng.coach.focus.attempts >= 1
    assert eng.overlay()["focus"]["name"] == worst["name"]


def test_drill_completes_and_moves_on():
    from simcoach.coach import SessionCoach
    from simcoach.voice import VoiceCoach
    c = SessionCoach(VoiceCoach(native=False))
    comp = {"gap": 0.5, "scores": {}, "corners": [
        {"name": "C1", "time_lost": 0.3, "issues": ["brake_early"]},
        {"name": "C2", "time_lost": 0.2, "issues": ["coasting_unknown"]}]}
    c.add_lap(1, 90.0, True, comp)
    c.start_focus(None)
    assert c.focus.name == "C1" and c.focus.kind == "brake_ladder"      # braking too early -> ladder
    # ladder: start at -20 m, then 5 m later each lap until the reference, then hold it twice
    for bp in (-20, -15, -10, -5, 0, 0, 0):
        c.on_corner(0, {"name": "C1", "time_lost": 0.05, "issues": [], "brake_point_m": bp,
                        "min_speed_diff_kmh": 0.0})
        if "C1" in c.focus.completed:
            break
    assert "C1" in c.focus.completed and c.focus.name == "C2" and c.focus.kind == "time"
    for _ in range(3):
        c.on_corner(1, {"name": "C2", "time_lost": 0.01, "issues": []})
    assert "C2" in c.focus.completed


def test_drill_library_evaluations():
    from simcoach.drills import drill_for, evaluate
    assert drill_for("no_trail") == "trail_brake" and drill_for("turn_in_late") == "turn_in"
    assert drill_for("low_min_speed") == "min_speed" and drill_for("wheelspin") == "throttle"
    assert drill_for("whatever") == "time"
    assert evaluate("trail_brake", {"trail_m_diff": -3}, {}, 0.05)["ok"]
    r = evaluate("trail_brake", {"trail_m_diff": -20}, {}, 0.05)
    assert not r["ok"] and r["say"] == "Trail the brake deeper"
    assert evaluate("turn_in", {"turn_in_m": 12}, {}, 0.05)["say"] == "Turn in earlier"
    assert evaluate("throttle", {"throttle_point_m": 0, "wheelspin_m_diff": 10}, {}, 0.05)["say"] == \
        "Smoother on the throttle"
    st = {}
    for t in (0.20, 0.25, 0.22):
        r = evaluate("consistency", {"time_lost": t}, st, 0.05)
    assert r["done"]
    # ladder overshoot locks the last good point
    st = {}
    evaluate("brake_ladder", {"brake_point_m": -20, "time_lost": 0.2}, st, 0.05)
    evaluate("brake_ladder", {"brake_point_m": -15, "time_lost": 0.15}, st, 0.05)
    r = evaluate("brake_ladder", {"brake_point_m": -10, "time_lost": 0.4, "min_speed_diff_kmh": -6}, st, 0.05)
    assert st["locked"] == -15 and "Back off" in r["say"]
    assert evaluate("brake_ladder", {"brake_point_m": -14, "time_lost": 0.12}, st, 0.05)["ok"]

def test_no_memory_growth_over_long_session():
    """Simulate a long stint; memory after warm-up must stay flat."""
    import gc
    import tracemalloc
    eng = LiveEngine(Config(record_laps=False, voice_native=False), DemoSource())
    eng.coach.voice.native = False
    eng.set_reference(demo.reference_lap())
    eng.coach.start_focus(None)
    # shrink every per-lap history cap so the warm-up fills them; after that, growth must be ~0
    import collections as _c
    eng.laps_done = _c.deque(maxlen=5)
    eng.history_laps = _c.deque(maxlen=5)
    eng.coach.history = _c.deque(maxlen=5)
    eng.race.max_laps = 5
    eng.coach.voice.log = _c.deque(maxlen=5)
    src = eng.source
    eng.session = src.session()
    per_lap = int(60 * 90)

    def run(laps):
        for _ in range(per_lap * laps):
            src._last -= 1 / 60
            eng._process(src.read())
            eng.snapshot() if _ % 3 == 0 else None
            eng.overlay() if _ % 3 == 0 else None

    run(6)                                  # warm-up: fill the (shrunken) caps, numpy pools
    gc.collect()
    tracemalloc.start()
    def to_lap_end():                       # measure at the same point of a lap each time
        n = eng.lap_count
        while eng.lap_count == n:
            src._last -= 1 / 60
            eng._process(src.read())

    run(2)                                  # settle one-off allocations (first comparisons, history file)
    samples = []
    for _ in range(12):
        to_lap_end()
        gc.collect()
        samples.append(tracemalloc.get_traced_memory()[0])
    tracemalloc.stop()
    spread = max(samples) - min(samples)
    # Bounded: memory may differ by one retained lap (~105 KB: "last lap" and "session best" are
    # separate laps until the latest lap becomes the best). A per-lap leak of >=13 KB fails this.
    assert spread < 150_000, f"memory not flat over 12 laps: {[round(x / 1024) for x in samples]} KiB"
    assert len(eng.events) <= 60 and len(eng.coach.history) <= 5 and len(eng.race.laps) <= 5


# ------------------------------------------------------------------ v4: auto-update
class _FakeResp:
    def __init__(self, status=200, json_data=None, text="", content=b""):
        self.status_code, self._json, self.text, self._content = status, json_data, text, content

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_release(payload: bytes, digest=True, sums=True, tag="v9.9.9"):
    import hashlib
    sha = hashlib.sha256(payload).hexdigest()
    assets = [{"name": f"SimCoach-Setup-{tag[1:]}.exe", "size": len(payload),
               "browser_download_url": f"https://github.com/o/r/releases/download/{tag}/SimCoach-Setup-{tag[1:]}.exe",
               **({"digest": f"sha256:{sha}"} if digest else {})}]
    if sums:
        assets.append({"name": "SHA256SUMS.txt",
                       "browser_download_url": f"https://github.com/o/r/releases/download/{tag}/SHA256SUMS.txt"})
    rel = {"tag_name": tag, "assets": assets, "body": "notes", "html_url": "https://github.com/o/r/releases/x"}
    return rel, f"{sha}  SimCoach-Setup-{tag[1:]}.exe\n"


def _updater_with(rel, sums_text, payload):
    from simcoach.updater import Updater

    def get(url, **kw):
        if url.endswith("/releases/latest"):
            return _FakeResp(json_data=rel) if rel else _FakeResp(status=404)
        if url.endswith("SHA256SUMS.txt"):
            return _FakeResp(text=sums_text)
        return _FakeResp(content=payload)
    u = Updater(Config(update_mode="notify"), "0.3.0")
    u.http.get = get
    return u


def test_version_compare():
    from simcoach.updater import is_newer
    assert is_newer("0.3.1", "0.3.0") and is_newer("v1.0", "0.9.9") and is_newer("0.10.0", "0.9.0")
    assert not is_newer("0.3.0", "0.3.0") and not is_newer("0.2.9", "0.3.0")
    assert not is_newer("0.3.0", "0.3.0.0")


def test_updater_downloads_and_verifies():
    payload = b"fake installer" * 1000
    rel, sums = _fake_release(payload)
    u = _updater_with(rel, sums, payload)
    st = u.run_once()
    assert st["status"] == "ready" and st["latest"] == "9.9.9" and st["progress"] == 1.0
    from pathlib import Path
    assert Path(st["file"]).read_bytes() == payload
    # not the installed Windows app here -> refuses to self-install, stays ready
    assert u.install(force=True)["status"] == "ready"


def test_updater_rejects_bad_checksum_and_missing_checksum():
    payload = b"real"
    rel, _ = _fake_release(payload, digest=False)
    u = _updater_with(rel, "0" * 64 + "  SimCoach-Setup-9.9.9.exe\n", b"tampered")
    assert u.run_once()["status"] == "error" and "checksum" in u.status()["error"]
    rel2, _ = _fake_release(payload, digest=False, sums=False, tag="v9.9.8")
    u2 = _updater_with(rel2, "", payload)
    assert u2.run_once()["status"] == "error" and "no checksum" in u2.status()["error"]


def test_updater_up_to_date_and_no_release():
    rel, sums = _fake_release(b"x", tag="v0.3.0")
    assert _updater_with(rel, sums, b"x").check()["status"] == "up_to_date"
    assert _updater_with(None, "", b"").check()["status"] == "up_to_date"


def test_updater_refuses_foreign_hosts():
    from simcoach.updater import _allowed
    assert _allowed("https://github.com/o/r/releases/download/v1/a.exe")
    assert _allowed("https://objects.githubusercontent.com/x")
    assert not _allowed("http://github.com/x") and not _allowed("https://evil.com/github.com")
    assert not _allowed("https://github.com.evil.com/x")


def test_update_api_endpoints():
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    payload = b"abc" * 100
    rel, sums = _fake_release(payload)
    u = _updater_with(rel, sums, payload)
    cfg = Config()
    client = TestClient(create_app(LiveEngine(cfg, DemoSource()), cfg, updater=u))
    assert client.get("/api/update").json()["status"] == "idle"
    assert client.post("/api/update/check").json()["status"] == "ready"
    assert client.post("/api/config", json={"update_mode": "off"}).json()["update_mode"] == "off"


def test_updater_falls_back_to_api_asset_url():
    payload = b"setup-bytes" * 50
    rel, sums = _fake_release(payload)
    for a in rel["assets"]:
        a["url"] = "https://api.github.com/repos/o/r/releases/assets/" + a["name"]
    from simcoach.updater import Updater
    calls = []

    def get(url, **kw):
        calls.append(url)
        if url.endswith("/releases/latest"):
            return _FakeResp(json_data=rel)
        if "releases/download" in url:            # web download blocked on this network
            return _FakeResp(status=404)
        assert kw.get("headers", {}).get("Accept") == "application/octet-stream"
        return _FakeResp(text=sums) if url.endswith("SHA256SUMS.txt") else _FakeResp(content=payload)
    u = Updater(Config(update_mode="notify"), "0.3.0")
    u.http.get = get
    assert u.run_once()["status"] == "ready"
    assert any("/releases/assets/" in c for c in calls)


# ---------------------------------------------------------- v5: corner names/numbers
def test_corner_map_names_and_matching():
    from simcoach import corners as cmap
    ref = demo.reference_lap()
    cs = detect_corners(ref)
    track = "Demo Ring - GP"
    cmap.save_map(track, [{"pct": cs[0].pct + 0.01, "number": "1", "name": "Hairpin"},
                          {"pct": cs[2].pct, "number": "4-5", "name": ""},
                          {"pct": cs[3].pct, "number": "", "name": "The Kink"},
                          {"pct": 0.5, "number": "", "name": ""}])          # empty -> dropped
    cmap.apply_names(cs, track)
    assert (cs[0].name, cs[0].title, cs[0].spoken) == ("T1", "T1 · Hairpin", "Hairpin")
    assert cs[1].name == "C2"                                               # unnamed keeps C#
    assert cs[2].spoken == "Turn 4 to 5" and cs[2].title == "T4-5"
    assert cs[3].name == "The Kink"
    # fuzzy track match (Garage 61 vs iRacing spelling)
    assert cmap.find_map("Demo Ring GP")["track"] == track
    assert cmap.find_map("Spa") is None
    # wrap-around: corner just after the line matches an entry just before it
    class C:  # minimal stand-in
        def __init__(self, pct): self.pct, self.index = pct, 0
    cmap.save_map("Wrap Track", [{"pct": 0.995, "number": "1", "name": "Line"}])
    c = cmap.apply_names([C(0.004)], "Wrap Track")[0]
    assert c.name == "T1"


def test_corner_names_flow_into_feedback_and_voice():
    from simcoach import corners as cmap
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    cs = detect_corners(demo.reference_lap())
    cmap.save_map("Demo Ring - GP", [{"pct": cs[2].pct, "number": "3", "name": "Big Stop"}])
    cfg = Config(record_laps=False)
    eng = LiveEngine(cfg, DemoSource())
    client = TestClient(create_app(eng, cfg, demo_mode=True))
    r = client.get("/api/corners", params={"ref": "demo:ref"}).json()
    assert r["map_track"] == "Demo Ring - GP" and r["corners"][2]["title"] == "T3 · Big Stop"
    cmp = client.get("/api/compare", params={"mine": "demo:you", "ref": "demo:ref"}).json()
    assert cmp["comparison"]["corners"][2]["title"] == "T3 · Big Stop"
    # live: events carry the title, voice uses the name
    eng.set_reference(demo.reference_lap())
    _drive(eng, 2.4)
    assert any(e.get("title") == "T3 · Big Stop" for e in eng.events)
    assert any(v["text"].startswith("Big Stop,") for v in eng.coach.voice.log)
    # saving through the API relabels the live reference immediately
    client.post("/api/corners", json={"track": "Demo Ring - GP",
                                      "corners": [{"pct": cs[2].pct, "number": "7", "name": "Renamed"}]})
    assert eng.ref_corners[2].title == "T7 · Renamed"
    assert client.get("/api/corners/export", params={"track": "Demo Ring - GP"}).status_code == 200
    cmap.save_map("Demo Ring - GP", [])                                    # clean up for other tests


# ------------------------------------------------------- v6: teammate lap files (.ibt)
def _make_ibt(path, laps=3, pit_lap=None):
    from simcoach.ibt import write_ibt
    ref = demo.reference_lap()
    dt, L = 1 / 60, demo.TRACK_LENGTH
    t, pct, lapn, spd, pit = [], [], [], [], []
    p, tt, n = 0.9, 100.0, 0
    while n <= laps:
        v = float(np.interp(p, GRID, ref.speed, period=1))
        t.append(tt); pct.append(p); lapn.append(n); spd.append(v); pit.append(n == pit_lap)
        p += v * dt / L; tt += dt
        if p >= 1:
            p -= 1; n += 1
    pct = np.array(pct)
    ch = {"SessionTime": np.array(t), "LapDistPct": pct.astype(np.float32), "Lap": np.array(lapn, dtype=np.int32),
          "Speed": np.array(spd, dtype=np.float32),
          "Throttle": np.interp(pct, GRID, ref.throttle).astype(np.float32),
          "Brake": np.interp(pct, GRID, ref.brake).astype(np.float32),
          "Gear": np.interp(pct, GRID, ref.gear).astype(np.int32),
          "SteeringWheelAngle": np.interp(pct, GRID, ref.steer).astype(np.float32),
          "OnPitRoad": np.array(pit), "IsOnTrack": np.ones(len(t), bool),
          "PlayerTrackSurface": np.full(len(t), 3, np.int32),
          "Lat": np.interp(pct, GRID, ref.lat), "Lon": np.interp(pct, GRID, ref.lon)}
    yml = ("---\nWeekendInfo:\n TrackDisplayName: Demo Ring\n TrackConfigName: GP\n TrackLength: 4.20 km\n"
           "DriverInfo:\n DriverCarIdx: 0\n Drivers:\n - CarIdx: 0\n   UserName: Alex Teammate\n"
           "   CarScreenName: Demo GT3\n...\n")
    write_ibt(path, ch, yml)
    return ref


def test_ibt_reader_extracts_laps(tmp_path):
    from simcoach.ibt import IBTError, extract_laps
    p = tmp_path / "team.ibt"
    ref = _make_ibt(p, laps=3, pit_lap=2)
    info, laps = extract_laps(p)
    assert info["driver"] == "Alex Teammate" and info["track"] == "Demo Ring" and info["track_length"] == 4200
    assert len(laps) == 2                                  # laps 1 and 2 complete (3 has no end crossing)
    assert laps[0].valid and not laps[-1].valid            # pit lap sorted last and flagged
    best = laps[0].lap
    assert abs(best.lap_time - ref.lap_time) < 0.05
    assert float(np.max(np.abs(best.time - ref.time))) < 0.05
    assert best.has_map() and best.meta["track"] == "Demo Ring - GP"
    p.unlink()                                             # memmap released -> deletable (matters on Windows)
    bad = tmp_path / "bad.ibt"
    bad.write_bytes(b"x" * 500)
    with pytest.raises(IBTError):
        extract_laps(bad)


def test_teammate_upload_and_set_reference(tmp_path):
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    p = tmp_path / "team.ibt"
    _make_ibt(p, laps=2)
    cfg = Config(record_laps=False)
    eng = LiveEngine(cfg, DemoSource())
    client = TestClient(create_app(eng, cfg))
    import sys as _sys
    fds = (lambda: len(os.listdir("/proc/self/fd"))) if _sys.platform.startswith("linux") else (lambda: 0)
    before = fds()
    for _ in range(3):
        r = client.post("/api/laps/upload", params={"filename": "team.ibt"}, content=p.read_bytes())
        assert r.status_code == 200, r.text
    assert fds() <= before + 2          # no file handle leaked per upload (locks the file on Windows)
    d = r.json()
    assert d["info"]["driver"] == "Alex Teammate" and len(d["laps"]) >= 1
    r2 = client.post("/api/laps/import", json={"upload_id": d["upload_id"], "index": 0, "driver": "Max",
                                               "set_reference": True}).json()
    assert r2["label"].startswith("Max 1:26") and eng.reference is not None
    assert eng.ref_label.startswith("Max")
    assert any(l["file"] == r2["file"] for l in client.get("/api/local/laps").json())
    # .blap is explained, not guessed
    rb = client.post("/api/laps/upload", params={"filename": "x.blap"}, content=b"\x00" * 100)
    assert rb.status_code == 415 and ".ibt" in rb.json()["detail"]
    # Garage 61 CSV without a time column needs the lap time
    csv = demo.demo_ref_csv().encode()
    assert client.post("/api/laps/upload", params={"filename": "g61.csv"}, content=csv).status_code == 422
    rc = client.post("/api/laps/upload", params={"filename": "g61.csv", "lap_time": 86.38}, content=csv)
    assert rc.status_code == 200 and abs(rc.json()["laps"][0]["lap_time"] - 86.38) < 0.01


def test_exit_demo_and_quit_endpoints():
    from fastapi.testclient import TestClient
    from simcoach.__main__ import relaunch_command
    from simcoach.server import create_app
    calls = []
    cfg = Config()
    demo_app = create_app(LiveEngine(cfg, DemoSource()), cfg, demo_mode=True,
                          on_quit=lambda: calls.append("quit"), on_restart_live=lambda: calls.append("live"))
    c = TestClient(demo_app)
    assert c.post("/api/exit_demo").json()["restarting"] is True
    assert c.post("/api/quit").json()["ok"] and calls == ["live", "quit"]
    live = TestClient(create_app(LiveEngine(cfg, DemoSource()), cfg, demo_mode=False,
                                 on_restart_live=lambda: calls.append("x")))
    assert live.post("/api/exit_demo").json()["demo"] is False and "x" not in calls
    # requests from another machine on the network are refused
    remote = TestClient(demo_app, client=("192.168.1.50", 5000))
    assert remote.post("/api/quit").status_code == 403
    cmd = relaunch_command(8061)
    assert "--takeover" in cmd and "--demo" not in cmd and "8061" in cmd


# ------------------------------------------- v7: optimal lap, line, car control, progress, race
def test_car_control_and_line_detect_planted_mistakes():
    cmp = compare_laps(demo.make_lap(demo.YOU_STYLE, "me"), demo.reference_lap())
    by = {c.name: c for c in cmp.corners}
    assert by["C1"].wheelspin_m_diff >= 20 and "wheelspin" in by["C1"].issues
    assert by["C3"].abs_m_diff >= 10 and "abs_heavy" in by["C3"].issues
    assert by["C7"].oversteer_m >= 15 and "oversteer" in by["C7"].issues
    assert by["C5"].line_apex_m == pytest.approx(2.5, abs=0.5) and "wide_apex" in by["C5"].issues
    assert abs(by["C2"].line_apex_m) < 0.2                      # on the reference line elsewhere
    d = cmp.to_dict()
    assert d["line"] and len(d["line"]) == N_BINS and d["scores"]["car_control"] < 100
    same = compare_laps(demo.reference_lap(), demo.reference_lap())
    assert all(not c.issues for c in same.corners) and same.to_dict()["scores"]["line"] == 100


def test_optimal_lap_stitches_best_segments():
    from simcoach.optimal import build_optimal
    a = demo.make_lap(demo.YOU_STYLE, "A", jitter=1.0, seed=1)
    b = demo.make_lap(demo.YOU_STYLE, "B", jitter=1.0, seed=2)
    ref = demo.reference_lap()
    lap, segs = build_optimal([a, b, ref])
    assert lap.lap_time <= min(a.lap_time, b.lap_time, ref.lap_time) + 1e-6
    assert abs(lap.lap_time - sum(s.duration for s in segs)) < 0.01
    assert np.all(np.diff(lap.time) > 0)                       # monotonic time after stitching
    lap2, _ = build_optimal([a, b])
    assert lap2.lap_time <= min(a.lap_time, b.lap_time) and lap2.meta["source"] == "optimal"
    with pytest.raises(ValueError):
        build_optimal([a])


def test_lift_and_coast_plan_and_race_planner():
    from simcoach.race import RaceTracker, extra_lap_target, lift_plan, plan_race
    lap = demo.reference_lap()
    fpl = float(lap.fuel[0] - lap.fuel[-1])
    small, big = lift_plan(lap, 0.05), lift_plan(lap, 0.2)
    assert small["reached"] and big["reached"] and small["plan"] and big["plan"]
    assert big["total_lost_s"] > small["total_lost_s"] > 0              # more saving costs more
    assert big["cost_per_litre_s"] >= small["cost_per_litre_s"]          # and more per litre
    assert all(p["lift_bin"] < p["brake_bin"] or p["lift_bin"] > 900 for p in big["plan"])
    plan = plan_race(86.4, fpl, 60, race_time_s=3 * 3600, pit_loss_s=60,
                     lift_cost_per_litre=small["cost_per_litre_s"])
    assert sum(plan["stints"]) == plan["total_laps"] and plan["stops"] == len(plan["stints"]) - 1
    assert plan["options"] and plan["options"][0]["save_per_lap"] > 0
    t = extra_lap_target(20.0, fpl)
    assert t["laps_goal"] == int(20 / fpl) + 1 and 20 / t["target_fuel_per_lap"] >= t["laps_goal"] - 1e-6
    rt = RaceTracker()
    for i in range(6):
        rt.add(i + 1, 90 + 0.1 * i, 3.0, True, pit=(i == 3))
    st = rt.status(30.0, 1800.0, -1.0, 60.0, 7)
    assert st["stint"] == 2 and st["fuel_per_lap"] == 3.0 and st["laps_of_fuel"] == 10.0
    assert st["laps_to_go"] == 20 and st["stops_needed"] == 1 and st["pit_window"]["close"] == 17


def test_live_race_fuel_save_and_history(tmp_path):
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    from simcoach import history
    cfg = Config(record_laps=True, voice_native=False)
    eng = LiveEngine(cfg, DemoSource())
    eng.set_reference(demo.reference_lap())
    client = TestClient(create_app(eng, cfg, demo_mode=True))
    _drive(eng, 3.6)
    st = client.get("/api/race").json()
    assert st["fuel_per_lap"] and 2.5 < st["fuel_per_lap"] < 3.5 and st["laps_of_fuel"]
    r = client.post("/api/fuelsave", json={"mode": "target", "save_per_lap": 0.1}).json()
    assert r["active"] and r["plan"]
    lift_bins = {p["lift_bin"] for p in r["plan"]}
    from simcoach.lap import GRID as G
    cue = eng._brake_cue(float(G[min(lift_bins)]) - 0.01)
    assert cue and cue["kind"] == "lift"
    assert client.post("/api/fuelsave", json={"mode": "off"}).json()["active"] is False
    plan = client.post("/api/race/plan", json={"race_minutes": 120, "pit_loss_s": 55}).json()
    assert plan["total_laps"] > 0 and "options" in plan
    # history + progress + practice plan
    assert history.load_sessions("Demo Ring - GP")
    prog = client.get("/api/progress", params={"track": "Demo Ring - GP"}).json()
    assert prog["sessions"] and prog["sessions"][-1]["best"]
    pp = client.get("/api/practice_plan").json()
    assert pp["plan"] and any(p.get("drill") and "drill" in p["title"] for p in pp["plan"])
    assert sum(p["minutes"] for p in pp["plan"]) == 45
    # optimal lap from the recorded laps
    o = client.post("/api/optimal", json={"set_reference": True}).json()
    assert o.get("lap_time") and o["lap_time"] <= o["best_single_lap"] + 1e-6, o
    assert eng.ref_label.startswith("Optimal lap")


def test_practice_plan_fits_session_length():
    from simcoach.history import practice_plan
    rep = {"corners": [{"name": "C1", "title": "T1", "avg_loss": 0.4, "best_loss": 0.1, "spread": 0.2,
                        "main_issue_code": "brake_early", "main_issue": "Braking too early"},
                       {"name": "C2", "title": "T2", "avg_loss": 0.3, "best_loss": 0.1, "spread": 0.05,
                        "main_issue_code": "wide_apex", "main_issue": "Missing the apex"}]}
    for m in (30, 45, 60, 90):
        plan = practice_plan(rep, {"braking": 70, "line": 85}, m)
        assert sum(p["minutes"] for p in plan) == m and all(p["minutes"] >= 3 for p in plan)
    assert any("Racing line" in p["title"] or "Braking" in p["title"] for p in practice_plan(rep, {"braking": 70}, 45))


def test_gps_precision_survives_save_and_json(tmp_path):
    ref = demo.reference_lap()
    p = tmp_path / "gps.csv"
    ref.save(p)
    back = Lap.load(p)
    # metres of error after a save/load round trip (1e-5 deg ~ 1.1 m would break line analysis)
    err_m = float(np.max(np.abs(back.lat - ref.lat))) * 110540
    assert err_m < 0.05
    j = ref.to_json()
    assert float(np.max(np.abs(np.array(j["lat"]) - ref.lat))) * 110540 < 0.01
    cmp = compare_laps(Lap.load(p), ref)
    assert max(abs(c.line_apex_m) for c in cmp.corners) < 0.2   # same lap -> on the line everywhere


# ------------------------------------------------- v8: planner from Garage 61 / live / exports
def test_g61_fuel_and_pace_stats():
    from simcoach.race import pace_stats
    assert describe_lap({"lapTime": 219.0, "fuelUsed": 7.02})["fuel_used"] == 7.02
    assert describe_lap({"lapTime": 219.0, "fuel": {"used": 6.9}})["fuel_used"] == 6.9
    assert describe_lap({"lapTime": 219.0})["fuel_used"] is None
    st = pace_stats([{"lap_time": 218.6, "fuel_used": 7.0}, {"lap_time": 219.3, "fuel_used": 7.06},
                     {"lap_time": 246.3, "fuel_used": 6.8},            # traffic/incident lap: excluded
                     {"lap_time": 219.0, "fuel_used": None, "clean": True},
                     {"lap_time": 210.0, "fuel_used": 9.0, "clean": False}])   # unclean: excluded
    assert st["lap_time"] == 219.0 and st["best"] == 218.6 and st["laps"] == 3
    assert st["fuel_per_lap"] == pytest.approx(7.03) and st["fuel_laps"] == 2


def test_plan_from_now_uses_fuel_in_tank():
    from simcoach.race import plan_race
    full = plan_race(220, 7.0, 75, race_time_s=3 * 3600)
    now = plan_race(220, 7.0, 75, race_time_s=3 * 3600, fuel_now=40)
    assert sum(now["stints"]) == now["total_laps"] == full["total_laps"] == 50
    assert now["stints"][0] == 5 and all(n <= 10 for n in now["stints"][1:])
    assert now["stops"] == len(now["stints"]) - 1 and now["fuel_margin"] >= 0
    opt = next(o for o in now["options"] if o["saves_stop"])
    # with the saving, fuel now + one stop fewer of full tanks covers the race
    assert 40 + (now["stops"] - 1) * 75 >= opt["target_fuel_per_lap"] * now["total_laps"] - 1e-6


def test_race_sources_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from simcoach import garage61, sessions
    from simcoach.server import create_app
    sessions.import_file(SAMPLE)                      # Le Mans export with fuel used per lap
    calls = {}

    def fake_find(self, **kw):
        calls.update(kw)
        return [{"lapTime": 219.0 + i * 0.1, "fuelUsed": 7.0 + i * 0.01, "driver": {"firstName": "Devon"}}
                for i in range(8)]
    monkeypatch.setattr(garage61.Garage61Client, "find_laps", fake_find)
    cfg = Config(garage61_token="x")
    eng = LiveEngine(cfg, DemoSource())
    client = TestClient(create_app(eng, cfg))
    r = client.get("/api/race/sources", params={"car": 1, "track": 2, "scope": "me"}).json()
    g = r["garage61"]
    assert g["laps"] == 8 and g["lap_time"] == pytest.approx(219.35) and g["fuel_per_lap"] == pytest.approx(7.035)
    assert calls["drivers"] == ["me"] and calls["cars"] == [1] and calls["group"] == "none"
    e = r["export"]
    assert e and e["car"] == "Dallara P217" and 218 < e["lap_time"] < 221 and 6.5 < e["fuel_per_lap"] < 7.5
    plan = client.post("/api/race/plan", json={"race_minutes": 360, "avg_lap": g["lap_time"],
                                               "fuel_per_lap": g["fuel_per_lap"], "tank": 75,
                                               "fuel_now": 30}).json()
    assert plan["from_now"] and plan["stints"][0] == 4 and sum(plan["stints"]) == plan["total_laps"]


# ------------------------------------------------------------- v9: tablet / phone (LAN + QR)
def test_lan_guard_qr_and_status():
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    cfg = Config()
    eng = LiveEngine(cfg, DemoSource())
    app = create_app(eng, cfg, demo_mode=True, bind_host="0.0.0.0", port=8061)
    local, tablet = TestClient(app), TestClient(app, client=("192.168.1.50", 5000))
    # the tablet can use the coaching screens...
    assert tablet.get("/").status_code == 200 and tablet.get("/api/status").status_code == 200
    assert tablet.post("/api/coach/focus", json={"action": "auto"}).status_code == 200
    # ...but not change settings, quit, restart or delete
    assert tablet.post("/api/config", json={"units": "imperial"}).status_code == 403
    assert tablet.post("/api/quit").status_code == 403 and tablet.post("/api/restart").status_code == 403
    assert tablet.delete("/api/local/laps/x.csv").status_code == 403
    assert local.post("/api/config", json={"units": "metric"}).status_code == 200
    st = tablet.get("/api/lan").json()
    assert st["active"] and st["viewer_is_remote"] and st["port"] == 8061
    # toggling the setting on a localhost-only server asks for a restart
    app2 = create_app(eng, cfg, bind_host="127.0.0.1")
    c2 = TestClient(app2)
    assert c2.post("/api/config", json={"lan_access": True}).json()["lan_access"] is True
    s2 = c2.get("/api/lan").json()
    assert s2["enabled"] and not s2["active"] and s2["needs_restart"]
    cfg.lan_access = False
    svg = local.get("/api/lan/qr.svg", params={"url": "http://192.168.1.20:8061/"})
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg") and "<svg" in svg.text
    assert local.get("/api/lan/qr.svg", params={"url": "javascript:alert(1)"}).status_code == 400


# --------------------------------------------- v10: vocal coach, drills from plan, session report
def test_vocal_coach_calls_braking_turn_in_and_trail():
    cfg = Config(record_laps=False, voice_mode="full")
    eng = LiveEngine(cfg, DemoSource())
    eng.set_reference(demo.reference_lap())
    _drive(eng, 2.6)
    kinds = {e["kind"] for e in eng.events}
    assert {"brake", "turn_in", "trail", "brake_pressure"} <= kinds
    trail_c3 = [e for e in eng.events if e["corner"] == "C3" and e["kind"] == "trail"]
    assert trail_c3 and trail_c3[-1]["severity"] == "bad"                 # planted: off the brake early
    spoken = [v["text"] for v in eng.coach.voice.log] + [e["text"] for e in eng.events]
    said = " | ".join(v["text"] for v in eng.coach.voice.log)
    assert "Brake later" in said or "Trail the brake deeper" in said or "Turn in earlier" in said, said
    assert spoken
    # quiet mode doesn't call phases
    eng2 = LiveEngine(Config(record_laps=False, voice_mode="cues"), DemoSource())
    eng2.set_reference(demo.reference_lap())
    _drive(eng2, 1.4)
    assert not any(t in v["text"] for v in eng2.coach.voice.log for t in ("Brake later", "Trail the brake", "Turn in"))


def test_voice_setting_migrates_to_full(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setenv("SIMCOACH_HOME", str(tmp_path))
    (tmp_path / "config.json").write_text(_json.dumps({"voice_mode": "cues"}))
    assert Config.load().voice_mode == "full"
    (tmp_path / "config.json").write_text(_json.dumps({"voice_mode": "off"}))
    assert Config.load().voice_mode == "off"                               # an explicit "off" is respected
    (tmp_path / "config.json").write_text(_json.dumps({"voice_mode": "cues", "voice_v2": True}))
    assert Config.load().voice_mode == "cues"                              # chosen after the change: kept


def test_plan_starts_drills_and_ticks_off(tmp_path):
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    cfg = Config(record_laps=False, voice_native=False)
    eng = LiveEngine(cfg, DemoSource())
    eng.set_reference(demo.reference_lap())
    client = TestClient(create_app(eng, cfg, demo_mode=True))
    _drive(eng, 3.6)
    plan = client.get("/api/practice_plan", params={"minutes": 45}).json()["plan"]
    drills_ = [i for i, p in enumerate(plan) if p.get("drill")]
    assert drills_ and all(p["status"] == "pending" for p in plan)
    i = drills_[0]
    r = client.post(f"/api/plan/{i}/start").json()
    assert r["plan"][i]["status"] == "active" and r["focus"]["active"]
    assert r["focus"]["corner"] == plan[i]["drill"]["corner"] and r["focus"]["kind"] == plan[i]["drill"]["kind"]
    # completing the drill ticks the step off
    eng.coach._plan_step_done(plan[i]["drill"]["corner"], plan[i]["drill"]["kind"])
    assert client.get("/api/plan").json()["plan"][i]["status"] == "done"
    assert client.post("/api/plan/99/start").status_code == 404
    # printable report
    assert client.get("/report").status_code == 200
    rep = client.get("/api/report").json()
    assert rep["report"]["laps"] >= 2 and rep["top"] and rep["plan"] and rep["grades"]
    t = rep["top"][0]
    assert t["trace"] and len(t["trace"]["me_speed"]) == len(t["trace"]["ref_speed"]) > 20
    assert t["last_lap"]["tips"]


# ------------------------------------------------- v11: consistency trainer, feature switches
def test_consistency_trainer_window_streak_and_why():
    from simcoach.consistency import ConsistencyTrainer
    ct = ConsistencyTrainer()
    ct.start(None, 0.3, 4)
    def corners(c3_loss, bp=-5.0):
        return [{"name": "C1", "time_lost": 0.1, "brake_point_m": 0.0},
                {"name": "C3", "title": "T3", "spoken": "T3", "time_lost": c3_loss, "brake_point_m": bp}]
    for t in (90.0, 90.2, 90.1):                       # 3 laps set the target from your pace
        ct.add_lap(t, True, corners(0.2))
    assert ct.target == pytest.approx(90.1)
    r = ct.add_lap(90.3, True, corners(0.2))
    assert r["inside"] and ct.streak == 1
    r = ct.add_lap(90.9, True, corners(0.75, bp=-18.0))  # out: T3 cost 0.55s, braked 13 m earlier
    assert not r["inside"] and ct.streak == 0
    assert r["why"]["corner"] == "T3" and r["why"]["cost"] == pytest.approx(0.55)
    assert "braked 13 m earlier" in r["why"]["habit"]
    assert "Outside" in ct.spoken(r) and "T3" in ct.spoken(r)
    for t in (90.05, 90.15, 90.0, 90.2):
        r = ct.add_lap(t, True, corners(0.2))
    assert r["completed"] and ct.best_streak == 4 and ct.status()["score"] > 50
    assert ct.add_lap(80.0, False, None) is None        # invalid laps don't count


def test_feature_switches_hide_and_block():
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    cfg = Config(record_laps=False, voice_native=False)
    eng = LiveEngine(cfg, DemoSource())
    eng.set_reference(demo.reference_lap())
    client = TestClient(create_app(eng, cfg, demo_mode=True))
    f = client.get("/api/features").json()
    assert set(f["features"]) >= {"drills", "consistency", "endurance", "practice", "live_feedback", "brake_cue"}
    client.post("/api/config", json={"features": {"consistency": False, "endurance": False, "drills": False,
                                                  "live_feedback": False, "brake_cue": False}})
    assert client.post("/api/consistency/start", json={}).status_code == 409
    assert client.post("/api/fuelsave", json={"mode": "extra_lap"}).status_code == 409
    assert client.post("/api/coach/focus", json={"action": "auto"}).status_code == 409
    assert client.post("/api/fuelsave", json={"mode": "off"}).status_code == 200      # turning off always works
    _drive(eng, 1.6)
    assert not eng.events                                   # no live corner feedback
    ov = eng.overlay()
    assert ov["brake_cue"] is None and ov["fuel"] is None and ov["consistency"] is None
    client.post("/api/config", json={"features": {"consistency": True, "live_feedback": True}})
    assert client.post("/api/consistency/start", json={"window": 0.5, "goal": 5}).json()["active"]
    _drive(eng, 1.2)
    assert eng.events and eng.overlay()["consistency"]["goal"] == 5


# ------------------------------------------------------------- v12: weekly goal & streak
def test_weekly_goal_streak():
    from datetime import date
    from simcoach.goals import weekly_summary
    S = lambda d, m, laps=10: {"id": d + "_120000_x", "date": d + "_120000", "drive_s": m * 60,  # noqa: E731
                               "laps": [], "lap_count": laps}
    ss = [S("20261005", 30), S("20261012", 200), S("20261020", 100), S("20261021", 90), S("20261027", 181),
          S("20261103", 60)]
    g = weekly_summary(ss, "minutes", 180, today=date(2026, 11, 3))
    assert g["streak"] == 3 and g["best_streak"] == 3 and not g["met"]        # this week unfinished: no break
    assert g["this_week"] == 60 and g["remaining"] == 120 and g["days_left"] == 5 and len(g["weeks"]) == 8
    g2 = weekly_summary(ss, "minutes", 180, today=date(2026, 11, 3), live={"minutes": 130})
    assert g2["met"] and g2["streak"] == 4                                    # live session completes the week
    g3 = weekly_summary(ss, "sessions", 2, today=date(2026, 11, 3))
    assert g3["weeks"][-2]["sessions"] == 1 and g3["streak"] == 0              # only W43 had 2 sessions
    assert weekly_summary(ss, "laps", 20, today=date(2026, 11, 3))["best_streak"] == 1
    assert weekly_summary([], "minutes", 180, today=date(2026, 11, 3))["streak"] == 0


def test_weekly_goal_live_and_api():
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    cfg = Config(record_laps=False, voice_native=False, goal_type="minutes", goal_value=2)
    eng = LiveEngine(cfg, DemoSource())
    eng.set_reference(demo.reference_lap())
    client = TestClient(create_app(eng, cfg, demo_mode=True))
    _drive(eng, 2.2)
    assert eng.drive_s > 150                                                  # time on track is counted
    g = client.get("/api/goals").json()
    assert g["met"] and g["this_week"] >= 2
    assert any("Weekly goal reached" in v["text"] for v in eng.coach.voice.log)
    assert client.post("/api/config", json={"goal_type": "laps", "goal_value": 50}).json()["goal_type"] == "laps"
    client.post("/api/config", json={"features": {"goals": False}})
    assert client.get("/api/goals").status_code == 409


# ------------------------------------------------- v12: training game, phone training hub, widgets
def test_training_game_xp_combo_daily_badges(tmp_path):
    import datetime as dt
    from simcoach.game import XP, TrainingGame, combo_mult, daily_for, level_for
    day = dt.date(2026, 11, 4)
    assert level_for(0)["level"] == 1 and level_for(100)["level"] == 2 and level_for(274)["level"] == 2
    assert level_for(275)["level"] == 3
    assert [combo_mult(n) for n in (0, 2, 3, 6, 10)] == [1, 1, 2, 3, 4]
    g = TrainingGame(path=tmp_path / "game.json", today=lambda: day)
    said = []
    g.say = said.append
    g.on("clean_lap")
    assert g.xp == XP["clean_lap"] and g.status()["badges"][0]["earned"]
    for _ in range(3):                                    # combo: x2 on the third hit
        g.on("drill_attempt", ok=True, corner="T1")
    assert g.combo == 3 and g.xp == XP["clean_lap"] + XP["drill_hit"] * (1 + 1 + 2)
    g.on("drill_attempt", ok=False)
    assert g.combo == 0 and g.best_combo == 3
    g.on("drill_done", corner="T1", kind="brake_ladder")
    assert {"first_drill", "ladder"} <= set(g.badges)
    g.on("plan_step", title="Warm-up", all_done=False)
    g.on("plan_step", title="Push laps", all_done=True)
    assert "plan" in g.badges and any("Level up" in s for s in said)
    # weekly goal XP only once per ISO week
    xp = g.xp
    g.on("weekly_goal"); g.on("weekly_goal")
    assert g.xp == xp + XP["weekly_goal"]
    # daily challenge
    d = daily_for(day)
    before = g.xp
    for _ in range(d["goal"]):
        if d["event"] == "combo":
            g.on("drill_attempt", ok=True)
        elif d["event"] in ("cons_lap",):
            g.on("cons_lap", inside=True, streak=1)
        elif d["event"] == "fuel_lap":
            g.on("fuel_lap", ok=True)
        elif d["event"] == "drill_hit":
            g.on("drill_attempt", ok=True)
        else:
            g.on(d["event"])
    st = g.status()
    assert st["daily"]["done"] and g.xp - before >= XP["daily"]
    # feed is bounded, state persists
    for _ in range(100):
        g.on("cons_lap", inside=False)
    assert len(g.feed) <= 25 and g.combo == 0
    g.save()
    g2 = TrainingGame(path=tmp_path / "game.json", today=lambda: day)
    assert g2.xp == g.xp and g2.badges == g.badges and g2.daily_done and g2.combo == 0
    assert g2.overlay()["level"] == level_for(g.xp)["level"]


def test_training_hub_select_from_phone_and_widgets():
    from fastapi.testclient import TestClient
    from simcoach.server import create_app
    cfg = Config(record_laps=False, voice_native=False)
    eng = LiveEngine(cfg, DemoSource())
    eng.set_reference(demo.reference_lap())
    app = create_app(eng, cfg, demo_mode=True, bind_host="0.0.0.0", port=8061)
    phone = TestClient(app, client=("192.168.1.50", 5000))
    xp0 = eng.game.xp
    _drive(eng, 3.6)
    assert eng.game.xp > xp0                                           # clean laps earn XP
    st = phone.get("/api/training").json()
    assert st["mode"] == "free" and st["corners"] and st["game"]["level"] >= 1 and "game" in st["feature_labels"]
    # pages
    for path in ("/train", "/widget/plan", "/widget/consistency", "/widget/endurance", "/widget/fuel"):
        assert phone.get(path).status_code == 200
    assert phone.get("/widget/nope").status_code == 404
    # drill from the phone
    st = phone.post("/api/training/select", json={"mode": "drill", "corner": 1, "kind": "min_speed"}).json()
    assert st["mode"] == "drill" and st["focus"]["corner"] == 1 and st["focus"]["kind"] == "min_speed"
    # consistency replaces the drill
    st = phone.post("/api/training/select", json={"mode": "consistency", "window": 0.2, "goal": 10}).json()
    assert st["mode"] == "consistency" and not st["focus"]["active"] and st["consistency"]["goal"] == 10
    # plan: builds one and starts the first open quest
    st = phone.post("/api/training/select", json={"mode": "plan", "minutes": 45}).json()
    assert st["mode"] == "plan" and st["plan"][0]["status"] == "active" and not st["consistency"]["active"]
    # fuel saving (demo has fuel) then back to free driving
    r = phone.post("/api/training/select", json={"mode": "fuel", "fuel_mode": "target", "save_per_lap": 0.1})
    assert r.status_code == 200 and r.json()["mode"] == "fuel" and r.json()["fuel_target"]
    assert not any(p["status"] == "active" for p in r.json()["plan"])
    w = phone.get("/api/widget").json()
    assert w["race"] is not None and w["fuel_save"]
    assert phone.post("/api/training/select", json={"mode": "free"}).json()["mode"] == "free"
    assert eng.fuel_save is None
    assert phone.post("/api/training/select", json={"mode": "nope"}).status_code == 422
    # training features can be switched from the phone - other settings stay local-only
    r = phone.post("/api/features", json={"features": {"consistency": False, "garage61_token": "x"}})
    assert r.status_code == 200 and r.json()["features"]["consistency"] is False
    assert "garage61_token" not in r.json()["features"]
    assert phone.post("/api/training/select", json={"mode": "consistency"}).status_code == 409
    assert phone.post("/api/config", json={"units": "imperial"}).status_code == 403
    phone.post("/api/features", json={"features": {"consistency": True, "game": False}})
    assert phone.get("/api/game").status_code == 409 and eng.overlay()["game"] is None
    phone.post("/api/features", json={"features": {"game": True}})
    assert eng.overlay()["game"]["level"] >= 1


# ------------------------------------------------- v12: racing line without live GPS
def test_racing_line_rebuilt_from_heading_and_speed():
    """iRacing has no Lat/Lon live - the line is rebuilt from heading, speed and slip angle."""
    from simcoach.control import _xy, aligned_latlon, line_offset
    from simcoach.live import LapBuffer
    ref = demo.reference_lap()
    bump = lambda g: 3.0 * np.exp(-((g - 0.3) / 0.015) ** 2)   # noqa: E731 - 3 m wide at 30 % of the lap
    # slip angle: heading points inside the corner; velocity vector carries the slip
    def drive_slip(ref, offset_fn, slip_sign):
        rx, ry = _xy(ref.lat, ref.lon, ref.lat.mean(), ref.lon.mean())
        tx, ty = np.gradient(np.r_[rx[-1], rx, rx[0]])[1:-1], np.gradient(np.r_[ry[-1], ry, ry[0]])[1:-1]
        n = np.hypot(tx, ty); nx, ny = -ty / n, tx / n
        off = offset_fn(GRID); mx, my = rx + nx * off, ry + ny * off
        pts = 20 * N_BINS
        pp = np.linspace(0, 1, pts, endpoint=False)
        X = np.r_[np.interp(pp, GRID, mx, period=1), mx[0]]; Y = np.r_[np.interp(pp, GRID, my, period=1), my[0]]
        pp = np.r_[pp, 1.0]
        ds = np.hypot(np.diff(X), np.diff(Y)); v = np.interp(pp[:-1], GRID, ref.speed, period=1)
        travel = np.unwrap(np.arctan2(np.diff(Y), np.diff(X)))
        curv = np.gradient(travel) / np.maximum(ds, 1e-6)
        beta = np.clip(0.9 * curv * 25, -0.08, 0.08)          # up to ~4.5 deg, nose pointing inside
        heading = travel + beta
        vxs, vys = v * np.cos(beta), slip_sign * -v * np.sin(beta)
        steer = np.interp(pp[:-1], GRID, ref.steer, period=1)
        buf = LapBuffer(0.0); t = 0.0
        for i in range(len(ds)):
            buf.add({"pct": pp[i], "speed": v[i], "throttle": 0, "brake": 0, "gear": 3, "steer": steer[i],
                     "session_time": t, "on_pit_road": False, "surface": 3, "heading": heading[i] + 0.4,
                     "vx": vxs[i], "vy": vys[i]})
            t += ds[i] / v[i]
        lap = buf.to_lap(ref.track_length); lap.meta = {"line": "reconstructed"}
        return lap, off, beta

    for sign in (1, -1):                                       # slip sign convention doesn't matter
        lap, off, beta = drive_slip(ref, bump, sign)
        assert lap.has_map() and lap.meta["line"] == "reconstructed"
        lo = line_offset(lap, ref)
        err = lo["offset"] - off
        assert abs(lo["offset"][300] - 3.0) < 0.5 and float(np.sqrt(np.mean(err ** 2))) < 0.4
    ll = aligned_latlon(lap, ref)                              # drawn in the reference's frame
    assert ll is not None and abs(float(np.mean(ll[0])) - float(np.mean(ref.lat))) < 1e-4
    # a buffer without heading (old data) still has no line
    buf = LapBuffer(0.0)
    for i in range(2001):
        buf.add({"pct": i / 2001, "speed": 50, "throttle": 1, "brake": 0, "gear": 4, "steer": 0,
                 "session_time": i * 0.04, "on_pit_road": False, "surface": 3})
    assert not buf.to_lap(4200).has_map()
