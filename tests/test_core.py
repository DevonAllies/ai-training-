import os
import tempfile

os.environ.setdefault("SIMCOACH_HOME", tempfile.mkdtemp(prefix="simcoach_test_"))

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
