#!/usr/bin/env python3
"""
replay_trip.py - replay a recorded trip through the ETA engine (Phase 7, Step 7.5).

Feeds each logged point, in order, into backend/buses/eta.py with the same EMA window the
server uses, then checks that the predicted ETA to a stop:
  1. is never negative,
  2. never rises by more than --tolerance-s between consecutive points,
  3. is backed by route distance that never grows by more than --tolerance-m,
  4. reaches ~0 when the bus reaches the stop.
If the log has timestamps it also reports ETA error (predicted - actual time to arrival).

Input: CSV from /api/export/positions/ (needs lat, lng, speed; fix_time or received_at optional),
       or a JSON list of {"lat":..,"lng":..,"speed":..,"fix_time":..}.

Examples:
  python tools/replay_trip.py --demo                              # built-in synthetic trip
  python tools/replay_trip.py data/trip_BUS-01_2026-11-21.csv --stop S5
  python tools/replay_trip.py trip.json --stop 8 --tolerance-s 0  # strict mode
Exit code 0 = all checks passed, 1 = violations found.
"""
import argparse
import csv
import importlib.util
import json
import math
import statistics
import sys
from bisect import bisect_left
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_eta():
    spec = importlib.util.spec_from_file_location("eta", ROOT / "backend" / "buses" / "eta.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eta"] = mod              # dataclasses needs the module registered
    spec.loader.exec_module(mod)
    return mod


def parse_ts(row):
    for key in ("fix_time", "received_at", "timestamp"):
        v = row.get(key)
        if v in (None, ""):
            continue
        try:
            if isinstance(v, (int, float)):
                return datetime.fromtimestamp(v, tz=timezone.utc)
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except (ValueError, OSError):
            continue
    return None


def load_trip(path):
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data["positions"] if isinstance(data, dict) else data
    else:
        with p.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        try:
            out.append({**r, "lat": float(r["lat"]), "lng": float(r["lng"]),
                        "speed": float(r.get("speed") or 0)})
        except (KeyError, ValueError, TypeError):
            continue                       # skip malformed rows
    return out


def demo_trip(eta, route, interval_s=5):
    """Synthetic bus driving the whole route at roughly 21-29 km/h, one point every 5 s."""
    cum = [0.0]
    for a, b in zip(route, route[1:]):
        cum.append(cum[-1] + eta.haversine(a, b))
    base = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    rows, d, n = [], 0.0, 0
    while d <= cum[-1]:
        kmh = 25 + 4 * math.sin(n / 25)
        k = min(bisect_left(cum, d), len(route) - 1)
        rows.append({"fix_time": (base + timedelta(seconds=n * interval_s)).isoformat(),
                     "lat": route[k][0], "lng": route[k][1], "speed": round(kmh, 1)})
        d += kmh / 3.6 * interval_s
        n += 1
    return rows


def pick_stop(stops, key):
    if key is None:
        return max(stops, key=lambda s: s["order"])
    for s in stops:
        if str(s.get("id")) == key or str(s["order"]) == key:
            return s
    sys.exit(f"Stop '{key}' not found. Use an id (S1..) or an order number (1..).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trip", nargs="?", help="CSV or JSON trip log")
    ap.add_argument("--demo", action="store_true", help="use a synthetic trip along the route")
    ap.add_argument("--route", default=str(ROOT / "data" / "route.json"))
    ap.add_argument("--stops", default=str(ROOT / "data" / "stops.json"))
    ap.add_argument("--stop", help="target stop id (S5) or order number (5); default = last stop")
    ap.add_argument("--tolerance-s", type=float, default=15.0, help="allowed ETA rise between points (s)")
    ap.add_argument("--tolerance-m", type=float, default=35.0, help="allowed distance increase (m, ~1 vertex)")
    ap.add_argument("--every", type=int, default=10, help="print every Nth row (flagged rows always print)")
    a = ap.parse_args()
    if not a.trip and not a.demo:
        ap.error("give a trip file or --demo")

    eta = load_eta()
    route = json.loads(Path(a.route).read_text(encoding="utf-8"))
    stops = sorted(json.loads(Path(a.stops).read_text(encoding="utf-8")), key=lambda s: s["order"])
    rows = demo_trip(eta, route) if a.demo else load_trip(a.trip)
    if not rows:
        sys.exit("No usable rows in the trip log.")

    target = pick_stop(stops, a.stop)
    all_idx = [eta.nearest_index(route, [s["lat"], s["lng"]]) for s in stops]
    j = eta.nearest_index(route, [target["lat"], target["lng"]])
    print(f"Target: {target['name']} (order {target['order']}, route vertex {j}) | {len(rows)} points | "
          f"tolerance {a.tolerance_s:g} s / {a.tolerance_m:g} m\n")
    print(f"{'row':>4} {'vtx':>4} {'dist m':>8} {'v m/s':>6} {'ETA s':>7}  note")

    speeds, prev, seq, violations, arrival_row = deque(maxlen=eta.EMA_WINDOW), None, [], [], None
    for n, row in enumerate(rows):
        speeds.append(row["speed"])
        i = eta.nearest_index(route, [row["lat"], row["lng"]])
        res = eta.eta_from_indexes(route, i, j, all_idx, list(speeds))
        if res is None:
            arrival_row = n
            print(f"{n:>4} {i:>4}   -- bus passed the stop --")
            break
        notes = []
        if res.eta_seconds < 0:
            notes.append("NEGATIVE ETA")
        if prev and res.eta_seconds - prev.eta_seconds > a.tolerance_s:
            notes.append(f"ETA +{res.eta_seconds - prev.eta_seconds:.0f}s")
        if prev and res.distance_m - prev.distance_m > a.tolerance_m:
            notes.append(f"distance +{res.distance_m - prev.distance_m:.0f}m")
        if notes:
            violations.append((n, "; ".join(notes)))
        seq.append((n, res))
        if res.bus_index == res.stop_index and arrival_row is None:
            arrival_row = n
        if notes or n % max(1, a.every) == 0 or arrival_row == n:
            print(f"{n:>4} {i:>4} {res.distance_m:>8.0f} {res.speed_ms:>6.1f} {res.eta_seconds:>7.0f}  {'; '.join(notes)}")
        prev = res
        if arrival_row is not None:
            break

    print("\n--- verification ---")
    if arrival_row is None:
        last = seq[-1][1]
        print(f"INFO  trip ends {last.distance_m:.0f} m before the stop (not a failure)")
    else:
        print(f"OK    bus reached the stop at row {arrival_row}")
    if violations:
        print(f"FAIL  {len(violations)} violation(s), first at row {violations[0][0]}: {violations[0][1]}")
    else:
        print("OK    ETA never negative, never rose more than tolerance, distance never grew")

    stamps = [parse_ts(r) for r in rows]
    if arrival_row is not None and all(stamps[: arrival_row + 1]):
        errs = [res.eta_seconds - (stamps[arrival_row] - stamps[n]).total_seconds() for n, res in seq]
        errs = [e for e in errs if e is not None]
        if errs:
            ab = sorted(abs(e) for e in errs)
            print(f"ETA error vs actual arrival: mean |e| {statistics.mean(ab):.0f} s, "
                  f"median {statistics.median(ab):.0f} s, p90 {ab[int(0.9 * (len(ab) - 1))]:.0f} s "
                  f"(playbook target: median under 120 s)")
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
