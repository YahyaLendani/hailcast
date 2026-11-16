"""Turn a stream of bus positions into finished trips.

Pure code with no I/O, so it can be tested against a recorded MTA response. A trip is one vehicle on
one MTA trip id. It ends when the vehicle starts another trip or stops reporting for IDLE_CLOSE.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
IDLE_CLOSE = timedelta(minutes=5)
MAX_KMH = 100.0      # a jump faster than this between two fixes is a GPS glitch; the fix is dropped
STOPPED_KMH = 3.0
MIN_FIXES = 8
MIN_DURATION_S = 5 * 60
MIN_DISTANCE_KM = 1.0


@dataclass
class Fix:
    vehicle: str
    trip_ref: str
    route: str
    destination: str
    at: datetime  # timezone-aware
    lat: float
    lon: float


@dataclass
class OpenTrip:
    first: Fix
    fixes: list = field(default_factory=list)


def haversine_m(a, b):
    r = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def simplify(points, tolerance=0.00003):
    """Douglas-Peucker with synchronised distance, as in scripts/build_porto_sample.py: a point is kept
    when it is far from where steady motion along the chord would put the bus at that point's time,
    so stops and changes of speed survive (0.00003 degrees is about 3 m)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        (y1, x1, t1), (y2, x2, t2) = points[lo], points[hi]
        span = (t2 - t1) or 1e-9
        worst, index = 0.0, 0
        for i in range(lo + 1, hi):
            y, x, t = points[i]
            f = (t - t1) / span
            dist = math.hypot(y - (y1 + (y2 - y1) * f), x - (x1 + (x2 - x1) * f))
            if dist > worst:
                worst, index = dist, i
        if worst > tolerance:
            keep[index] = True
            stack += [(lo, index), (index, hi)]
    return [p for p, k in zip(points, keep) if k]


def build_trip(trip: OpenTrip):
    """A finished trip as a dict ready to store, or None when it is too short or too sparse to show."""
    fixes = trip.fixes
    if len(fixes) < MIN_FIXES:
        return None
    t0 = fixes[0].at
    duration = (fixes[-1].at - t0).total_seconds()
    if duration < MIN_DURATION_S:
        return None
    raw = [(f.lat, f.lon, (f.at - t0).total_seconds()) for f in fixes]
    speeds, metres = [], 0.0
    stopped = 0.0
    for a, b in zip(raw, raw[1:]):
        dt = b[2] - a[2]
        m = haversine_m(a, b)
        kmh = m / dt * 3.6
        metres += m
        speeds.append([round(a[2], 1), round(kmh, 1)])
        if kmh < STOPPED_KMH:
            stopped += dt
    if metres / 1000 < MIN_DISTANCE_KM:
        return None
    first = trip.first
    start_local = t0.astimezone(NEW_YORK).replace(tzinfo=None)
    points = [[round(lat, 5), round(lon, 5), round(t, 1)] for lat, lon, t in simplify(raw)]
    return {
        # MTA trip ids repeat on every day with the same schedule, so the start time makes it unique.
        "id": f"{first.vehicle}-{start_local:%Y%m%d%H%M}-{first.trip_ref}"[:160],
        "route": first.route,
        "destination": first.destination,
        "vehicle": first.vehicle,
        "start": start_local,
        "end_utc": fixes[-1].at.astimezone(timezone.utc).replace(tzinfo=None),
        "duration_s": int(round(duration)),
        "distance_km": round(metres / 1000, 2),
        "avg_kmh": round(metres / duration * 3.6, 1),
        "max_kmh": max(s for _, s in speeds),
        "stopped_s": int(round(stopped)),
        "gps_fixes": len(fixes),
        "points": points,
        "speeds": speeds,
    }


class Stitcher:
    """Keeps the trips in progress. feed() takes one poll's fixes and returns the trips that finished."""

    def __init__(self):
        self.open: dict[str, OpenTrip] = {}  # by vehicle

    def feed(self, fixes, now: datetime):
        done = []
        for fix in fixes:
            trip = self.open.get(fix.vehicle)
            if trip and trip.first.trip_ref != fix.trip_ref:
                done.append(self.open.pop(fix.vehicle))
                trip = None
            if trip is None:
                self.open[fix.vehicle] = OpenTrip(first=fix, fixes=[fix])
                continue
            last = trip.fixes[-1]
            dt = (fix.at - last.at).total_seconds()
            if dt <= 0:
                continue  # the same report again, or an older one
            if haversine_m((last.lat, last.lon), (fix.lat, fix.lon)) / dt * 3.6 > MAX_KMH:
                continue
            trip.fixes.append(fix)
        for vehicle, trip in list(self.open.items()):
            if now - trip.fixes[-1].at > IDLE_CLOSE:
                done.append(self.open.pop(vehicle))
        return [t for t in (build_trip(t) for t in done) if t]
