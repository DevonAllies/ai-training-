"""Corner numbers and names per track.

iRacing and Garage 61 telemetry contain no turn numbers or names, so SimCoach
detects corners itself (C1, C2… = speed minima of the reference lap). A corner
map links those positions to the real turn number and name, e.g.::

    {"track": "Circuit des 24 Heures du Mans - 24 Heures du Mans",
     "corners": [{"pct": 0.071, "number": "1-2", "name": "Dunlop Chicane"}, ...]}

Maps are stored per track in %APPDATA%\\SimCoach\\corners\\ (one JSON file each),
created in the dashboard (Corners tab) and can be exported/imported to share.
Positions are fractions of the lap (0..1), so a map works with any car and any
reference lap on that track layout.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import app_dir

MATCH_WINDOW = 0.02     # a named corner matches a detected one within 2 % of the lap


def corners_dir() -> Path:
    d = app_dir() / "corners"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def track_key(track: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (track or "").lower()).strip("_")[:120] or "unknown"


def _clean(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries or []:
        try:
            pct = float(e.get("pct", e.get("apex_pct")))
        except (TypeError, ValueError):
            continue
        number = str(e.get("number") or "").strip()[:12]
        name = str(e.get("name") or "").strip()[:60]
        if 0 <= pct <= 1 and (number or name):
            out.append({"pct": round(pct, 4), "number": number, "name": name})
    return sorted(out, key=lambda e: e["pct"])


def save_map(track: str, entries: list[dict]) -> dict:
    data = {"track": track, "corners": _clean(entries)}
    path = corners_dir() / f"{track_key(track)}.json"
    if data["corners"]:
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return data


def list_maps() -> list[dict]:
    out = []
    for p in sorted(corners_dir().glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"track": d.get("track", p.stem), "corners": _clean(d.get("corners", []))})
        except (OSError, json.JSONDecodeError):
            continue
    return out


def find_map(track: str) -> dict | None:
    """Exact track match first, else the stored map whose track name is most similar
    (Garage 61 and iRacing spell track names slightly differently)."""
    if not track:
        return None
    exact = corners_dir() / f"{track_key(track)}.json"
    if exact.exists():
        try:
            d = json.loads(exact.read_text(encoding="utf-8"))
            return {"track": d.get("track", track), "corners": _clean(d.get("corners", []))}
        except (OSError, json.JSONDecodeError):
            pass
    want = _tokens(track)
    best, score = None, 0.0
    for m in list_maps():
        have = _tokens(m["track"])
        if not have or not want:
            continue
        s = len(want & have) / len(want | have)
        if s > score:
            best, score = m, s
    return best if score >= 0.6 else None


def labels(number: str, name: str, index: int) -> tuple[str, str, str]:
    """(short, title, spoken) labels for a corner."""
    if number:
        short = f"T{number}"
        title = f"T{number} · {name}" if name else short
        spoken = name or f"Turn {number.replace('-', ' to ')}"
    elif name:
        short = name if len(name) <= 10 else name[:9] + "…"
        title = name
        spoken = name
    else:
        short = title = f"C{index + 1}"
        spoken = f"C{index + 1}"
    return short, title, spoken


def apply_names(corners: list, track: str) -> list:
    """Label detected corners (in place) from the track's corner map. Returns them."""
    m = find_map(track)
    entries = list(m["corners"]) if m else []
    used: set[int] = set()
    for c in corners:
        best, best_d = None, MATCH_WINDOW
        for i, e in enumerate(entries):
            if i in used:
                continue
            d = abs(e["pct"] - c.pct)
            d = min(d, 1 - d)                       # wrap around the start/finish line
            if d <= best_d:
                best, best_d = i, d
        if best is not None:
            used.add(best)
            c.number, c.label_name = entries[best]["number"], entries[best]["name"]
        else:
            c.number, c.label_name = "", ""
        c.name, c.title, c.spoken = labels(c.number, c.label_name, c.index)
    return corners


def corner_dict(c) -> dict:
    return {"index": c.index, "name": c.name, "title": c.title, "spoken": c.spoken,
            "number": c.number, "label_name": c.label_name,
            "start": c.start, "apex": c.apex, "end": c.end, "pct": round(c.pct, 4)}
