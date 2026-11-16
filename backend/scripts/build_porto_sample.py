"""Build the real-GPS trip sample from the Porto taxi dataset.

Source: "Taxi Service Trajectory - Prediction Challenge, ECML PKDD 2015", UCI Machine Learning
Repository, https://doi.org/10.24432/C55W25 (CC BY 4.0). Each trip there is a GPS point every
15 seconds from pickup to drop-off.

This script picks a varied sample of clean trips, snaps each one to the road network with the OSRM
map-matching service (OpenStreetMap data) and keeps the real timing: every 15-second leg of the trip
keeps its start and end time, so a cab animated along the result moves at the recorded speed. A 15-second
leg that cannot be matched is drawn as a straight line between its two fixes.

Usage (from the repository root; the zip is the UCI download, about 530 MB):
    python backend/scripts/build_porto_sample.py path/to/porto.zip
Output: backend/app/data/porto_trips.json
"""
import csv
import io
import json
import math
import random
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "porto_trips.json"
OSRM = "https://router.project-osrm.org/match/v1/driving/{coords}?timestamps={ts}&radiuses={rad}" \
       "&overview=full&geometries=geojson&annotations=distance&gaps=ignore"
STEP_SECONDS = 15
SAMPLE_SIZE = 120
SCAN_ROWS = 60_000
MAX_TRACE = 10  # the OSRM demo server matches at most 10 fixes per request
CALL_TYPES = {"A": "Booked through the dispatch centre", "B": "Picked up at a taxi rank", "C": "Hailed on the street"}
BBOX = (41.10, 41.25, -8.72, -8.52)  # Porto and its edges: lat min, lat max, lon min, lon max


def haversine_m(a, b):
    """Distance in metres between two (lat, lon) points."""
    r = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def lisbon_time(unix):
    """Porto local time. Portugal is UTC+1 from the last Sunday of March to the last Sunday of October."""
    utc = datetime.fromtimestamp(unix, tz=timezone.utc)

    def last_sunday(year, month):
        d = datetime(year, month, 31, 1, tzinfo=timezone.utc)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    summer = last_sunday(utc.year, 3) <= utc < last_sunday(utc.year, 10)
    return (utc + timedelta(hours=1 if summer else 0)).replace(tzinfo=None)


def read_rows(path):
    outer = zipfile.ZipFile(path)
    inner = zipfile.ZipFile(outer.open("train.csv.zip"))
    with inner.open("train.csv") as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))


def candidates(path):
    """Clean trips of 6 to 25 minutes inside Porto, without GPS jumps."""
    for n, row in enumerate(read_rows(path)):
        if n >= SCAN_ROWS:
            break
        if row["MISSING_DATA"] != "False":
            continue
        pts = [(lat, lon) for lon, lat in json.loads(row["POLYLINE"])]
        if not 24 <= len(pts) <= 100:
            continue
        if not all(BBOX[0] <= la <= BBOX[1] and BBOX[2] <= lo <= BBOX[3] for la, lo in pts):
            continue
        legs = [haversine_m(a, b) for a, b in zip(pts, pts[1:])]
        if max(legs) / STEP_SECONDS * 3.6 > 110 or sum(legs) < 2000:
            continue
        yield {"trip_id": row["TRIP_ID"], "call_type": row["CALL_TYPE"], "start": int(row["TIMESTAMP"]), "gps": pts}


