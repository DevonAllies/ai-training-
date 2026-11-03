"""Start SimCoach:  python -m simcoach  [--demo] [--port 8061] [--no-browser] [--no-overlay]"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

log = logging.getLogger("simcoach")


def _fix_stdio() -> None:
    """The installed app has no console: sys.stdout/stderr are None, which breaks
    libraries that write to them (uvicorn checks isatty on startup)."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def _setup_logging() -> Path:
    from .config import app_dir
    path = app_dir() / "simcoach.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fh = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr and getattr(sys.stderr, "isatty", lambda: False)():
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    return path


def _already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=0.7) as r:
            return "version" in json.loads(r.read().decode())
    except Exception:
        return False


def import_sample_data() -> None:
    """Import Garage 61 exports shipped in ./sample_data (once)."""
    from . import sessions
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))   # PyInstaller bundle
    folder = base / "sample_data"
    if not folder.is_dir():
        return
    marker = sessions.sessions_dir() / ".sample_imported"
    done = set(marker.read_text().split("\n")) if marker.exists() else set()
    for f in sorted(folder.glob("*.xlsx")):
        if f.name in done:
            continue
        try:
            sessions.import_file(f)
            done.add(f.name)
            log.info("Imported Garage 61 export %s", f.name)
        except Exception as exc:  # a bad sample file must not stop the app
            log.warning("Could not import %s: %s", f.name, exc)
    marker.write_text("\n".join(sorted(done)))


def main(argv: list[str] | None = None) -> None:
    _fix_stdio()
    from . import __version__

    ap = argparse.ArgumentParser(prog="simcoach", description="iRacing training coach with Garage 61")
    ap.add_argument("--port", type=int, default=8061)
    ap.add_argument("--host", default="127.0.0.1",
                    help="Use 0.0.0.0 to view the dashboard from a tablet/phone on your network")
    ap.add_argument("--demo", action="store_true", help="Simulated driver instead of iRacing")
    ap.add_argument("--demo-speed", type=float, default=1.0, help=argparse.SUPPRESS)
    ap.add_argument("--no-browser", action="store_true", help="Don't open the dashboard")
    ap.add_argument("--no-overlay", action="store_true", help="Don't show the in-game overlay window")
    ap.add_argument("--no-tray", action="store_true", help="Don't show the system-tray icon")
    ap.add_argument("--import", dest="import_files", nargs="*", metavar="XLSX",
                    help="Import Garage 61 session export(s) and exit")
    ap.add_argument("--version", action="version", version=f"SimCoach {__version__}")
    args = ap.parse_args(argv)

    log_path = _setup_logging()
    url = f"http://127.0.0.1:{args.port}/"

    if args.import_files:
        from . import sessions
        for f in args.import_files:
            print("Imported", f, "->", sessions.import_file(f))
        return

    # Second launch (e.g. clicking the shortcut again) just opens the dashboard.
    if _already_running(args.port):
        log.info("SimCoach is already running - opening the dashboard")
        if not args.no_browser:
            webbrowser.open(url)
        return

    import uvicorn

    from .config import Config
    from .live import DemoSource, LiveEngine
    from .server import auto_sector_targets, create_app

    log.info("SimCoach %s starting (log: %s)", __version__, log_path)
    import_sample_data()
    config = Config.load()
    engine = LiveEngine(config, DemoSource(args.demo_speed) if args.demo else None)
    if args.demo:
        from . import demo
        engine.set_reference(demo.reference_lap())
    app = create_app(engine, config, demo_mode=args.demo)
    engine.on_session_change = auto_sector_targets
    engine.start()

    print(f"\n  SimCoach {__version__} running at {url}\n  Browser overlay: {url}overlay\n"
          f"  Press Ctrl+C to quit.\n")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port,
                                           log_level="warning", log_config=None))
    stop = threading.Event()

    def quit_all():
        stop.set()
        server.should_exit = True

    tray = None
    if not args.no_tray:
        from .tray import Tray
        tray = Tray(config, url, quit_all)
        if not tray.start():
            tray = None

    overlay = None
    if not args.no_overlay:
        try:
            from .overlay import run_overlay
            overlay = run_overlay
        except ImportError as exc:     # tkinter missing (e.g. minimal Linux Python)
            log.warning("In-game overlay unavailable (%s). Use the browser overlay instead.", exc)

    try:
        if overlay is None:
            server.run()
        else:
            # Tk must own the main thread; the web server runs alongside it.
            t = threading.Thread(target=server.run, name="web", daemon=True)
            t.start()
            try:
                overlay(engine.overlay, config, on_quit=quit_all, stop_event=stop)
            except Exception as exc:   # e.g. no display available
                log.warning("Overlay window failed (%s); continuing without it.", exc)
                t.join()
            else:
                server.should_exit = True
                t.join(timeout=3)
    except KeyboardInterrupt:
        pass
    finally:
        if tray:
            tray.stop()
        engine.stop()
        log.info("SimCoach stopped")


if __name__ == "__main__":
    main()
