"""System-tray icon (Windows notification area) so SimCoach runs like a normal app
without a console window: open the dashboard, switch overlay/voice modes, quit.

Uses pystray + Pillow when available; silently does nothing otherwise.
"""

from __future__ import annotations

import logging
import threading
import webbrowser
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)
ICON = Path(__file__).parent / "static" / "icon.png"


class Tray:
    def __init__(self, config: Config, url: str, on_quit, updater=None):
        self.updater = updater
        self.config = config
        self.url = url
        self.on_quit = on_quit
        self.icon = None

    def start(self) -> bool:
        try:
            import pystray  # type: ignore
            from PIL import Image
        except Exception as exc:  # optional dependency
            log.info("Tray icon unavailable (%s)", exc)
            return False

        def mode_item(label, key, value):
            def act(icon, item):
                setattr(self.config, key, value)
                self._save()
            return pystray.MenuItem(label, act, checked=lambda item: getattr(self.config, key) == value,
                                    radio=True)

        menu = pystray.Menu(
            pystray.MenuItem("Open dashboard", lambda i, it: webbrowser.open(self.url), default=True),
            pystray.MenuItem("Open browser overlay", lambda i, it: webbrowser.open(self.url + "overlay")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Overlay", pystray.Menu(
                mode_item("Practice sessions only", "overlay_mode", "practice"),
                mode_item("Always", "overlay_mode", "always"),
                mode_item("Off", "overlay_mode", "off"))),
            pystray.MenuItem("Voice coach", pystray.Menu(
                mode_item("Cues before corners", "voice_mode", "cues"),
                mode_item("Detailed", "voice_mode", "detailed"),
                mode_item("Off", "voice_mode", "off"))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: self._update_label(), self._update_action,
                             visible=lambda item: self.updater is not None),
            pystray.MenuItem("Quit SimCoach", self._quit),
        )
        try:
            image = Image.open(ICON)
            self.icon = pystray.Icon("SimCoach", image, "SimCoach", menu)
            threading.Thread(target=self.icon.run, name="tray", daemon=True).start()
            return True
        except Exception as exc:
            log.warning("Could not start tray icon: %s", exc)
            return False

    def _update_label(self) -> str:
        st = self.updater.status() if self.updater else {}
        if st.get("status") == "ready":
            return f"Install update {st.get('latest')} now"
        if st.get("status") == "downloading":
            return f"Downloading update… {int(st.get('progress', 0) * 100)}%"
        return "Check for updates"

    def _update_action(self, icon=None, item=None):
        if not self.updater:
            return
        if self.updater.status().get("status") == "ready":
            self.updater.install(force=True)
        else:
            self.updater.check_soon()

    def _save(self):
        try:
            self.config.save()
        except OSError:
            pass

    def _quit(self, icon=None, item=None):
        self.stop()
        self.on_quit()

    def stop(self):
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