def pick_sample(path):
    """A spread of hours and trip lengths rather than the first rows of the file."""
    rng = random.Random(7)
    pool = list(candidates(path))
    buckets = {}
    for trip in pool:
        hour = lisbon_time(trip["start"]).hour
        size = min(len(trip["gps"]) // 25, 3)
        buckets.setdefault((hour // 3, size), []).append(trip)
    for trips in buckets.values():
        rng.shuffle(trips)
    picked, keys = [], sorted(buckets)
    while len(picked) < SAMPLE_SIZE and any(buckets[k] for k in keys):
        for k in keys:
            if buckets[k] and len(picked) < SAMPLE_SIZE:
                picked.append(buckets[k].pop())
    print(f"{len(pool)} clean candidates, {len(picked)} picked")
    return picked


def simplify(points, tolerance=0.00003):
    """Douglas-Peucker with synchronised distance, so timing survives (0.00003 deg is about 3 m).

    Each point is compared with where a cab moving steadily along the chord would be at that point's
    time. A stop or a change of speed therefore counts as a deviation and is kept.
    """
    if len(points) < 3:
        return points
    (y1, x1, t1), (y2, x2, t2) = points[0], points[-1]
    span = (t2 - t1) or 1e-9
    worst, index = 0.0, 0
    for i in range(1, len(points) - 1):
        y, x, t = points[i]
        f = (t - t1) / span
        dist = math.hypot(y - (y1 + (y2 - y1) * f), x - (x1 + (x2 - x1) * f))
        if dist > worst:
            worst, index = dist, i
    if worst <= tolerance:
        return [points[0], points[-1]]
    return simplify(points[:index + 1], tolerance)[:-1] + simplify(points[index:], tolerance)


def match_chunk(gps):
    """Map-match up to MAX_TRACE fixes. Returns one entry per leg: matched geometry or None."""
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in gps)
    ts = ";".join(str(i * STEP_SECONDS) for i in range(len(gps)))
    rad = ";".join("30" for _ in gps)
    req = urllib.request.Request(OSRM.format(coords=coords, ts=ts, rad=rad),
                                 headers={"User-Agent": "hailcast-sample-builder"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 400:  # NoMatch and similar: nothing to snap in this chunk
            return [None] * (len(gps) - 1), [None] * len(gps)
        raise
    tps = data.get("tracepoints") or [None] * len(gps)
    snapped = [(tp["location"][1], tp["location"][0]) if tp else None for tp in tps]
    # Split each matching's line into its legs (one leg per pair of consecutive matched fixes).
    leg_shapes = {}
    for mi, m in enumerate(data.get("matchings", [])):
        line = [(lat, lon) for lon, lat in m["geometry"]["coordinates"]]
        start = 0
        for li, leg in enumerate(m["legs"]):
            n = len(leg["annotation"]["distance"])
            leg_shapes[(mi, li)] = {"points": line[start:start + n + 1], "metres": leg["distance"]}
            start += n
    legs = []
    for k in range(len(gps) - 1):
        a, b = tps[k], tps[k + 1]
        if a and b and a["matchings_index"] == b["matchings_index"] and b["waypoint_index"] == a["waypoint_index"] + 1:
            legs.append(leg_shapes.get((a["matchings_index"], a["waypoint_index"])))
        else:
            legs.append(None)
    return legs, snapped


def match(gps):
    """Match a whole trip in overlapping chunks. Returns (legs, snapped fixes)."""
    legs, snapped = [], [None] * len(gps)
    start = 0
    while start < len(gps) - 1:
        end = min(start + MAX_TRACE, len(gps))
        for attempt in range(3):
            try:
                chunk_legs, chunk_snapped = match_chunk(gps[start:end])
                break
            except Exception as exc:  # network hiccup: wait and retry
                print(f"  chunk {start}: {exc}; retrying")
                time.sleep(3 * (attempt + 1))
        else:
            chunk_legs, chunk_snapped = [None] * (end - start - 1), [None] * (end - start)
        legs.extend(chunk_legs)
        for i, pt in enumerate(chunk_snapped):
            if pt and snapped[start + i] is None:
                snapped[start + i] = pt
        time.sleep(1.1)  # the OSRM demo server asks for at most one request per second
        start = end - 1
    return legs, snapped


def timed_path(gps, legs, snapped):
    """(lat, lon, seconds) points plus (seconds, km/h) for each 15-second leg.

    A leg the matcher could not snap is a straight line between the two fixes (snapped where possible).
    """
    points, speeds = [], []
    for i in range(len(gps) - 1):
        t0 = i * STEP_SECONDS
        straight = haversine_m(gps[i], gps[i + 1])
        leg = legs[i]
        # A matched leg much longer than the straight line, or too fast for 15 seconds, is a wrong
        # match (a detour or loop the taxi could not have driven); fall back to the straight line.
        if leg and (leg["metres"] > 1.5 * straight + 50 or leg["metres"] / STEP_SECONDS * 3.6 > 110):
            legs[i] = leg = None
        if leg:
            seg, metres = leg["points"], leg["metres"]
        else:
            a, b = snapped[i] or gps[i], snapped[i + 1] or gps[i + 1]
            seg, metres = [a, b], haversine_m(a, b)
        if len(seg) < 2:
            seg = [seg[0], seg[0]]  # the cab did not move during this leg
        cum = [0.0]
        for a, b in zip(seg, seg[1:]):
            cum.append(cum[-1] + haversine_m(a, b))
        total = cum[-1] or 1.0
        for j, (lat, lon) in enumerate(seg):
            if points and j == 0:
                continue  # shared with the previous leg's last point
            share = cum[j] / total if cum[-1] else j / (len(seg) - 1)
            points.append((round(lat, 5), round(lon, 5), round(t0 + STEP_SECONDS * share, 1)))
        speeds.append((t0, round(metres / STEP_SECONDS * 3.6, 1)))
    return points, speeds


def build(path):
    trips = []
    for k, trip in enumerate(pick_sample(path), 1):
        legs, snapped = match(trip["gps"])
        points, speeds = timed_path(trip["gps"], legs, snapped)
        share = sum(leg is not None for leg in legs) / len(legs)
        points = [list(p) for p in simplify(points)]
        duration = (len(trip["gps"]) - 1) * STEP_SECONDS
        metres = sum(haversine_m(a[:2], b[:2]) for a, b in zip(points, points[1:]))
        moving = [s for _, s in speeds]
        start = lisbon_time(trip["start"])
        trips.append({
            "id": trip["trip_id"],
            "start": start.isoformat(),
            "call_type": CALL_TYPES.get(trip["call_type"], trip["call_type"]),
            "snapped_to_roads": round(share, 2),
            "duration_s": duration,
            "distance_km": round(metres / 1000, 2),
            "avg_kmh": round(metres / duration * 3.6, 1),
            "max_kmh": max(moving),
            "stopped_s": STEP_SECONDS * sum(1 for s in moving if s < 3),
            "gps_fixes": len(trip["gps"]),
            "points": points,
            "speeds": [list(s) for s in speeds],
        })
        print(f"{k:3d} {trip['trip_id']} {share:.0%} of legs snapped, {len(points)} pts", flush=True)
    trips.sort(key=lambda t: t["start"])
    OUT.write_text(json.dumps({
        "source": {
            "name": "Taxi Service Trajectory - Prediction Challenge, ECML PKDD 2015",
            "publisher": "UCI Machine Learning Repository",
            "url": "https://doi.org/10.24432/C55W25",
            "licence": "CC BY 4.0",
            "city": "Porto, Portugal",
            "note": "Real GPS fixes every 15 seconds, snapped to OpenStreetMap roads with OSRM where it could "
                    "match them; snapped_to_roads is the share of 15-second legs matched. "
                    "Times are Porto local time.",
        },
        "trips": trips,
    }, separators=(",", ":")), encoding="utf-8")
    share = sum(t["snapped_to_roads"] for t in trips) / len(trips)
    print(f"{len(trips)} trips written to {OUT}; {share:.0%} of legs snapped to roads")


if __name__ == "__main__":
    build(sys.argv[1])
