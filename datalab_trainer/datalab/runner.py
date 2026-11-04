"""Run learner code in SQL (DuckDB), Python or R and optionally check it.

* SQL runs in-process on DuckDB. Every CSV in workspace/data is available as a
  view named after the file (``customers``, ``orders`` ...), and relative paths
  such as ``'data/orders.csv'`` resolve against the workspace.
* Python runs in a separate interpreter (by default the one running DataLab) so
  a crash or an endless loop cannot take the app down. Matplotlib figures are
  captured as PNGs.
* R runs with ``Rscript``. Base-graphics and ggplot figures are captured as PNGs.

All three behave the same on Windows and Linux: no shell, no WSL, no Wine.
"""
from __future__ import annotations

import base64
import datetime as dt
import glob
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

MAX_ROWS = 500
MAX_OUTPUT = 200_000


@dataclass
class RunResult:
    ok: bool = True
    stdout: str = ""
    stderr: str = ""
    images: list[str] = field(default_factory=list)  # file names under the figures folder
    table: dict | None = None  # {"columns": [...], "rows": [[...]], "truncated": bool, "total": n}
    check: dict | None = None  # {"passed": bool, "message": str}
    elapsed: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok, "stdout": self.stdout[-MAX_OUTPUT:], "stderr": self.stderr[-MAX_OUTPUT:],
            "images": self.images, "table": self.table, "check": self.check,
            "elapsed": round(self.elapsed, 2),
        }


# --------------------------------------------------------------------------- helpers

def _figures_dir(workspace: Path) -> Path:
    d = workspace / "figures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _collect_figures(out: Path, workspace: Path, label: str) -> list[str]:
    """Move fig_*.png from a run folder into workspace/figures with unique names."""
    figs = sorted(out.glob("fig_*.png"))
    dest = _figures_dir(workspace)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    names = []
    for i, f in enumerate(figs, 1):
        if f.stat().st_size < 200:  # empty device
            continue
        name = f"{stamp}-{label}-{i:02d}.png"
        shutil.move(str(f), dest / name)
        names.append(name)
    _prune_figures(dest)
    return names


def _prune_figures(dest: Path, keep: int = 120) -> None:
    files = sorted(dest.glob("*.png"), key=lambda p: p.stat().st_mtime)
    for p in files[:-keep]:
        try:
            p.unlink()
        except OSError:
            pass


def _safe_label(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", s or "run")[:40] or "run"


def _decode(b: bytes) -> str:
    for enc in ("utf-8", sys.getdefaultencoding()):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def _subprocess_flags() -> dict:
    if os.name == "nt":  # don't flash a console window on Windows
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def _run_proc(cmd: list[str], cwd: Path, env: dict, timeout: int) -> tuple[int, str, str, bool]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, **_subprocess_flags())
        return p.returncode, _decode(p.stdout), _decode(p.stderr), False
    except subprocess.TimeoutExpired as e:
        return -1, _decode(e.stdout or b""), _decode(e.stderr or b""), True


# --------------------------------------------------------------------------- SQL

def _jsonable(v):
    if v is None:
        return None
    if isinstance(v, float):
        return None if math.isnan(v) else v
    if isinstance(v, (int, str, bool)):
        return v
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()
    try:
        import decimal
        if isinstance(v, decimal.Decimal):
            return float(v)
    except Exception:
        pass
    return str(v)


def sql_connect(workspace: Path):
    import duckdb

    con = duckdb.connect(":memory:")
    ws = str(workspace).replace("\\", "/").replace("'", "''")
    con.execute(f"SET file_search_path = '{ws}'")
    for f in sorted((workspace / "data").glob("*.csv")):
        rel = f"data/{f.name}"
        name = f.stem
        con.execute(f'CREATE OR REPLACE VIEW "{name}" AS SELECT * FROM read_csv_auto(\'{rel}\', header=true)')
    pj = workspace / "data" / "products.json"
    if pj.exists():
        try:
            con.execute("CREATE OR REPLACE VIEW products AS SELECT * FROM read_json_auto('data/products.json')")
        except Exception:
            pass
    return con


def _sql_query(con, code: str):
    rel = con.execute(code)
    if rel.description is None:
        return [], []
    cols = [d[0] for d in rel.description]
    rows = rel.fetchall()
    return cols, rows


