import secrets

from django.utils import timezone
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from .geo import is_near_route_bbox
from .models import Bus, Position, Route
from .serializers import IngestSerializer

OFF_ROUTE_MARGIN_KM = 5.0


def _authenticate_bus(request):
    """Return the Bus whose code == bus_id and whose key == X-API-Key, else None."""
    data = request.data if hasattr(request.data, "get") else {}
    code = data.get("bus_id")
    key = request.headers.get("X-API-Key", "")
    if not isinstance(code, str) or not key:
        return None
    bus = Bus.objects.select_related("route").filter(code=code).first()
    if bus and secrets.compare_digest(bus.api_key.encode(), key.encode()):
        return bus
    return None


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def ingest(request):
    bus = _authenticate_bus(request)
    if bus is None:
        return Response({"error": "unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    ser = IngestSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"error": "invalid_data", "details": ser.errors}, status=status.HTTP_400_BAD_REQUEST)
    d = ser.validated_data

    path = bus.route.path if bus.route else None
    if path and len(path) >= 2 and not is_near_route_bbox(d["lat"], d["lng"], path, OFF_ROUTE_MARGIN_KM):
        return Response(
            {"error": "off_route", "detail": f"Position is more than {OFF_ROUTE_MARGIN_KM:g} km from the route area."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    pos = Position.objects.create(
        bus=bus, lat=d["lat"], lng=d["lng"], speed=d["speed"], heading=d["heading"], fix_time=d["fix_time"]
    )
    return Response({"ok": True, "id": pos.pk}, status=status.HTTP_201_CREATED)


@never_cache
@api_view(["GET"])
def buses(request):
    now = timezone.now()
    out = []
    for bus in Bus.objects.order_by("code"):
        p = bus.positions.order_by("-received_at").first()   # uses the (bus, -received_at) index
        if p is None:
            continue
        out.append({
            "code": bus.code,
            "route": bus.route_id,
            "lat": p.lat,
            "lng": p.lng,
            "speed": p.speed,
            "heading": p.heading,
            "updated": p.received_at,
            "seconds_ago": max(0, int((now - p.received_at).total_seconds())),
            "fix_time": p.fix_time,
            "delay_seconds": p.delay_seconds,
        })
    return Response(out)


@api_view(["GET"])
def route_detail(request, pk):
    route = get_object_or_404(Route, pk=pk)
    stops = list(route.stops.order_by("order").values("id", "code", "name", "lat", "lng", "order"))
    return Response({"id": route.pk, "name": route.name, "path": route.path, "stops": stops})