import csv
import datetime as dt
import re
import statistics
from urllib.parse import urlencode

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseBadRequest, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from .models import Bus

ACTIVE_WINDOW_S = 120       # reported within 2 min  -> Active
ALERT_WINDOW_S = 30 * 60    # silent 2-30 min        -> Offline + alert (was running, went quiet)
                            # silent > 30 min        -> Offline, no alert (assumed parked)
LATENCY_SAMPLE = 50         # positions used for median latency
REFRESH_S = 10


def _ago(seconds):
    s = int(seconds)
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s ago"
    return f"{s // 3600}h {(s % 3600) // 60:02d}m ago"


@staff_member_required
def dashboard(request):
    now = timezone.now()
    rows, alerts = [], []
    for bus in Bus.objects.select_related("route").order_by("code"):
        recent = list(bus.positions.order_by("-received_at", "-id")[:LATENCY_SAMPLE])
        row = {"code": bus.code, "route": bus.route.name if bus.route else "-",
               "status": "offline", "label": "Offline", "last_seen": None, "age": "No data yet",
               "speed": None, "latency": None, "median_latency": None,
               "default_date": timezone.localdate(now).isoformat()}
        if recent:
            last = recent[0]
            age_s = (now - last.received_at).total_seconds()
            lats = [p.latency_seconds for p in recent if p.latency_seconds is not None]
            row.update(last_seen=last.received_at, age=_ago(age_s), speed=last.speed,
                       latency=last.latency_seconds,
                       median_latency=statistics.median(lats) if lats else None,
                       default_date=timezone.localdate(last.received_at).isoformat())
            if age_s <= ACTIVE_WINDOW_S:
                row.update(status="active", label="Active")
            elif age_s <= ALERT_WINDOW_S:
                row.update(status="silent")                    # still labelled Offline, styled amber
                alerts.append({"code": bus.code, "age": _ago(age_s)})
        rows.append(row)
    return render(request, "dashboard.html", {
        "rows": rows, "alerts": alerts, "now": now, "refresh_s": REFRESH_S,
        "active_window_min": ACTIVE_WINDOW_S // 60,
    })


@staff_member_required
def export_positions(request):
    """GET /api/export/positions/?bus=BUS-01&date=YYYY-MM-DD  (date optional, project time zone)."""
    code = request.GET.get("bus", "")
    if not code:
        return HttpResponseBadRequest("Missing ?bus=<code>")
    bus = get_object_or_404(Bus, code=code)
    qs = bus.positions.order_by("received_at", "id")

    day = request.GET.get("date")
    if day:
        try:
            d = dt.date.fromisoformat(day)
        except ValueError:
            return HttpResponseBadRequest("date must be YYYY-MM-DD")
        start = timezone.make_aware(dt.datetime.combine(d, dt.time.min))
        qs = qs.filter(received_at__gte=start, received_at__lt=start + dt.timedelta(days=1))

    def iso(v):                                               # always UTC, so replay_trip.py can parse it
        return v.astimezone(dt.timezone.utc).isoformat() if v else ""

    class Echo:
        def write(self, value):
            return value

    writer = csv.writer(Echo())

    def rows():
        yield writer.writerow(["fix_time", "received_at", "latency_s", "lat", "lng", "speed", "heading"])
        for p in qs.iterator(chunk_size=2000):
            yield writer.writerow([iso(p.fix_time), iso(p.received_at),
                                   "" if p.latency_seconds is None else p.latency_seconds,
                                   p.lat, p.lng, p.speed, p.heading])

    safe = re.sub(r"[^A-Za-z0-9_-]", "_", code)
    resp = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="trip_{safe}_{day or "all"}.csv"'
    return resp
