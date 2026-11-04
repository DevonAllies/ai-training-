"""Start DataLab Trainer:  python -m datalab [--port 8070] [--no-browser]"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

from . import __version__


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="datalab", description="DataLab Trainer - SQL, Python and R data science training")
    ap.add_argument("--port", type=int, default=8070)
    ap.add_argument("--host", default="127.0.0.1", help="interface to bind (default: this computer only)")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)

    from .server import App, serve
    from .store import Store

    store = Store()
    app = App(store)
    port = args.port
    for attempt in range(20):
        try:
            httpd = serve(app, args.host, port)
            break
        except OSError:
            port += 1
    else:
        print("Could not find a free port.", file=sys.stderr)
        return 1
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{port}/"
    print(f"DataLab Trainer {__version__}")
    print(f"  Open {url} in your browser (Ctrl+C to stop).")
    print(f"  Your workspace: {store.workspace}")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
