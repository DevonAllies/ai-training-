"""Auto-update from GitHub Releases.

Flow (installed Windows app):
  1. check   - ask the GitHub API for the latest release of the configured repo
  2. download- fetch SimCoach-Setup-<ver>.exe into %APPDATA%\\SimCoach\\updates
  3. verify  - SHA-256 must match the release's published checksum (GitHub's asset
               digest or the SHA256SUMS.txt asset). No checksum -> no install.
  4. install - run the installer silently and quit; the installer replaces the
               files and starts the new version again.

Modes (Settings -> Updates):
  auto   - download in the background, install automatically when you're not
           driving (iRacing not on track), otherwise wait
  notify - download, then show "Update ready - Install now" in the dashboard/tray
  off    - never check

Safety: it never installs while you're on track; downloads only come from
GitHub-hosted URLs; one background thread with fixed state (no growth).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from .config import Config, app_dir

log = logging.getLogger(__name__)

API = "https://api.github.com/repos/{repo}/releases/latest"
CHECK_EVERY_S = 6 * 3600
FIRST_CHECK_DELAY_S = 20
ALLOWED_HOSTS = ("github.com", "githubusercontent.com")


def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def updates_dir() -> Path:
    d = app_dir() / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _allowed(url: str) -> bool:
    u = urlparse(url)
    return u.scheme == "https" and any(u.hostname == h or (u.hostname or "").endswith("." + h)
                                       for h in ALLOWED_HOSTS)


def can_self_install() -> bool:
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


class Updater:
    def __init__(self, config: Config, current_version: str, is_busy=lambda: False, on_quit=None):
        self.config = config
        self.current = current_version
        self.is_busy = is_busy              # True while driving - never install then
        self.on_quit = on_quit              # called after the installer is launched
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": f"SimCoach-Updater/{current_version}",
                                  "Accept": "application/vnd.github+json"})
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self.state = {"status": "idle", "current": current_version, "latest": None, "notes": "",
                      "release_url": None, "progress": 0.0, "error": None, "checked_at": None,
                      "can_install": can_self_install(), "file": None,
                      "install_problem": None, "last_install_failed": None}
        self._asset: dict | None = None
        self._sha256: str | None = None
        self._run_lock = threading.Lock()   # one check/download at a time (button + background)
        self._check_last_install()

    # ------------------------------------------- did the last install work?
    def _pending_path(self) -> Path:
        return updates_dir() / "pending.json"

    def _check_last_install(self) -> None:
        """An install was started earlier: if we're still on the old version it failed -
        say so (with the installer's log) instead of silently trying the same thing again."""
        p = self._pending_path()
        try:
            pend = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        to = str(pend.get("to") or "")
        if to and is_newer(to, self.current):
            tail = ""
            try:
                lines = (updates_dir() / "install.log").read_text(encoding="utf-8", errors="replace").splitlines()
                tail = " | ".join(l.split(" ", 2)[-1] for l in lines[-4:] if l.strip())
            except OSError:
                pass
            self.state["last_install_failed"] = to
            self.state["install_problem"] = (f"The {to} update was started but didn't install - you're still on "
                                   f"{self.current}. Click Install now to try again, or download it from the "
                                   f"release page." + (f" Installer log: {tail}" if tail else ""))
            log.warning("previous update to %s did not install: %s", to, tail)
        else:
            log.info("update to %s installed", to or self.current)
        p.unlink(missing_ok=True)
    # -------------------------------------------------------------- state
    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)

    def status(self) -> dict:
        with self.lock:
            d = dict(self.state)
        d["mode"] = self.config.update_mode
        return d

    # ------------------------------------------------------------- thread
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="updater", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self.http.close()

    def check_soon(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        if self._stop.wait(FIRST_CHECK_DELAY_S):
            return
        last_check = 0.0
        while not self._stop.is_set():
            forced = self._wake.is_set()
            self._wake.clear()
            mode = self.config.update_mode
            if mode != "off" and (forced or time.time() - last_check >= CHECK_EVERY_S):
                last_check = time.time()
                try:
                    self.run_once()
                except Exception as exc:          # never let the updater crash the app
                    log.exception("update check failed")
                    self._set(status="error", error=str(exc))
            # an update is ready: install as soon as we're not driving (auto mode)
            if self.state["status"] == "ready" and mode == "auto" and not self.is_busy():
                self.install()
            self._wake.wait(60)

    # -------------------------------------------------------------- steps
    def run_once(self) -> dict:
        """Check, and download if a newer version exists. Returns the status."""
        if not self._run_lock.acquire(blocking=False):     # already checking / downloading
            return self.status()
        try:
            self.check()
            if self.state["status"] == "available" and self.config.update_mode in ("auto", "notify"):
                self.download()
            return self.status()
        finally:
            self._run_lock.release()

    def check_now(self) -> dict:
        """'Check for updates now': runs in the background so the page stays responsive;
        the dashboard polls the status (checking -> downloading % -> ready)."""
        if self._run_lock.locked():
            return self.status()
        self._set(status="checking", error=None)

        def work():
            try:
                self.run_once()
                if self.state["status"] == "ready" and self.config.update_mode == "auto" and not self.is_busy():
                    self.install()
            except Exception as exc:
                log.exception("update check failed")
                self._set(status="error", error=str(exc))
        threading.Thread(target=work, name="update-check", daemon=True).start()
        return self.status()

    def check(self) -> dict:
        self._set(status="checking", error=None)
        repo = self.config.update_repo
        r = self.http.get(API.format(repo=repo), timeout=15)
        self._set(checked_at=time.time())
        if r.status_code == 404:
            self._set(status="up_to_date", latest=None, error="No releases published yet.")
            return self.status()
        if r.status_code in (403, 429):
            self._set(status="error", error="GitHub rate limit reached - will retry later.")
            return self.status()
        r.raise_for_status()
        rel = r.json()
        latest = (rel.get("tag_name") or "").lstrip("v")
        assets = rel.get("assets") or []
        setup = next((a for a in assets if re.fullmatch(r"SimCoach-Setup-.*\.exe", a.get("name", ""))), None)
        sums = next((a for a in assets if a.get("name") == "SHA256SUMS.txt"), None)
        self._set(latest=latest, notes=(rel.get("body") or "")[:4000], release_url=rel.get("html_url"))
        if not latest or not is_newer(latest, self.current):
            self._set(status="up_to_date")
            return self.status()
        if setup is None:
            self._set(status="error", error=f"Release {latest} has no installer attached.")
            return self.status()
        self._asset = setup
        self._sha256 = self._expected_sha256(setup, sums)
        existing = updates_dir() / setup["name"]
        if existing.exists() and self._sha256 and _sha256_file(existing) == self._sha256:
            self._set(status="ready", file=str(existing), progress=1.0)
        else:
            self._set(status="available", progress=0.0)
        return self.status()

    def _get_asset(self, asset: dict, stream: bool = False, timeout: int = 30):
        """Fetch a release asset: the normal download link first, then the API asset
        endpoint (works on networks that block github.com web downloads)."""
        last_exc: Exception | None = None
        for url, accept in ((asset.get("browser_download_url", ""), None),
                            (asset.get("url", ""), "application/octet-stream")):
            if not url or not _allowed(url):
                continue
            try:
                headers = {"Accept": accept} if accept else {}
                r = self.http.get(url, stream=stream, timeout=timeout, headers=headers)
                r.raise_for_status()
                return r
            except Exception as exc:
                last_exc = exc
                log.info("download via %s failed: %s", url, exc)
        raise last_exc or RuntimeError("Release asset has no usable download URL")

    def _expected_sha256(self, setup: dict, sums: dict | None) -> str | None:
        digest = setup.get("digest") or ""
        if digest.startswith("sha256:"):
            return digest.split(":", 1)[1].lower()
        if sums:
            try:
                r = self._get_asset(sums, timeout=15)
                for line in r.text.splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[1].lstrip("*") == setup["name"]:
                        return parts[0].lower()
            except Exception as exc:
                log.warning("could not fetch SHA256SUMS: %s", exc)
        return None

    def download(self) -> dict:
        a = self._asset
        if not a:
            return self.status()
        if not (_allowed(a.get("browser_download_url", "")) or _allowed(a.get("url", ""))):
            self._set(status="error", error="Refusing to download from an unexpected host.")
            return self.status()
        if not self._sha256:
            self._set(status="error", error="Release has no checksum - not installing it automatically.")
            return self.status()
        self._clean_old(keep=a["name"])
        dest = updates_dir() / a["name"]
        part = dest.with_suffix(".part")
        self._set(status="downloading", progress=0.0)
        h = hashlib.sha256()
        total = int(a.get("size") or 0)
        done = 0
        try:
            r = self._get_asset(a, stream=True)
        except Exception as exc:
            self._set(status="error", error=f"Download failed: {exc}")
            return self.status()
        with r:
            with open(part, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if self._stop.is_set():
                        f.close()
                        part.unlink(missing_ok=True)
                        return self.status()
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if total:
                        self._set(progress=round(done / total, 3))
        if h.hexdigest() != self._sha256:
            part.unlink(missing_ok=True)
            self._set(status="error", error="Downloaded update failed checksum verification - discarded.")
            return self.status()
        os.replace(part, dest)
        self._set(status="ready", file=str(dest), progress=1.0)
        log.info("Update %s downloaded and verified", self.state["latest"])
        return self.status()

    def install(self, force: bool = False) -> dict:
        """Launch the silent installer and quit. Never while driving unless forced by the user."""
        if self.state["status"] != "ready" or not self.state["file"]:
            return self.status()
        if not can_self_install():
            self._set(error="Automatic install only works in the installed Windows app.")
            return self.status()
        if self.is_busy() and not force:
            self._set(error="Waiting until you're off track to install.")
            return self.status()
        path = self.state["file"]
        if self._sha256 and _sha256_file(Path(path)) != self._sha256:   # re-verify right before running
            self._set(status="error", error="Update file changed on disk - discarded.")
            Path(path).unlink(missing_ok=True)
            return self.status()
        log_file = updates_dir() / "install.log"
        # The installer waits for this app to exit (and stops it if it hangs) before it
        # replaces any files, then starts the new version.
        args = [path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                "/FORCECLOSEAPPLICATIONS", f"/LOG={log_file}"]
        try:
            self._pending_path().write_text(json.dumps({"from": self.current, "to": self.state["latest"],
                                                         "at": time.time()}), encoding="utf-8")
        except OSError:
            pass
        flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(args, creationflags=flags, close_fds=True)
        except OSError as exc:                   # e.g. blocked by antivirus
            self._pending_path().unlink(missing_ok=True)
            self._set(status="error", error=f"Couldn't start the installer: {exc}")
            return self.status()
        self._set(status="installing")
        log.info("Installing update %s - SimCoach will restart", self.state["latest"])
        if self.on_quit:
            threading.Timer(1.0, self.on_quit).start()
        return self.status()

    def _clean_old(self, keep: str) -> None:
        for p in updates_dir().glob("SimCoach-Setup-*"):
            if p.name != keep:
                p.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
