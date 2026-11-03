"""Minimal Garage 61 REST API client.

Docs: https://garage61.net/developer
Create a personal access token in Garage 61 under Settings -> Developer.
The token needs the ``driving_data`` permission to read laps and telemetry.

Privacy note from Garage 61: lap searches only return laps driven by
yourself, your teammates and drivers you follow - there is no global search.
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

BASE_URL = "https://garage61.net/api/v1/"


class Garage61Error(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Garage61Client:
    def __init__(self, token: str, base_url: str = BASE_URL, timeout: float = 20.0):
        self.token = token
        self.base_url = base_url
        self.timeout = timeout
        self._session = requests.Session()
        self._cache: dict[str, tuple[float, Any]] = {}

    # ------------------------------------------------------------------ http
    def _get(self, endpoint: str, params: dict | None = None, raw: bool = False):
        if not self.token:
            raise Garage61Error("No Garage 61 token configured. Add one in Settings.", 401)
        clean = {}
        for k, v in (params or {}).items():
            if v is None or v == "" or v == []:
                continue
            if isinstance(v, (list, tuple)):
                v = ",".join(str(x) for x in v)
            elif isinstance(v, bool):
                v = "true" if v else "false"
            clean[k] = v
        try:
            r = self._session.get(
                self.base_url + endpoint,
                params=clean,
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise Garage61Error(f"Could not reach Garage 61: {exc}") from exc
        if r.status_code == 401:
            raise Garage61Error("Garage 61 rejected the token (401). Check it in Settings.", 401)
        if r.status_code == 403:
            raise Garage61Error(
                "Garage 61 denied access (403). Telemetry of other drivers needs a Pro plan "
                "and the token needs the driving_data permission.", 403)
        if r.status_code == 429:
            raise Garage61Error("Garage 61 rate limit reached, try again shortly.", 429)
        if not r.ok:
            raise Garage61Error(f"Garage 61 error {r.status_code}: {r.text[:200]}", r.status_code)
        return r.text if raw else r.json()

    def _cached(self, key: str, ttl: float, fn):
        hit = self._cache.get(key)
        now = time.time()
        if hit and now - hit[0] < ttl:
            return hit[1]
        val = fn()
        self._cache[key] = (now, val)
        return val

    # ------------------------------------------------------------- endpoints
    def me(self) -> dict:
        return self._cached("me", 300, lambda: self._get("me"))

    def teams(self) -> list[dict]:
        return self._cached("teams", 600, lambda: _items(self._get("teams")))

    def cars(self) -> list[dict]:
        return self._cached("cars", 3600, lambda: _items(self._get("cars")))

    def tracks(self) -> list[dict]:
        return self._cached("tracks", 3600, lambda: _items(self._get("tracks")))

    def find_laps(
        self,
        cars: list[int] | None = None,
        tracks: list[int] | None = None,
        drivers: list[str] | None = None,
        teams: list[str] | None = None,
        extra_drivers: list[str] | None = None,
        group: str = "driver",
        telemetry_required: bool = True,
        age: int | None = None,
        limit: int = 200,
        **extra,
    ) -> list[dict]:
        """Search laps. ``group='driver'`` returns each driver's personal best.

        If neither drivers, teams nor extra_drivers is given, Garage 61 returns
        yourself and all of your teammates.
        """
        params = {
            "cars": cars,
            "tracks": tracks,
            "drivers": drivers,
            "teams": teams,
            "extraDrivers": extra_drivers,
            "group": group,
            "seeTelemetry": telemetry_required or None,
            "age": age,
            "limit": limit,
        }
        params.update(extra)
        return _items(self._get("laps", params))

    def get_lap(self, lap_id: str) -> dict:
        return self._cached(f"lap:{lap_id}", 3600, lambda: self._get(f"laps/{lap_id}"))

    def lap_csv(self, lap_id: str) -> str:
        return self._get(f"laps/{lap_id}/csv", raw=True)

    # --------------------------------------------------------------- helpers
    def match_track(self, display_name: str, config_name: str = "") -> dict | None:
        """Best-effort match of an iRacing track name to a Garage 61 track."""
        return best_match(self.tracks(), f"{display_name} {config_name}",
                          lambda t: f"{t.get('name', '')} {t.get('variant', '')}")

    def match_car(self, screen_name: str) -> dict | None:
        return best_match(self.cars(), screen_name, lambda c: c.get("name", ""))


def _items(payload) -> list:
    if isinstance(payload, dict):
        return payload.get("items", [])
    return payload or []


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def best_match(items: list[dict], target: str, key) -> dict | None:
    """Pick the item whose name shares the most words with ``target`` (Jaccard)."""
    want = _tokens(target)
    if not want:
        return None
    best, best_score = None, 0.0
    for it in items:
        have = _tokens(key(it))
        if not have:
            continue
        score = len(want & have) / len(want | have)
        if score > best_score:
            best, best_score = it, score
    return best if best_score >= 0.34 else None


def describe_lap(lap: dict) -> dict:
    """Flatten a Garage 61 lap record into the fields the UI needs.

    The API returns nested objects; we read them defensively so small schema
    changes do not break the app.
    """
    drv = lap.get("driver") or {}
    name = " ".join(x for x in (drv.get("firstName"), drv.get("lastName")) if x) or drv.get("name") \
        or drv.get("slug") or "Unknown"
    car = lap.get("car") or {}
    track = lap.get("track") or {}
    return {
        "id": lap.get("id"),
        "driver": name,
        "driver_slug": drv.get("slug"),
        "car": car.get("name"),
        "car_id": car.get("id"),
        "track": " - ".join(x for x in (track.get("name"), track.get("variant")) if x),
        "track_id": track.get("id"),
        "lap_time": lap.get("lapTime"),
        "date": lap.get("startTime") or lap.get("date"),
        "session_type": lap.get("sessionType"),
        "can_view_telemetry": lap.get("canViewTelemetry", True),
        "is_me": bool(lap.get("isMe") or drv.get("isMe")),
    }
