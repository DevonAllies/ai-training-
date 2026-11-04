"""Local web server for DataLab Trainer (standard library only).

Binds to 127.0.0.1 so nothing outside your computer can reach it. Because the
API runs code, every POST must carry the ``X-DataLab: 1`` header, which a
browser will not send from another website without a CORS pre-flight that this
server never approves.
"""
from __future__ import annotations

import json
import mimetypes
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import __version__, runner
from .curriculum import Curriculum
from .store import Store, prepare_workspace

STATIC = Path(__file__).resolve().parent / "static"
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


class App:
    def __init__(self, store: Store, curriculum: Curriculum | None = None):
        self.store = store
        self.cur = curriculum or Curriculum()
        self._env_cache: dict | None = None
        self._env_lock = threading.Lock()

    @property
    def ws(self) -> Path:
        return self.store.workspace

    def settings(self) -> dict:
        return self.store.get("settings")

    # ---------------------------------------------------------------- API handlers
    def overview(self) -> dict:
        prog = self.store.get("exercises")
        return {
            "version": __version__,
            "workspace": str(self.ws),
            "stages": [{"id": s.id, "order": s.order, "title": s.title, "summary": s.summary,
                        "quiz_size": len(s.quiz)} for s in self.cur.stages],
            "exercises": [dict(e.summary(), passed=bool(prog.get(e.id, {}).get("passed")),
                               attempts=prog.get(e.id, {}).get("attempts", 0),
                               revealed=bool(prog.get(e.id, {}).get("revealed")))
                          for e in self.cur.exercises],
            "quiz": self.store.get("quiz"),
        }

    def stage(self, sid: str) -> dict | None:
        s = self.cur.stage(sid)
        if not s:
            return None
        return {"id": s.id, "title": s.title, "summary": s.summary, "lesson": s.lesson,
                "quiz": [{"text": q.text, "options": q.options} for q in s.quiz]}

    def grade_quiz(self, sid: str, answers: list) -> dict | None:
        s = self.cur.stage(sid)
        if not s:
            return None
        results = []
        score = 0
        for i, q in enumerate(s.quiz):
            a = answers[i] if i < len(answers) else None
            ok = a == q.answer
            score += ok
            results.append({"correct": ok, "answer": q.answer, "explain": q.explain})
        quiz = self.store.get("quiz")
        best = max(score, quiz.get(sid, {}).get("best", 0))
        quiz[sid] = {"last": score, "best": best, "total": len(s.quiz), "at": time.time()}
        self.store.put("quiz", quiz)
        return {"score": score, "total": len(s.quiz), "results": results}

    def exercise(self, ex_id: str) -> dict | None:
        e = self.cur.by_id.get(ex_id)
        if not e:
            return None
        rec = self.store.exercise(ex_id)
        d = e.public()
        d["saved_code"] = rec.get("code")
        d["passed"] = bool(rec.get("passed"))
        same = [x for x in self.cur.exercises]
        idx = same.index(e)
        d["prev"] = same[idx - 1].id if idx > 0 else None
        d["next"] = same[idx + 1].id if idx + 1 < len(same) else None
        return d

    def run(self, body: dict) -> dict:
        lang = body.get("lang")
        code = body.get("code", "")
        ex_id = body.get("exercise")
        do_check = bool(body.get("check"))
        s = self.settings()
        timeout = int(s.get("timeout") or 120)
        ex = self.cur.by_id.get(ex_id) if ex_id else None
        if ex:
            lang = ex.lang
        label = ex_id or f"playground-{lang}"
        if lang == "sql":
            res = runner.run_sql(code, self.ws, solution=ex.solution if (ex and do_check) else None,
                                 ordered=bool(ex and ex.ordered))
        elif lang == "python":
            res = runner.run_python(code, self.ws, check=ex.check if (ex and do_check) else None,
                                    python=s.get("python_path") or None, timeout=timeout, label=label)
        elif lang == "r":
            res = runner.run_r(code, self.ws, check=ex.check if (ex and do_check) else None,
                               rscript=s.get("rscript_path") or None, timeout=timeout, label=label)
        else:
            return {"ok": False, "stderr": f"Unknown language {lang!r}"}
        if ex:
            if do_check:
                self.store.record_attempt(ex.id, code, bool(res.check and res.check["passed"]))
            else:
                self.store.save_code(ex.id, code)
        elif body.get("playground_key"):
            pg = self.store.get("playground")
            pg[str(body["playground_key"])] = code
            self.store.put("playground", pg)
        return res.to_dict()

    def solution(self, ex_id: str) -> dict | None:
        e = self.cur.by_id.get(ex_id)
        if not e:
            return None
        self.store.mark_revealed(ex_id)
        return {"solution": e.solution}

    def environment(self, refresh: bool = False) -> dict:
        with self._env_lock:
            if self._env_cache is None or refresh:
                s = self.settings()
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(2) as pool:
                    fpy = pool.submit(runner.python_env, s.get("python_path") or None)
                    fr = pool.submit(runner.r_env, s.get("rscript_path") or None)
                    py_info, r_info = fpy.result(), fr.result()
                self._env_cache = {"python": py_info, "r": r_info,
                                   "sql": self._duckdb_version(),
                                   "workspace": str(self.ws), "home": str(self.store.home)}
            return self._env_cache

    @staticmethod
    def _duckdb_version() -> dict:
        try:
            import duckdb
            return {"duckdb": duckdb.__version__}
        except Exception as e:  # pragma: no cover
            return {"duckdb": None, "error": str(e)}

    def datasets(self) -> list[dict]:
        out = []
        for f in sorted((self.ws / "data").iterdir()):
            if f.is_file():
                out.append({"name": f.name, "size": f.stat().st_size, "path": f"data/{f.name}"})
        return out

    def preview(self, name: str) -> dict | None:
        if not SAFE_NAME.match(name):
            return None
        f = self.ws / "data" / name
        if not f.exists():
            return None
        if f.suffix == ".csv":
            res = runner.run_sql(f"SELECT * FROM read_csv_auto('data/{name}', header=true, all_varchar=true) LIMIT 50", self.ws)
            prof = runner.run_sql(f"SUMMARIZE SELECT * FROM read_csv_auto('data/{name}', header=true)", self.ws)
            lines = sum(1 for _ in f.open(encoding="utf-8", errors="replace")) - 1
            return {"kind": "table", "table": res.table, "profile": prof.table, "rows": lines}
        if f.suffix == ".json":
            return {"kind": "text", "text": f.read_text(encoding="utf-8")[:20000]}
        if f.suffix == ".db":
            import sqlite3
            con = sqlite3.connect(f.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                text = []
                for t in tables:
                    cols = [r[1] + " " + r[2] for r in con.execute(f'PRAGMA table_info("{t}")')]
                    n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                    text.append(f"{t} ({n} rows): " + ", ".join(cols))
            finally:
                con.close()
            return {"kind": "text", "text": "SQLite database\n\n" + "\n".join(text)}
        return {"kind": "text", "text": "(binary file)"}

    def figures(self) -> list[dict]:
        d = self.ws / "figures"
        files = sorted(d.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True) if d.exists() else []
        return [{"name": p.name, "time": p.stat().st_mtime} for p in files]

    def save_report(self, body: dict) -> dict:
        name = re.sub(r"[^A-Za-z0-9_-]+", "-", body.get("filename") or "report").strip("-") or "report"
        rdir = self.ws / "reports"
        rdir.mkdir(exist_ok=True)
        paths = {}
        if body.get("html"):
            p = rdir / f"{name}.html"
            p.write_text(body["html"], encoding="utf-8")
            paths["html"] = str(p)
        if body.get("markdown"):
            p = rdir / f"{name}.md"
            p.write_text(body["markdown"], encoding="utf-8")
            paths["markdown"] = str(p)
        return {"saved": paths}


# ---------------------------------------------------------------- HTTP plumbing

def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DataLab/" + __version__

        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200):
            self._send(status, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

        def _not_found(self):
            self._json({"error": "not found"}, 404)

        def _file(self, path: Path):
            if not path.exists() or not path.is_file():
                return self._not_found()
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            self._send(200, path.read_bytes(), ctype)

        def do_GET(self):
            url = urlparse(self.path)
            p = unquote(url.path)
            q = dict(x.split("=", 1) for x in url.query.split("&") if "=" in x)
            try:
                if p in ("/", "/index.html"):
                    return self._file(STATIC / "index.html")
                if p.startswith("/static/"):
                    name = p[len("/static/"):]
                    if not SAFE_NAME.match(name):
                        return self._not_found()
                    return self._file(STATIC / name)
                if p.startswith("/figures/"):
                    name = p[len("/figures/"):]
                    if not SAFE_NAME.match(name):
                        return self._not_found()
                    return self._file(app.ws / "figures" / name)
                if p == "/api/overview":
                    return self._json(app.overview())
                if p.startswith("/api/stage/"):
                    d = app.stage(p.rsplit("/", 1)[1])
                    return self._json(d) if d else self._not_found()
                if p.startswith("/api/exercise/"):
                    d = app.exercise(p.rsplit("/", 1)[1])
                    return self._json(d) if d else self._not_found()
                if p == "/api/env":
                    return self._json(app.environment(refresh=q.get("refresh") == "1"))
                if p == "/api/settings":
                    return self._json(app.settings())
                if p == "/api/datasets":
                    return self._json(app.datasets())
                if p.startswith("/api/dataset/"):
                    d = app.preview(p.rsplit("/", 1)[1])
                    return self._json(d) if d else self._not_found()
                if p == "/api/figures":
                    return self._json(app.figures())
                if p in ("/api/report", "/api/project", "/api/playground"):
                    return self._json(app.store.get(p.rsplit("/", 1)[1]))
                return self._not_found()
            except Exception as e:  # pragma: no cover - surfaced to the UI
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        def do_POST(self):
            if self.headers.get("X-DataLab") != "1":
                return self._json({"error": "missing X-DataLab header"}, HTTPStatus.FORBIDDEN)
            p = urlparse(self.path).path
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            try:
                if p == "/api/run":
                    return self._json(app.run(body))
                if p.startswith("/api/solution/"):
                    d = app.solution(p.rsplit("/", 1)[1])
                    return self._json(d) if d else self._not_found()
                if p.startswith("/api/quiz/"):
                    d = app.grade_quiz(p.rsplit("/", 1)[1], body.get("answers", []))
                    return self._json(d) if d else self._not_found()
                if p == "/api/save":
                    ex = body.get("exercise")
                    if ex in app.cur.by_id:
                        app.store.save_code(ex, body.get("code", ""))
                    return self._json({"ok": True})
                if p == "/api/settings":
                    s = app.settings()
                    for k in ("python_path", "rscript_path"):
                        if k in body:
                            s[k] = str(body[k]).strip()
                    if "timeout" in body:
                        s["timeout"] = max(10, min(1800, int(body["timeout"])))
                    app.store.put("settings", s)
                    return self._json(app.environment(refresh=True))
                if p in ("/api/report", "/api/project", "/api/playground"):
                    app.store.put(p.rsplit("/", 1)[1], body)
                    return self._json({"ok": True})
                if p == "/api/report/export":
                    return self._json(app.save_report(body))
                if p == "/api/reset-data":
                    prepare_workspace(app.store.home, reset=True)
                    return self._json({"ok": True})
                if p == "/api/reset-progress":
                    app.store.reset_progress()
                    return self._json({"ok": True})
                return self._not_found()
            except Exception as e:  # pragma: no cover
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    return Handler


def serve(app: App, host: str = "127.0.0.1", port: int = 8070) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    return httpd
