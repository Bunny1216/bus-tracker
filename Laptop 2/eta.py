"""
eta.py - Smart ETA engine for the City Bus Tracker.

Pure Python, no Django imports, so the exact same code runs inside the API
(views.py) and inside the offline tool (tools/replay_trip.py).

Method (Build Guide section 7, extended):
  1. Snap the bus and the stop to their nearest route vertices (i and j).
  2. j < i  -> the bus already passed the stop -> None.
  3. distance = sum of Haversine segment lengths from vertex i to vertex j.
  4. speed    = EMA of the last 10 reported speeds (km/h -> m/s), floored at 3 m/s.
  5. ETA      = distance / speed + 20 s of dwell per intermediate stop.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Iterable, Optional, Sequence

EARTH_RADIUS_M = 6_371_000
MIN_SPEED_MS = 3.0        # floor so a stopped bus never gives an infinite ETA
DWELL_S = 20              # seconds added per intermediate stop
EMA_WINDOW = 10           # number of most recent Position rows used
EMA_ALPHA = 2 / (EMA_WINDOW + 1)   # standard EMA smoothing for a 10-sample span (~0.18); higher = reacts faster
AT_STOP_RADIUS_M = 30.0   # about one route vertex spacing

Point = Sequence[float]   # [lat, lng]


def haversine(a: Point, b: Point) -> float:
    """Great-circle distance in metres between two [lat, lng] points."""
    lat1, lng1, lat2, lng2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(h)))


def nearest_index(path: Sequence[Point], point: Point) -> int:
    """Index of the route vertex closest to `point` (linear scan, fine for ~500 points)."""
    if not path:
        raise ValueError("route path is empty")
    return min(range(len(path)), key=lambda k: haversine(path[k], point))


def distance_along(path: Sequence[Point], i: int, j: int) -> float:
    """Route distance in metres from vertex i to vertex j (i <= j)."""
    return sum(haversine(path[k], path[k + 1]) for k in range(i, j))


def ema_speed_ms(speeds_kmh: Sequence[Optional[float]],
                 alpha: float = EMA_ALPHA, window: int = EMA_WINDOW) -> float:
    """
    Exponential moving average of speeds given OLDEST FIRST, in km/h.
    Only the last `window` samples are used. Returns m/s, never below MIN_SPEED_MS.
    """
    vals = [max(0.0, float(s)) / 3.6 for s in list(speeds_kmh)[-window:] if s is not None]
    if not vals:
        return MIN_SPEED_MS
    ema = vals[0]
    for v in vals[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return max(ema, MIN_SPEED_MS)


@dataclass(frozen=True)
class EtaResult:
    eta_seconds: float
    distance_m: float
    stops_between: int
    speed_ms: float
    bus_index: int
    stop_index: int

    @property
    def status(self) -> str:
        return "At Stop" if self.distance_m <= AT_STOP_RADIUS_M else "Approaching"


def eta_from_indexes(path: Sequence[Point], bus_idx: int, stop_idx: int,
                     all_stop_indexes: Iterable[int],
                     speeds_kmh: Sequence[Optional[float]]) -> Optional[EtaResult]:
    """
    Core calculation on pre-snapped indexes (cheap to call repeatedly).
    `all_stop_indexes` = route vertex index of EVERY stop on the route; stops strictly
    between the bus and the target each add DWELL_S.
    """
    if stop_idx < bus_idx:
        return None                                   # bus already passed this stop
    dist = distance_along(path, bus_idx, stop_idx)
    between = sum(1 for k in all_stop_indexes if bus_idx < k < stop_idx)
    speed = ema_speed_ms(speeds_kmh)
    return EtaResult(dist / speed + DWELL_S * between, dist, between, speed, bus_idx, stop_idx)


def eta_to_stop(path: Sequence[Point], bus_pt: Point, stop_pt: Point,
                speeds_kmh: Sequence[Optional[float]],
                stop_points: Iterable[Point] = ()) -> Optional[EtaResult]:
    """Convenience wrapper that does the snapping too."""
    i = nearest_index(path, bus_pt)
    j = nearest_index(path, stop_pt)
    ks = [nearest_index(path, p) for p in stop_points]
    return eta_from_indexes(path, i, j, ks, speeds_kmh)