def _close(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if math.isnan(a) and math.isnan(b):
            return True
        return abs(a - b) <= 1e-6 + 1e-4 * max(abs(a), abs(b))
    return _jsonable(a) == _jsonable(b)


def _row_key(row):
    return tuple((0, "") if v is None else (1, round(v, 4)) if isinstance(v, float) else (1, str(v)) for v in row)


def compare_tables(got_cols, got_rows, exp_cols, exp_rows, ordered: bool) -> tuple[bool, str]:
    if len(got_cols) != len(exp_cols):
        return False, (f"Your result has {len(got_cols)} column(s); expected {len(exp_cols)}: "
                       f"{', '.join(exp_cols)}.")
    if len(got_rows) != len(exp_rows):
        return False, f"Your result has {len(got_rows)} row(s); expected {len(exp_rows)}."
    a, b = list(got_rows), list(exp_rows)
    if not ordered:
        a, b = sorted(a, key=_row_key), sorted(b, key=_row_key)
    for i, (ra, rb) in enumerate(zip(a, b), 1):
        for j, (va, vb) in enumerate(zip(ra, rb)):
            if not _close(va, vb):
                where = f"row {i}" if ordered else "the rows"
                return False, (f"Column '{exp_cols[j]}' differs in {where}: got {_jsonable(va)!r}, "
                               f"expected {_jsonable(vb)!r}." + ("" if ordered else
                               " (Row order doesn't matter for this task.)"))
    names_a = [c.lower() for c in got_cols]
    names_b = [c.lower() for c in exp_cols]
    if names_a != names_b:
        return True, ("Values are correct. Tip: name the columns " + ", ".join(exp_cols)
                      + " (use AS) so your output matches the task exactly.")
    if ordered:
        return True, "Correct, including row order."
    return True, "Correct."


def run_sql(code: str, workspace: Path, solution: str | None = None, ordered: bool = False) -> RunResult:
    res = RunResult()
    t0 = time.perf_counter()
    con = None
    try:
        con = sql_connect(workspace)
        cols, rows = _sql_query(con, code)
        res.table = {"columns": cols, "rows": [[_jsonable(v) for v in r] for r in rows[:MAX_ROWS]],
                     "truncated": len(rows) > MAX_ROWS, "total": len(rows)}
        if not cols:
            res.stdout = "Statement ran (no rows returned)."
        if solution:
            con2 = sql_connect(workspace)
            try:
                ecols, erows = _sql_query(con2, solution)
            finally:
                con2.close()
            passed, msg = compare_tables(cols, rows, ecols, erows, ordered)
            res.check = {"passed": passed, "message": msg}
    except Exception as e:  # duckdb errors are descriptive; show them as-is
        res.ok = False
        res.stderr = f"{type(e).__name__}: {e}"
        if solution:
            res.check = {"passed": False, "message": "Your query raised an error, see below."}
    finally:
        if con is not None:
            con.close()
    res.elapsed = time.perf_counter() - t0
    return res


# --------------------------------------------------------------------------- Python

_MPL_BACKEND = r'''
"""Matplotlib backend used by DataLab: plt.show() saves figures as PNG."""
import os
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas  # noqa: F401
from matplotlib.backend_bases import FigureManagerBase as FigureManager  # noqa: F401

_OUT = os.environ.get("DATALAB_OUT", ".")
_count = [0]


def save_all(close=True):
    import matplotlib.pyplot as plt
    for num in plt.get_fignums():
        fig = plt.figure(num)
        if not fig.axes:
            continue
        _count[0] += 1
        fig.savefig(os.path.join(_OUT, "fig_%03d.png" % _count[0]), dpi=100, bbox_inches="tight")
    if close:
        plt.close("all")


def show(*args, **kwargs):
    save_all()
'''

_PY_DRIVER = r'''
import json, linecache, os, sys, traceback
_out = sys.argv[1]
_result = {"user_ok": False, "check": None}
_ns = {"__name__": "__main__", "__builtins__": __builtins__}


def _src(name):
    with open(os.path.join(_out, name), encoding="utf-8") as f:
        return f.read()


def _exec(src, fname):
    linecache.cache[fname] = (len(src), None, src.splitlines(True), fname)
    exec(compile(src, fname, "exec"), _ns)


try:
    import pandas as _pd
    _pd.set_option("display.width", 160)
    _pd.set_option("display.max_columns", 40)
    del _pd
except Exception:
    pass

try:
    _exec(_src("user.py"), "your_code.py")
    _result["user_ok"] = True
except SystemExit:
    _result["user_ok"] = True
except BaseException:
    _et, _ev, _tb = sys.exc_info()
    traceback.print_exception(_et, _ev, _tb.tb_next.tb_next if _tb.tb_next else _tb)

sys.stdout.flush()
if _result["user_ok"] and os.path.exists(os.path.join(_out, "check.py")):
    class CheckFailed(Exception):
        pass

    def expect(cond, msg):
        if not cond:
            raise CheckFailed(msg)

    _ns["expect"] = expect
    _ns["CheckFailed"] = CheckFailed
    try:
        _exec(_src("check.py"), "check.py")
        _result["check"] = {"passed": True, "message": _ns.get("CHECK_MESSAGE", "All checks passed.")}
    except CheckFailed as e:
        _result["check"] = {"passed": False, "message": str(e)}
    except NameError as e:
        _result["check"] = {"passed": False, "message": "Something the task asks you to create is missing: %s" % e}
    except Exception as e:
        _result["check"] = {"passed": False, "message": "%s: %s" % (type(e).__name__, e)}

if "matplotlib.pyplot" in sys.modules:
    try:
        import _datalab_mpl
        _datalab_mpl.save_all(close=False)
    except Exception:
        pass

with open(os.path.join(_out, "result.json"), "w", encoding="utf-8") as f:
    json.dump(_result, f)
'''


def run_python(code: str, workspace: Path, check: str | None = None, python: str | None = None,
               timeout: int = 120, label: str = "py") -> RunResult:
    res = RunResult()
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="datalab-py-") as tmp:
        out = Path(tmp)
        (out / "user.py").write_text(code, encoding="utf-8")
        if check:
            (out / "check.py").write_text(check, encoding="utf-8")
        (out / "_driver.py").write_text(_PY_DRIVER, encoding="utf-8")
        (out / "_datalab_mpl.py").write_text(_MPL_BACKEND, encoding="utf-8")
        env = dict(os.environ)
        env.update({
            "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
            "MPLBACKEND": "module://_datalab_mpl", "DATALAB_OUT": str(out),
            "PYTHONPATH": str(out) + os.pathsep + env.get("PYTHONPATH", ""),
            "PYTHONWARNINGS": "ignore::FutureWarning",
        })
        exe = python or sys.executable
        code_, so, se, timed_out = _run_proc([exe, str(out / "_driver.py"), str(out)], workspace, env, timeout)
        res.stdout, res.stderr = so, se
        if timed_out:
            res.ok = False
            res.stderr += f"\nStopped: the code ran longer than {timeout} seconds."
        import json
        rj = out / "result.json"
        if rj.exists():
            r = json.loads(rj.read_text(encoding="utf-8"))
            res.ok = res.ok and r["user_ok"]
            res.check = r.get("check")
        else:
            res.ok = False
            if code_ not in (0, -1) and not se:
                res.stderr += f"\nPython exited with code {code_}."
        if check and res.check is None:
            res.check = {"passed": False, "message": "Fix the error in your code first."}
        res.images = _collect_figures(out, workspace, _safe_label(label))
    res.elapsed = time.perf_counter() - t0
    return res


