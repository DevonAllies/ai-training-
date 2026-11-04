"""Tests for DataLab Trainer.

The most important test runs every exercise's *solution* through the real
checker (SQL, Python, and R when Rscript is installed) and asserts it passes,
and runs every *starter* and asserts it does not pass yet.

Run from the datalab_trainer folder:   python -m pytest -q tests
"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from datalab import runner
from datalab.curriculum import Curriculum
from datalab.server import App, serve
from datalab.store import Store

CUR = Curriculum()
HAVE_R = runner.find_rscript() is not None


def _have(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


@pytest.fixture(scope="session")
def store(tmp_path_factory) -> Store:
    return Store(tmp_path_factory.mktemp("datalab-home"))


def _run(ex, code, ws):
    if ex.lang == "sql":
        return runner.run_sql(code, ws, solution=ex.solution, ordered=ex.ordered)
    if ex.lang == "python":
        return runner.run_python(code, ws, check=ex.check, timeout=300, label=ex.id)
    return runner.run_r(code, ws, check=ex.check, timeout=300, label=ex.id)


def _skip_reason(ex) -> str | None:
    if ex.lang == "r" and not HAVE_R:
        return "Rscript not installed"
    for need in ex.needs:
        if ex.lang == "python" and not _have(need):
            return f"python package {need} not installed"
    return None


def test_curriculum_shape():
    assert [s.id for s in CUR.stages] == ["basics", "import", "clean", "eda", "visualise", "stats", "model",
                                         "forecast", "explain", "report"]
    ids = [e.id for e in CUR.exercises]
    assert len(ids) == len(set(ids)), "duplicate exercise ids"
    for s in CUR.stages:
        assert s.lesson.strip() and len(s.quiz) >= 3
        for q in s.quiz:
            assert 0 <= q.answer < len(q.options), f"quiz answer missing in {s.id}: {q.text}"
        langs = {e.lang for e in CUR.exercises if e.stage == s.id}
        assert langs == {"sql", "python", "r"}, f"stage {s.id} should have SQL, Python and R exercises"
    for e in CUR.exercises:
        assert e.task.strip() and e.solution.strip() and e.starter.strip(), e.id
        if e.lang != "sql":
            assert e.check.strip(), f"{e.id} needs a check"


@pytest.mark.parametrize("ex", CUR.exercises, ids=lambda e: e.id)
def test_solution_passes(ex, store):
    reason = _skip_reason(ex)
    if reason:
        pytest.skip(reason)
    res = _run(ex, ex.solution, store.workspace)
    assert res.check and res.check["passed"], f"{ex.id}: {res.check}\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout[-2000:]}"


@pytest.mark.parametrize("ex", CUR.exercises, ids=lambda e: e.id)
def test_starter_does_not_pass(ex, store):
    reason = _skip_reason(ex)
    if reason:
        pytest.skip(reason)
    res = _run(ex, ex.starter, store.workspace)
    assert not (res.check and res.check["passed"]), f"{ex.id}: the starter code already passes"


def test_sql_compare_tolerates_order_and_rounding():
    ok, _ = runner.compare_tables(["a", "b"], [(1, 2.00001), (2, 3.0)], ["a", "b"], [(2, 3.0), (1, 2.0)], ordered=False)
    assert ok
    ok, msg = runner.compare_tables(["a"], [(1,), (2,)], ["a"], [(2,), (1,)], ordered=True)
    assert not ok and "row 1" in msg


def test_python_error_and_figures(store):
    res = runner.run_python("import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])\nplt.show()\nprint('hi')\n",
                            store.workspace)
    assert res.ok and "hi" in res.stdout and len(res.images) == 1
    assert (store.workspace / "figures" / res.images[0]).exists()
    res = runner.run_python("x = 1\nraise ValueError('boom')\n", store.workspace)
    assert not res.ok and "boom" in res.stderr and "your_code.py" in res.stderr


def test_python_timeout(store):
    res = runner.run_python("while True: pass\n", store.workspace, timeout=3)
    assert not res.ok and "longer than 3 seconds" in res.stderr


@pytest.mark.skipif(not HAVE_R, reason="Rscript not installed")
def test_r_plot_and_error(store):
    res = runner.run_r("x <- 1:10\nplot(x)\nprint(sum(x))\n", store.workspace)
    assert res.ok and "55" in res.stdout and len(res.images) == 1
    res = runner.run_r("stop('boom')\n", store.workspace)
    assert not res.ok and "boom" in res.stderr


def test_store_roundtrip(tmp_path):
    s = Store(tmp_path)
    s.record_attempt("import-sql-1", "SELECT 1", passed=True)
    s2 = Store(tmp_path)
    assert s2.exercise("import-sql-1")["passed"] is True
    assert (tmp_path / "workspace" / "data" / "customers.csv").exists()


def test_http_api(tmp_path):
    app = App(Store(tmp_path), CUR)
    httpd = serve(app, "127.0.0.1", 0)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"

    def get(path):
        try:
            with urllib.request.urlopen(base + path) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    def post(path, body, header=True):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **({"X-DataLab": "1"} if header else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    try:
        st, body = get("/")
        assert st == 200 and b"DataLab" in body
        st, body = get("/static/app.js")
        assert st == 200
        ov = json.loads(get("/api/overview")[1])
        assert len(ov["stages"]) == 10 and ov["exercises"]
        ex = json.loads(get("/api/exercise/import-sql-1")[1])
        assert "solution" not in ex and ex["starter"]
        assert post("/api/run", {"exercise": "import-sql-1", "code": "SELECT 1", "check": True}, header=False)[0] == 403
        st, res = post("/api/run", {"exercise": "import-sql-1", "code": CUR.by_id["import-sql-1"].solution, "check": True})
        assert st == 200 and res["check"]["passed"]
        ov = json.loads(get("/api/overview")[1])
        assert next(e for e in ov["exercises"] if e["id"] == "import-sql-1")["passed"]
        st, q = post("/api/quiz/import", {"answers": [1, 2, 1, 2]})
        assert st == 200 and q["score"] == 4
        st, ds = get("/api/dataset/customers_raw.csv")
        assert st == 200 and json.loads(ds)["rows"] == 618
        st, _ = get("/static/..%2Fserver.py")
        assert st == 404
        st, saved = post("/api/report/export", {"filename": "t", "html": "<h1>x</h1>", "markdown": "# x"})
        assert st == 200 and Path(saved["saved"]["html"]).exists()
    finally:
        httpd.shutdown()
        httpd.server_close()
