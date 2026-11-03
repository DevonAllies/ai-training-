"""Voice coach output.

Two outputs, both optional:

* native text-to-speech on Windows via pyttsx3 (uses the built-in SAPI voices),
  spoken on a single background thread
* a short rolling log of phrases that the browser overlay can speak with the
  browser's own speech synthesis (``/overlay?voice=1``) - handy for headsets
  plugged into a tablet, or when pyttsx3 is not installed

Memory/CPU safety: one worker thread, a bounded queue (old phrases are dropped
rather than piling up while you drive) and a fixed-size log.
"""

from __future__ import annotations

import collections
import itertools
import logging
import queue
import threading
import time

log = logging.getLogger(__name__)


class VoiceCoach:
    def __init__(self, native: bool = True, max_queue: int = 3, log_size: int = 20):
        self.native = native
        self._q: queue.Queue[str | None] = queue.Queue(maxsize=max_queue)
        self._thread: threading.Thread | None = None
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self.log: collections.deque[dict] = collections.deque(maxlen=log_size)
        self._recent: dict[str, float] = {}
        self.backend = "pending" if native else "browser"

    # --------------------------------------------------------------- public
    def say(self, text: str, min_repeat_s: float = 4.0) -> bool:
        """Queue a phrase. Returns False if it was suppressed as a repeat."""
        now = time.monotonic()
        with self._lock:
            last = self._recent.get(text)
            if last is not None and now - last < min_repeat_s:
                return False
            self._recent[text] = now
            if len(self._recent) > 64:                      # keep the dedupe map bounded
                cutoff = now - 60
                self._recent = {k: v for k, v in self._recent.items() if v > cutoff}
            self.log.append({"id": next(self._ids), "text": text})
        if self.native and self.backend != "unavailable":
            self._ensure_thread()
            try:
                self._q.put_nowait(text)
            except queue.Full:
                try:                                        # drop the oldest, keep the newest
                    self._q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._q.put_nowait(text)
                except queue.Full:
                    pass
        return True

    def recent(self, n: int = 5) -> list[dict]:
        with self._lock:
            return list(self.log)[-n:]

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            try:
                self._q.put_nowait(None)
            except queue.Full:
                pass
            self._thread.join(timeout=2)

    # --------------------------------------------------------------- worker
    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._worker, name="voice", daemon=True)
            self._thread.start()

    def _worker(self) -> None:
        try:
            import pyttsx3  # type: ignore
            engine = pyttsx3.init()
            engine.setProperty("rate", 185)
            self.backend = "native"
        except Exception as exc:  # not installed / no voices on this system
            log.info("Native voice unavailable (%s); browser voice still works.", exc)
            self.backend = "unavailable"
            return
        while True:
            text = self._q.get()
            if text is None:
                break
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                log.exception("text-to-speech failed")
        try:
            engine.stop()
        except Exception:
            pass


def spoken_seconds(x: float) -> str:
    """0.21 -> 'two tenths', 0.6 -> 'six tenths', 1.3 -> '1.3 seconds'."""
    x = abs(x)
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    if x < 0.95:
        t = max(1, round(x * 10))
        return f"{words[t]} tenth" + ("" if t == 1 else "s")
    return f"{x:.1f} seconds"
