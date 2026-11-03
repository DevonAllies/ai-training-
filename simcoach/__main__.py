"""Start SimCoach:  python -m simcoach  [--demo] [--port 8061] [--no-browser]"""

from __future__ import annotations

import argparse
import logging
import threading
import webbrowser

import uvicorn

from .config import Config
from .live import DemoSource, LiveEngine
from .server import create_app


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="simcoach", description="iRacing training coach with Garage 61")
    ap.add_argument("--port", type=int, default=8061)
    ap.add_argument("--host", default="127.0.0.1",
                    help="Use 0.0.0.0 to view the dashboard from a tablet/phone on your network")
    ap.add_argument("--demo", action="store_true", help="Simulated driver instead of iRacing")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = Config.load()
    engine = LiveEngine(config, DemoSource() if args.demo else None)
    if args.demo:
        from . import demo
        engine.set_reference(demo.reference_lap())
    engine.start()

    app = create_app(engine, config, demo_mode=args.demo)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\n  SimCoach running at {url}\n  Press Ctrl+C to quit.\n")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
