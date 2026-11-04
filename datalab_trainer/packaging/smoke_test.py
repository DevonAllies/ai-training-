"""Smoke-test a packaged DataLab build: start it, then run every exercise's model
solution through its API and check that it passes.

    python packaging/smoke_test.py dist/DataLabTrainer/DataLabTrainer [--skip-r]

Uses only the standard library, so any Python can run it. Exits non-zero on failure.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from datalab.curriculum import Curriculum  # noqa: E402  (pure stdlib module)

PORT = 8099


def call(path: str, body: dict | None = None, timeout: int = 600):
    url = f"http://127.0.0.1:{PORT}{path}"
    if body is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-DataLab": "1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main() -> int:
    exe = sys.argv[1]
    skip_r = "--skip-r" in sys.argv
    home = tempfile.mkdtemp(prefix="datalab-smoke-")
    env = dict(os.environ, DATALAB_HOME=home)
    proc = subprocess.Popen([exe, "--no-browser", "--port", str(PORT)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(90):
            try:
                ov = call("/api/overview", timeout=5)
                break
            except Exception:
                if proc.poll() is not None:
                    print(proc.stdout.read().decode(errors="replace"))
                    print("The app exited during start-up.")
                    return 1
                time.sleep(1)
        else:
            print("The app did not start within 90 s.")
            return 1
        print(f"DataLab {ov['version']} is up: {len(ov['stages'])} modules, {len(ov['exercises'])} exercises")
        envinfo = call("/api/env?refresh=1", timeout=180)
        py = envinfo["python"]
        print("Python:", py.get("version"), py.get("path"))
        missing = [k for k, v in py.get("packages", {}).items() if not v]
        print("R:", envinfo["r"].get("version"), envinfo["r"].get("path"))
        if missing:
            print("Packages missing from the build:", missing)
            return 1

        cur = Curriculum()
        failures = []
        for ex in cur.exercises:
            if ex.lang == "r" and (skip_r or not envinfo["r"].get("version")):
                continue
            t0 = time.time()
            res = call("/api/run", {"exercise": ex.id, "code": ex.solution, "check": True})
            ok = bool(res.get("check") and res["check"]["passed"])
            print(f"  {'PASS' if ok else 'FAIL'} {ex.id:22s} {time.time() - t0:5.1f}s")
            if not ok:
                failures.append(ex.id)
                print("    ", (res.get("check") or {}).get("message"))
                print("    ", (res.get("stderr") or "")[-1500:].replace("\n", "\n     "))
        res = call("/api/run", {"lang": "python", "code": "import json, csv, statistics, sqlite3, base64, io\nprint('stdlib ok')"})
        if "stdlib ok" not in res.get("stdout", ""):
            failures.append("stdlib-imports")
            print(res.get("stderr"))
        print(f"{len(failures)} failure(s)")
        return 1 if failures else 0
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
