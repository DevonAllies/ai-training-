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
        {"name": "C2", "time_lost": 0.2, "issues": ["late_throttle"]}]}
    c.add_lap(1, 90.0, True, comp)
    c.start_focus(None)
    assert c.focus.name == "C1"
    for _ in range(3):
        c.on_corner(0, {"name": "C1", "time_lost": 0.01, "issues": []})
    assert "C1" in c.focus.completed and c.focus.name == "C2"


def test_no_memory_growth_over_long_session():
    """Simulate a long stint; memory after warm-up must stay flat."""
    import gc
    import tracemalloc
    eng = LiveEngine(Config(record_laps=False, voice_native=False), DemoSource())
    eng.coach.voice.native = False
    eng.set_reference(demo.reference_lap())
    eng.coach.start_focus(None)
    src = eng.source
    eng.session = src.session()
    per_lap = int(60 * 90)

    def run(laps):
        for _ in range(per_lap * laps):
            src._last -= 1 / 60
            eng._process(src.read())
            eng.snapshot() if _ % 3 == 0 else None
            eng.overlay() if _ % 3 == 0 else None

    run(4)                                  # warm-up: caches, first laps, numpy pools
    gc.collect()
    tracemalloc.start()
    base = tracemalloc.take_snapshot()
    run(10)
    gc.collect()
    after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    growth = sum(s.size_diff for s in after.compare_to(base, "filename"))
    # 10 more laps of history (bounded deques) may add a little - but not per-sample growth
    assert growth < 400_000, f"memory grew by {growth} bytes over 10 laps"
    assert len(eng.events) <= 30 and len(eng.coach.history) <= 100


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
