"""Start SimCoach:  python -m simcoach  [--demo] [--port 8061] [--no-browser] [--no-overlay]"""

from __future__ import annotations

import argparse
import logging
import threading
import webbrowser
from pathlib import Path

import uvicorn

from . import sessions
from .config import Config
from .live import DemoSource, LiveEngine
from .server import auto_sector_targets, create_app

log = logging.getLogger("simcoach")


def import_sample_data() -> None:
    """Import Garage 61 exports shipped in ./sample_data (once)."""
    folder = Path(__file__).resolve().parent.parent / "sample_data"
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
    ap = argparse.ArgumentParser(prog="simcoach", description="iRacing training coach with Garage 61")
    ap.add_argument("--port", type=int, default=8061)
    ap.add_argument("--host", default="127.0.0.1",
                    help="Use 0.0.0.0 to view the dashboard from a tablet/phone on your network")
    ap.add_argument("--demo", action="store_true", help="Simulated driver instead of iRacing")
    ap.add_argument("--no-browser", action="store_true", help="Don't open the dashboard")
    ap.add_argument("--no-overlay", action="store_true", help="Don't show the in-game overlay window")
    ap.add_argument("--import", dest="import_files", nargs="*", metavar="XLSX",
                    help="Import Garage 61 session export(s) and exit")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.import_files:
        for f in args.import_files:
            print("Imported", f, "->", sessions.import_file(f))
        return

    import_sample_data()
    config = Config.load()
    engine = LiveEngine(config, DemoSource() if args.demo else None)
    if args.demo:
        from . import demo
        engine.set_reference(demo.reference_lap())
    app = create_app(engine, config, demo_mode=args.demo)
    engine.on_session_change = auto_sector_targets
    engine.start()

    url = f"http://127.0.0.1:{args.port}/"
    print(f"\n  SimCoach running at {url}\n  Browser overlay: {url}overlay\n  Press Ctrl+C to quit.\n")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="warning"))

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

            def quit_all():
                server.should_exit = True

            try:
                overlay(engine.overlay, config, on_quit=quit_all)
            except Exception as exc:   # e.g. no display available
                log.warning("Overlay window failed (%s); continuing without it.", exc)
                t.join()
            else:
                server.should_exit = True
                t.join(timeout=3)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