# --------------------------------------------------------------------------- R

_R_DRIVER = r'''
.dl <- new.env()
.dl$out <- commandArgs(trailingOnly = TRUE)[1]
.dl$n <- 0L
options(device = function(...) {
  grDevices::png(file.path(.dl$out, "fig_%03d.png"), width = 900, height = 600, res = 110)
})
options(warn = 1, width = 110)
.dl$user_ok <- tryCatch({
  source(file.path(.dl$out, "user.R"), local = globalenv(), echo = FALSE,
         print.eval = TRUE, encoding = "UTF-8", max.deparse.length = Inf)
  TRUE
}, error = function(e) {
  cat("Error: ", conditionMessage(e), "\n", sep = "", file = stderr())
  FALSE
})
if (.dl$user_ok && file.exists(file.path(.dl$out, "check.R"))) {
  expect <- function(cond, msg) {
    if (!isTRUE(all(cond))) stop(structure(class = c("dl_check", "error", "condition"),
                                       list(message = msg, call = NULL)))
    invisible(TRUE)
  }
  .dl$msg <- tryCatch({
    source(file.path(.dl$out, "check.R"), local = globalenv(), encoding = "UTF-8")
    c("PASS", if (exists("CHECK_MESSAGE")) CHECK_MESSAGE else "All checks passed.")
  }, dl_check = function(e) c("FAIL", conditionMessage(e)),
     error = function(e) c("FAIL", paste0("Something the task asks for is missing or wrong: ",
                                           conditionMessage(e))))
  writeLines(.dl$msg, file.path(.dl$out, "check.txt"), useBytes = TRUE)
}
writeLines(if (.dl$user_ok) "OK" else "ERROR", file.path(.dl$out, "status.txt"))
invisible(grDevices::graphics.off())
'''


def find_rscript(configured: str | None = None) -> str | None:
    if configured and Path(configured).exists():
        return configured
    found = shutil.which("Rscript")
    if found:
        return found
    if os.name == "nt":
        cands = []
        for base in [os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "R")]:
            cands += glob.glob(os.path.join(base, "R", "R-*", "bin", "Rscript.exe"))
            cands += glob.glob(os.path.join(base, "R-*", "bin", "Rscript.exe"))
        if cands:
            def ver(p):
                m = re.search(r"R-(\d+)\.(\d+)\.(\d+)", p)
                return tuple(int(x) for x in m.groups()) if m else (0,)
            return max(cands, key=ver)
    else:
        for p in ["/usr/bin/Rscript", "/usr/local/bin/Rscript", "/opt/R/current/bin/Rscript"]:
            if Path(p).exists():
                return p
    return None


