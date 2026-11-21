#!/usr/bin/env python3
"""
fake_bus.py - posts a simulated bus position to /api/ingest/ every few seconds.

Walks data/route.json forward to Abdullahpur, then back, forever. Speed and heading are
derived from the distance/bearing to the next point (30 m / 3 s = 36 km/h).

    pip install requests
    python tools/fake_bus.py --key YOUR_KEY
    python tools/fake_bus.py --url https://your-app.onrender.com --key YOUR_KEY
"""
import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROUTE_FILE = Path(__file__).resolve().parent.parent / "data" / "route.json"
EARTH_R = 6371000.0


def haversine_m(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlng = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def bearing_deg(a, b):
    p1, p2, dlng = math.radians(a[0]), math.radians(b[0]), math.radians(b[1] - a[1])
    y = math.sin(dlng) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlng)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_args():
    p = argparse.ArgumentParser(description="Simulated bus for the City Bus Tracker.")
    p.add_argument("--url", default=os.environ.get("TRACKER_URL", "http://127.0.0.1:8000"))
    p.add_argument("--key", default=os.environ.get("BUS_API_KEY"), help="Bus API key (or set BUS_API_KEY).")
    p.add_argument("--bus-id", default="BUS-01")
    p.add_argument("--interval", type=float, default=3.0, help="Seconds between posts.")
    p.add_argument("--route", type=Path, default=ROUTE_FILE)
    return p.parse_args()


def main():
    args = parse_args()
    if not args.key:
        sys.exit("Missing API key: pass --key or set BUS_API_KEY (run `python manage.py seed_data --show-key`).")

    points = json.loads(args.route.read_text(encoding="utf-8"))
    if len(points) < 2:
        sys.exit("route.json needs at least 2 points.")
    sequence = points + points[-2:0:-1]          # out and back, no duplicated end points
    endpoint = args.url.rstrip("/") + "/api/ingest/"

    session = requests.Session()
    session.headers.update({"X-API-Key": args.key})
    print(f"Posting {args.bus_id} to {endpoint} every {args.interval:g}s ({len(sequence)} points per lap). Ctrl+C to stop.")

    i = 0
    try:
        while True:
            cur, nxt = sequence[i], sequence[(i + 1) % len(sequence)]
            speed = min(haversine_m(cur, nxt) / args.interval * 3.6, 120.0)   # server rejects > 120
            body = {
                "bus_id": args.bus_id,
                "lat": cur[0], "lng": cur[1],
                "speed": round(speed, 1),
                "heading": round(bearing_deg(cur, nxt), 1),
                "fix_time": utc_now_iso(),
            }
            stamp = time.strftime("%H:%M:%S")
            try:
                r = session.post(endpoint, json=body, timeout=10)
            except requests.RequestException as exc:
                print(f"[{stamp}] network error: {exc}")
            else:
                if r.status_code == 201:
                    print(f"[{stamp}] 201 point {i + 1}/{len(sequence)}  {cur[0]:.5f},{cur[1]:.5f}  {body['speed']} km/h")
                elif r.status_code == 401:
                    sys.exit("401 Unauthorized: wrong API key or bus id.")
                else:
                    print(f"[{stamp}] {r.status_code} {r.text[:200]}")
            i = (i + 1) % len(sequence)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()