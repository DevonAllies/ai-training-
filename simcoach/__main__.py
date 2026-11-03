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


def _running_instance(port: int) -> dict | None:
    """Status of a SimCoach already running on this port, or None."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=0.7) as r:
            d = json.loads(r.read().decode())
            return d if "version" in d else None
    except Exception:
        return None


def _already_running(port: int) -> bool:
    return _running_instance(port) is not None


def _ask_to_quit(port: int) -> None:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2).close()
    except Exception:
        pass


def _wait_port_free(port: int, timeout: float = 20.0) -> bool:
    """Wait until the previous instance has released the port."""
    import socket
    import time
    end = time.time() + timeout
    while time.time() < end:
        if not _already_running(port):
            with socket.socket() as s:
                if sys.platform != "win32":      # match uvicorn: ignore sockets left in TIME_WAIT
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("127.0.0.1", port))
                    return True
                except OSError:
                    pass
        time.sleep(0.3)
    return False


def relaunch_command(port: int, demo: bool = False) -> list[str]:
    """Command line that starts SimCoach again (installed exe or python -m simcoach)."""
    base = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "simcoach"]
    args = ["--takeover", "--no-browser", "--port", str(port)]
    return base + args + (["--demo"] if demo else [])


def spawn_detached(cmd: list[str]) -> None:
    import subprocess
    if sys.platform == "win32":
        subprocess.Popen(cmd, creationflags=0x00000008 | 0x00000200, close_fds=True)
    else:
        subprocess.Popen(cmd, start_new_session=True, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
    ap.add_argument("--host", default=None,
                    help="Listen address (default: this PC only, or your network when "
                         "'Allow my tablet/phone' is on in Settings). 0.0.0.0 = whole network")
    ap.add_argument("--demo", action="store_true", help="Simulated driver instead of iRacing")
    ap.add_argument("--demo-speed", type=float, default=1.0, help=argparse.SUPPRESS)
    ap.add_argument("--no-browser", action="store_true", help="Don't open the dashboard")
    ap.add_argument("--no-overlay", action="store_true", help="Don't show the in-game overlay window")
    ap.add_argument("--no-tray", action="store_true", help="Don't show the system-tray icon")
    ap.add_argument("--no-update", action="store_true", help="Don't check for updates")
    ap.add_argument("--updated", action="store_true", help=argparse.SUPPRESS)   # relaunch after update
    ap.add_argument("--takeover", action="store_true", help=argparse.SUPPRESS)  # wait for the old instance to exit
    ap.add_argument("--import", dest="import_files", nargs="*", metavar="XLSX",
                    help="Import Garage 61 session export(s) and exit")
    ap.add_argument("--version", action="version", version=f"SimCoach {__version__}")
    args = ap.parse_args(argv)

    log_path = _setup_logging()
    if args.updated:
        args.no_browser = True
    url = f"http://127.0.0.1:{args.port}/"

    if args.import_files:
        from . import sessions
        for f in args.import_files:
            print("Imported", f, "->", sessions.import_file(f))
        return

    running = None if args.takeover else _running_instance(args.port)
    if running and running.get("demo") and not args.demo:
        # The demo is running but the user started the real app: close the demo, start live mode.
        log.info("Demo is running - closing it and starting live mode")
        _ask_to_quit(args.port)
        running = None
        args.takeover = True
    if running:
        # Second launch (e.g. clicking the shortcut again) just opens the dashboard.
        log.info("SimCoach is already running - opening the dashboard")
        if not args.no_browser:
            webbrowser.open(url)
        return
    if args.takeover and not _wait_port_free(args.port):
        log.error("Previous SimCoach did not exit in time - giving up")
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
    server_ref: dict = {}

    def quit_all():
        stop.set()
        if "server" in server_ref:
            server_ref["server"].should_exit = True

    stop = threading.Event()
    from .updater import Updater
    updater = Updater(config, __version__,
                      is_busy=lambda: bool(engine.connected and engine.last_sample
                                           and engine.last_sample.get("on_track")),
                      on_quit=quit_all)
    def restart_live():
        spawn_detached(relaunch_command(args.port, demo=False))
        threading.Timer(0.5, quit_all).start()

    def restart_app():
        spawn_detached(relaunch_command(args.port, demo=args.demo))
        threading.Timer(0.5, quit_all).start()

    host = args.host or ("0.0.0.0" if config.lan_access else "127.0.0.1")
    app = create_app(engine, config, demo_mode=args.demo, updater=updater,
                     on_quit=lambda: threading.Timer(0.3, quit_all).start(), on_restart_live=restart_live,
                     on_restart=restart_app, bind_host=host, port=args.port)
    engine.on_session_change = auto_sector_targets
    engine.start()
    if not args.no_update and not args.demo:
        updater.start()
    if args.updated:
        log.info("Updated to %s", __version__)

    print(f"\n  SimCoach {__version__} running at {url}\n  Browser overlay: {url}overlay\n"
          f"  Press Ctrl+C to quit.\n")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    if host != "127.0.0.1":
        from .lan import lan_urls
        log.info("Dashboard on your network: %s", ", ".join(lan_urls(args.port)))
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=args.port,
                                           log_level="warning", log_config=None))
    server_ref["server"] = server

    tray = None
    if not args.no_tray:
        from .tray import Tray
        tray = Tray(config, url, quit_all, updater)
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
        updater.stop()
        engine.stop()
        log.info("SimCoach stopped")


if __name__ == "__main__":
    main()