R_MISSING = ("R was not found. Install it natively (no Wine needed):\n"
             "  Windows: download R from https://cran.r-project.org/bin/windows/base/ and run the installer.\n"
             "  Ubuntu:  sudo apt install r-base\n"
             "Then restart DataLab, or set the Rscript path on the Setup page.")


def run_r(code: str, workspace: Path, check: str | None = None, rscript: str | None = None,
          timeout: int = 120, label: str = "r") -> RunResult:
    res = RunResult()
    t0 = time.perf_counter()
    exe = find_rscript(rscript)
    if not exe:
        res.ok = False
        res.stderr = R_MISSING
        if check:
            res.check = {"passed": False, "message": "R is not installed yet - see the Setup page."}
        return res
    with tempfile.TemporaryDirectory(prefix="datalab-r-") as tmp:
        out = Path(tmp)
        (out / "user.R").write_text(code, encoding="utf-8")
        if check:
            (out / "check.R").write_text(check, encoding="utf-8")
        (out / "_driver.R").write_text(_R_DRIVER, encoding="utf-8")
        env = dict(os.environ)
        rc, so, se, timed_out = _run_proc([exe, "--no-save", "--no-restore",
                                          str(out / "_driver.R"), str(out)], workspace, env, timeout)
        res.stdout, res.stderr = so, se
        status = out / "status.txt"
        res.ok = status.exists() and status.read_text(encoding="utf-8", errors="replace").strip() == "OK"
        if timed_out:
            res.ok = False
            res.stderr += f"\nStopped: the code ran longer than {timeout} seconds."
        ck = out / "check.txt"
        if ck.exists():
            lines = ck.read_text(encoding="utf-8", errors="replace").splitlines()
            res.check = {"passed": bool(lines) and lines[0] == "PASS",
                         "message": "\n".join(lines[1:]) or ""}
        elif check:
            res.check = {"passed": False, "message": "Fix the error in your code first."}
        res.images = _collect_figures(out, workspace, _safe_label(label))
    res.elapsed = time.perf_counter() - t0
    return res


# --------------------------------------------------------------------------- environment report

PY_PACKAGES = ["pandas", "numpy", "matplotlib", "scipy", "sklearn", "statsmodels", "duckdb", "openpyxl", "shap"]
R_PACKAGES = ["ggplot2", "dplyr", "tidyr", "readr", "readxl", "jsonlite", "DBI", "RSQLite", "rmarkdown"]


def python_env(python: str | None = None) -> dict:
    exe = python or sys.executable
    probe = ("import importlib, json, sys\nout={'version': sys.version.split()[0], 'packages': {}}\n"
             f"for m in {PY_PACKAGES!r}:\n"
             "    try:\n        mod=importlib.import_module(m); out['packages'][m]=getattr(mod,'__version__','yes')\n"
             "    except Exception:\n        out['packages'][m]=None\nprint(json.dumps(out))\n")
    try:
        p = subprocess.run([exe, "-c", probe], capture_output=True, timeout=90, **_subprocess_flags())
        import json
        info = json.loads(_decode(p.stdout).strip().splitlines()[-1])
        info["path"] = exe
        return info
    except Exception as e:
        return {"path": exe, "error": str(e), "packages": {}}


def r_env(rscript: str | None = None) -> dict:
    exe = find_rscript(rscript)
    if not exe:
        return {"path": None, "error": R_MISSING, "packages": {}}
    pk = ", ".join(f'"{p}"' for p in R_PACKAGES)
    expr = ("cat(paste0('VERSION=', R.version$major, '.', R.version$minor), '\\n');"
            f"for (p in c({pk})) cat(p, '=', if (requireNamespace(p, quietly=TRUE)) "
            "as.character(packageVersion(p)) else 'NA', '\\n', sep='')")
    try:
        p = subprocess.run([exe, "-e", expr], capture_output=True, timeout=90, **_subprocess_flags())
        info: dict = {"path": exe, "packages": {}}
        for line in _decode(p.stdout).splitlines():
            line = line.strip()
            if line.startswith("VERSION="):
                info["version"] = line.split("=", 1)[1].strip()
            elif "=" in line:
                k, v = line.split("=", 1)
                info["packages"][k] = None if v == "NA" else v
        return info
    except Exception as e:
        return {"path": exe, "error": str(e), "packages": {}}


def image_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")
