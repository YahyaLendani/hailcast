"""Precompute a likely road route between every pair of sample zones.

Uses the public OSRM demo server (OpenStreetMap data) once, at build time, so the running app
never depends on it. Output: backend/app/data/zone_routes.json, keyed "pickup-dropoff", each with
the route as [lat, lon] points plus OSRM's road distance (miles) and driving time (minutes).

Run from the repository root:  python backend/scripts/build_zone_routes.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.core.zones import ZONES  # noqa: E402

OUT = BACKEND / "app" / "data" / "zone_routes.json"
URL = "https://router.project-osrm.org/route/v1/driving/{a};{b}?overview=full&geometries=geojson"


def simplify(points, tolerance=0.00008):
    """Douglas-Peucker in degrees (0.00008 is roughly 8 metres): keeps the shape, drops most points."""
    if len(points) < 3:
        return points
    (y1, x1), (y2, x2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
    worst, index = 0.0, 0
    for i in range(1, len(points) - 1):
        y, x = points[i]
        dist = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
        if dist > worst:
            worst, index = dist, i
    if worst <= tolerance:
        return [points[0], points[-1]]
    return simplify(points[:index + 1], tolerance)[:-1] + simplify(points[index:], tolerance)


def fetch(src, dst):
    a = f"{src[2]},{src[1]}"
    b = f"{dst[2]},{dst[1]}"
    req = urllib.request.Request(URL.format(a=a, b=b), headers={"User-Agent": "hailcast-route-builder"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    route = data["routes"][0]
    # GeoJSON is [lon, lat]; Leaflet wants [lat, lon]. Five decimals is about one metre.
    points = [[round(lat, 5), round(lon, 5)] for lon, lat in route["geometry"]["coordinates"]]
    return {
        "points": simplify(points),
        "road_miles": round(route["distance"] / 1609.344, 2),
        "drive_minutes": round(route["duration"] / 60, 1),
    }


def main():
    routes = json.loads(OUT.read_text()) if OUT.exists() else {}
    for route in routes.values():
        route["points"] = simplify(route["points"])
    for src_id, src in ZONES.items():
        for dst_id, dst in ZONES.items():
            key = f"{src_id}-{dst_id}"
            if src_id == dst_id or key in routes:
                continue
            for attempt in range(3):
                try:
                    routes[key] = fetch(src, dst)
                    break
                except Exception as exc:  # network hiccup: wait and retry
                    print(f"{key}: {exc}; retrying")
                    time.sleep(3 * (attempt + 1))
            time.sleep(1.1)  # the demo server asks for at most one request per second
            print(key, routes.get(key, {}).get("road_miles"))
            OUT.write_text(json.dumps(routes, separators=(",", ":")))
    OUT.write_text(json.dumps(routes, separators=(",", ":")))
    print(f"{len(routes)} routes written to {OUT}")


if __name__ == "__main__":
    main()
