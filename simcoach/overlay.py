"""Native in-game overlay window (Windows, tkinter - ships with Python).

A small, borderless, always-on-top, semi-transparent panel that sits on top of
iRacing. iRacing must run in *borderless windowed* or *windowed* mode
(Options -> Graphics -> uncheck "Fullscreen") for any overlay to show on top.

By default the overlay only appears while you are on track in a practice /
testing session ("practice" mode). It shows:

* live delta to your reference lap + whether you are losing time right now
* a BRAKE cue counting down to the reference braking point
* the last corner-phase feedback: brake point early/late, turn-in early/late,
  min speed too slow, throttle late - colour coded
* sector deltas for the current lap

Drag it with the left mouse button. Right-click for options. Mouse wheel resizes.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import font as tkfont

from .config import Config

log = logging.getLogger(__name__)

BG = "#0d1014"
FG = "#e6e9ee"
MUTED = "#8a94a3"
GOOD = "#33c27f"
BAD = "#ff5a5f"
WARN = "#f5b83d"
SEV = {"good": GOOD, "bad": BAD, "warn": WARN, "ok": FG}
KIND_LABEL = {"brake": "BRAKE", "turn_in": "TURN-IN", "min_speed": "MIN SPD", "throttle": "THROTTLE"}


def fmt_delta(d: float | None) -> str:
    if d is None:
        return "--.--"
    return ("+" if d >= 0 else "−") + f"{abs(d):.2f}"


def fmt_time(s: float | None) -> str:
    if not s or s <= 0:
        return "-:--.---"
    m, r = divmod(s, 60)
    return f"{int(m)}:{r:06.3f}"


class OverlayWindow:
    W, H = 380, 268

    def __init__(self, get_state, config: Config, on_quit=None, stop_event=None):
        self.stop_event = stop_event
        self.get_state = get_state
        self.config = config
        self.on_quit = on_quit
        self.root = tk.Tk()
        self.root.title("SimCoach overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", config.overlay_opacity)
        except tk.TclError:
            pass
        self.root.configure(bg=BG)
        fams = {f.lower() for f in tkfont.families(self.root)}
        self.sans = next((f for f in ("Segoe UI", "DejaVu Sans", "Helvetica", "Arial") if f.lower() in fams),
                         "Helvetica")
        self.mono = next((f for f in ("Consolas", "DejaVu Sans Mono", "Courier New", "Courier")
                          if f.lower() in fams), "Courier")
        self.scale = max(0.6, min(2.0, config.overlay_scale))
        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._apply_geometry()
        self._shown = True
        self._drag = (0, 0)

        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._do_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._save_pos())
        self.canvas.bind("<MouseWheel>", self._wheel)            # Windows
        self.canvas.bind("<Button-4>", lambda e: self._resize(0.1))   # X11
        self.canvas.bind("<Button-5>", lambda e: self._resize(-0.1))
        self.menu = tk.Menu(self.root, tearoff=0)
        self.mode_var = tk.StringVar(value=config.overlay_mode)
        for label, val in (("Show in practice only", "practice"), ("Always show", "always"),
                           ("Hide overlay", "off")):
            self.menu.add_radiobutton(label=label, variable=self.mode_var, value=val,
                                      command=self._set_mode)
        self.menu.add_separator()
        self.menu.add_command(label="Bigger", command=lambda: self._resize(0.1))
        self.menu.add_command(label="Smaller", command=lambda: self._resize(-0.1))
        self.menu.add_separator()
        self.menu.add_command(label="Quit SimCoach", command=self.quit)
        self.canvas.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))

    # ------------------------------------------------------------ window
    def _apply_geometry(self):
        w, h = int(self.W * self.scale), int(self.H * self.scale)
        self.root.geometry(f"{w}x{h}+{self.config.overlay_x}+{self.config.overlay_y}")

    def _start_drag(self, e):
        self._drag = (e.x, e.y)

    def _do_drag(self, e):
        x = self.root.winfo_x() + e.x - self._drag[0]
        y = self.root.winfo_y() + e.y - self._drag[1]
        self.root.geometry(f"+{x}+{y}")

    def _save_pos(self):
        self.config.overlay_x, self.config.overlay_y = self.root.winfo_x(), self.root.winfo_y()
        self._persist()

    def _wheel(self, e):
        self._resize(0.1 if e.delta > 0 else -0.1)

    def _resize(self, step):
        self.scale = round(max(0.6, min(2.0, self.scale + step)), 2)
        self.config.overlay_scale = self.scale
        self._apply_geometry()
        self._persist()

    def _set_mode(self):
        self.config.overlay_mode = self.mode_var.get()
        self._persist()

    def _persist(self):
        try:
            self.config.save()
        except OSError:
            log.warning("could not save overlay settings")

    def quit(self):
        if self.on_quit:
            self.on_quit()
        self.root.destroy()

    # ------------------------------------------------------------ drawing
    def run(self):
        self.root.after(100, self._tick)
        self.root.mainloop()

    def _tick(self):
        if self.stop_event is not None and self.stop_event.is_set():   # quit from tray
            self.root.destroy()
            return
        try:
            st = self.get_state()
            self.mode_var.set(self.config.overlay_mode)
            if st.get("visible"):
                if not self._shown:
                    self.root.deiconify()
                    self.root.attributes("-topmost", True)
                    self._shown = True
                self.draw(st)
            elif self._shown:
                self.root.withdraw()
                self._shown = False
        except Exception:
            log.exception("overlay update failed")
        self.root.after(50, self._tick)   # 20 Hz

    def draw(self, st: dict):
        c = self.canvas
        c.delete("all")
        k = self.scale
        W = self.W * k

        def font(size, bold=False, mono=False):
            fam = self.mono if mono else self.sans
            return (fam, int(size * k), "bold" if bold else "normal")

        # --- header: delta + trend
        d = st.get("delta")
        col = MUTED if d is None else (BAD if d > 0 else GOOD)
        c.create_text(12 * k, 8 * k, anchor="nw", text="DELTA", fill=MUTED, font=font(8))
        c.create_text(12 * k, 20 * k, anchor="nw", text=fmt_delta(d), fill=col, font=font(30, True, True))
        tr = st.get("trend")
        if tr is not None and abs(tr) > 0.03:
            c.create_text(12 * k, 66 * k, anchor="nw",
                          text=("LOSING " if tr > 0 else "GAINING ") + f"{abs(tr):.2f}s here",
                          fill=BAD if tr > 0 else GOOD, font=font(9, True))
        elif not st.get("has_reference"):
            c.create_text(12 * k, 66 * k, anchor="nw", text="No reference lap yet",
                          fill=MUTED, font=font(9))
        c.create_text(W - 12 * k, 8 * k, anchor="ne", text=(st.get("session_type") or "").upper(),
                      fill=MUTED, font=font(8))
        c.create_text(W - 12 * k, 24 * k, anchor="ne", text="PREDICTED", fill=MUTED, font=font(8))
        c.create_text(W - 12 * k, 36 * k, anchor="ne", text=fmt_time(st.get("predicted")),
                      fill=FG, font=font(14, True, True))
        c.create_text(W - 12 * k, 58 * k, anchor="ne", text="REF " + fmt_time(st.get("ref_lap_time")),
                      fill=MUTED, font=font(8, mono=True))
        fuel = st.get("fuel") or {}
        if fuel.get("laps") is not None:
            c.create_text(W - 12 * k, 72 * k, anchor="ne",
                          text=f"FUEL {fuel['laps']:.1f} laps" + ("  SAVE" if fuel.get("save_mode") else ""),
                          fill="#3ea6ff" if fuel.get("save_mode") else MUTED, font=font(8, True, True))

        # --- brake cue
        y = 88 * k
        cue = st.get("brake_cue")
        if cue and cue.get("kind") == "lift":
            m = cue["m"]
            lift_col = "#3ea6ff"
            if m <= 0:
                c.create_rectangle(12 * k, y, W - 12 * k, y + 26 * k, fill=lift_col, width=0)
                c.create_text(W / 2, y + 13 * k, text=f"LIFT  ({cue['corner']})", fill="#04121f",
                              font=font(13, True))
            else:
                frac = max(0.0, min(1.0, 1 - m / 250))
                c.create_rectangle(12 * k, y, W - 12 * k, y + 26 * k, outline="#2a313b", width=1)
                c.create_rectangle(12 * k, y, 12 * k + (W - 24 * k) * frac, y + 26 * k, fill="#173a5c", width=0)
                dist = f"{m} m" if st.get("units") == "metric" else f"{round(m * 3.281)} ft"
                c.create_text(W / 2, y + 13 * k, text=f"{cue['corner']}  lift in {dist}", fill=FG, font=font(11, True))
        elif cue:
            m = cue["m"]
            if m <= 0:
                c.create_rectangle(12 * k, y, W - 12 * k, y + 26 * k, fill=BAD, width=0)
                c.create_text(W / 2, y + 13 * k, text=f"BRAKE  ({cue['corner']})", fill="#fff",
                              font=font(13, True))
            else:
                frac = max(0.0, min(1.0, 1 - m / 250))
                c.create_rectangle(12 * k, y, W - 12 * k, y + 26 * k, outline="#2a313b", width=1)
                c.create_rectangle(12 * k, y, 12 * k + (W - 24 * k) * frac, y + 26 * k,
                                   fill="#5a2a2c", width=0)
                dist = f"{m} m" if st.get("units") == "metric" else f"{round(m * 3.281)} ft"
                c.create_text(W / 2, y + 13 * k, text=f"{cue['corner']}  brake in {dist}",
                              fill=FG, font=font(11, True))
        else:
            focus = st.get("focus") or {}
            if focus.get("active") and focus.get("name"):
                drill = (focus.get("drill") or "drill").upper()
                c.create_text(12 * k, y + 6 * k, anchor="w", text=f"{focus['name']} · {drill}",
                              fill=WARN, font=font(9, True))
                lt = focus.get("ladder_locked", focus.get("ladder_target"))
                if focus.get("kind") == "brake_ladder" and lt is not None:
                    c.create_text(12 * k, y + 20 * k, anchor="w", text=f"brake at {lt:+.0f} m",
                                  fill=FG, font=font(9, mono=True))
                for i in range(focus.get("needed", 3)):
                    x0 = 200 * k + i * 16 * k
                    c.create_oval(x0, y + 7 * k, x0 + 12 * k, y + 19 * k, width=0,
                                  fill=GOOD if i < focus.get("streak", 0) else "#262d36")
                if focus.get("last_loss") is not None:
                    c.create_text(W - 12 * k, y + 13 * k, anchor="e",
                                  text=f"last {fmt_delta(focus['last_loss'])}s", fill=MUTED, font=font(9, mono=True))
            else:
                c.create_text(12 * k, y + 13 * k, anchor="w",
                              text=f"Next: {st.get('next_corner') or '–'}", fill=MUTED, font=font(10))

        # --- corner phase feedback
        y = 122 * k
        events = st.get("events") or []
        if not events:
            c.create_text(12 * k, y + 4 * k, anchor="nw",
                          text="Corner feedback appears here as you drive.", fill=MUTED, font=font(9))
        for i, e in enumerate(reversed(events)):
            yy = y + i * 24 * k
            colr = SEV.get(e["severity"], FG)
            c.create_rectangle(12 * k, yy + 3 * k, 16 * k, yy + 19 * k, fill=colr, width=0)
            c.create_text(22 * k, yy + 11 * k, anchor="w", text=e["corner"], fill=MUTED,
                          font=font(10, True, True))
            c.create_text(62 * k, yy + 11 * k, anchor="w", text=e["text"],
                          fill=colr if i == 0 else FG, font=font(11 if i == 0 else 10, i == 0))

        # --- sectors
        n = st.get("sector_count") or 0
        if n:
            y = self.H * k - 30 * k
            gap = 4 * k
            w = (W - 24 * k - gap * (n - 1)) / n
            done = {s["sector"]: s for s in st.get("sectors") or []}
            for i in range(n):
                x0 = 12 * k + i * (w + gap)
                s = done.get(i + 1)
                if s and s.get("delta") is not None:
                    fill = GOOD if s["delta"] <= 0 else ("#7a2a2d" if s["delta"] < 0.3 else BAD)
                    txt = fmt_delta(s["delta"])
                elif s:
                    fill, txt = "#2a313b", f"{s['time']:.1f}"
                else:
                    fill, txt = "#1b2027", f"S{i + 1}"
                c.create_rectangle(x0, y, x0 + w, y + 22 * k, fill=fill, width=0)
                c.create_text(x0 + w / 2, y + 11 * k, text=txt, fill=FG,
                              font=font(8 if n > 5 else 9, True, True))


def run_overlay(get_state, config: Config, on_quit=None, stop_event=None) -> None:
    OverlayWindow(get_state, config, on_quit, stop_event).run()
