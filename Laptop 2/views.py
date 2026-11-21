import logging
from datetime import datetime, timezone as dt_tz

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from . import eta as eta_engine
from .models import Bus, Position, Route, Stop

logger = logging.getLogger("buses.ingest")

STALE_AFTER_S = 120   # buses silent for longer are left out of stop ETAs


# ----------------------------------------------------------------------------- ingest
class PositionIn(serializers.ModelSerializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    speed = serializers.FloatField(min_value=0, max_value=120, default=0)   # km/h
    heading = serializers.FloatField(min_value=0, max_value=360, default=0)
    fix_time = serializers.DateTimeField(required=False, allow_null=True)

    class Meta:
        model = Position
        fields = ["lat", "lng", "speed", "heading", "fix_time"]


def _payload_with_fix_time(data):
    """
    Copy the request body and normalise the fix time. Accepts `fix_time` (or the
    API-contract name `timestamp`) as an ISO-8601 string or as Unix epoch seconds.
    """
    payload = {k: v for k, v in data.items()}
    raw = payload.pop("timestamp", None) if "fix_time" not in payload else payload.get("fix_time")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        raw = datetime.fromtimestamp(raw, tz=dt_tz.utc)      # may raise ValueError/OverflowError/OSError
    payload["fix_time"] = raw if raw not in ("", None) else None
    return payload


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def ingest(request):
    received_at = timezone.now()                              # one instant for storage AND latency
    key = request.headers.get("X-API-Key")
    bus = Bus.objects.filter(code=request.data.get("bus_id"), api_key=key).first()
    if not bus:
        return Response({"error": "unauthorized"}, status=401)

    try:
        payload = _payload_with_fix_time(request.data)
    except (ValueError, OverflowError, OSError):
        return Response({"error": "invalid fix_time"}, status=400)

    ser = PositionIn(data=payload)
    ser.is_valid(raise_exception=True)

    fix_time = ser.validated_data.get("fix_time")
    latency = round((received_at - fix_time).total_seconds(), 3) if fix_time else None
    ser.save(bus=bus, received_at=received_at, latency_seconds=latency)

    if latency is not None:
        log = logger.warning if latency < 0 else logger.info
        log("ingest bus=%s latency_s=%.3f%s", bus.code, latency,
            " (negative: unit clock ahead of server?)" if latency < 0 else "")
    return Response({"ok": True, "latency_seconds": latency}, status=201)


# ----------------------------------------------------------------------------- read APIs
@api_view(["GET"])
def buses(request):
    now = timezone.now()
    out = []
    for bus in Bus.objects.select_related("route"):
        p = bus.positions.order_by("-received_at", "-id").first()
        if p:
            out.append({
                "code": bus.code, "route": bus.route_id,
                "lat": p.lat, "lng": p.lng, "speed": p.speed, "heading": p.heading,
                "updated": p.received_at,
                "age_s": round((now - p.received_at).total_seconds(), 1),  # server-side: no client clock skew
                "latency_s": p.latency_seconds,
            })
    return Response(out)


@api_view(["GET"])
def route_detail(request, pk):
    r = get_object_or_404(Route, pk=pk)
    return Response({"id": r.id, "name": r.name, "path": r.path,
                     # `id` is needed by the web app to call /api/stops/<id>/etas/
                     "stops": list(r.stops.values("id", "name", "lat", "lng", "order"))})


@api_view(["GET"])
def stop_etas(request, pk):
    """Approaching buses for one stop, soonest first."""
    stop = get_object_or_404(Stop.objects.select_related("route"), pk=pk)
    route = stop.route
    path = route.path
    if len(path) < 2:
        return Response([])

    stop_idx = {s.pk: eta_engine.nearest_index(path, [s.lat, s.lng]) for s in route.stops.all()}
    target_idx = stop_idx[stop.pk]
    all_idx = list(stop_idx.values())
    now = timezone.now()

    results = []
    for bus in Bus.objects.filter(route=route):
        recent = list(bus.positions.order_by("-received_at", "-id")[:eta_engine.EMA_WINDOW])
        if not recent:
            continue
        latest = recent[0]
        age = (now - latest.received_at).total_seconds()
        if age > STALE_AFTER_S:
            continue                                          # silent bus: ETA would be fiction
        speeds = [p.speed for p in reversed(recent)]          # oldest first for the EMA
        bus_idx = eta_engine.nearest_index(path, [latest.lat, latest.lng])
        res = eta_engine.eta_from_indexes(path, bus_idx, target_idx, all_idx, speeds)
        if res is None:
            continue                                          # already passed this stop
        results.append({
            "bus_code": bus.code,
            "eta_seconds": round(res.eta_seconds),
            "eta_minutes": round(res.eta_seconds / 60, 1),
            "distance_m": round(res.distance_m),
            "status": res.status,
            "last_seen_age_s": round(age),
        })
    results.sort(key=lambda r: r["eta_seconds"])
    return Response(results)
