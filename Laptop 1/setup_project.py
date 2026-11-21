#!/usr/bin/env python3
"""
setup_project.py - writes the whole City Bus Tracker backend + live frontend into the project folder.

Usage (from E:\\bus-tracker, or pass the folder as an argument):
    python setup_project.py
    python setup_project.py E:\\bus-tracker

Never touches: data/route.json, data/stops.json, tools/gpx_converter.html, web/index.html.
Standard library only. Every file is UTF-8 with LF line endings.
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent

# relative path -> (content, overwrite?)
FILES = {}


def add(rel, text, overwrite=True):
    text = text.lstrip("\n")
    if text and not text.endswith("\n"):
        text += "\n"
    FILES[rel] = (text, overwrite)


# --------------------------------------------------------------------------- root files
add("requirements.txt", r'''
Django>=5.2,<6.0
djangorestframework>=3.15
gunicorn>=22.0
whitenoise>=6.7
psycopg2-binary>=2.9
dj-database-url>=2.2
django-cors-headers>=4.4
''')

add("Procfile", r'''
web: gunicorn --chdir backend tracker.wsgi --bind 0.0.0.0:$PORT --log-file -
''')

add("build.sh", r'''
#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
cd backend
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py seed_data                 # idempotent, but resets route/stops from data/ - remove after first deploy
python manage.py createsuperuser --noinput || true   # needs DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD
''')

add(".gitignore", r'''
venv/
__pycache__/
*.pyc
db.sqlite3
.env
backend/staticfiles/
''')

# --------------------------------------------------------------------------- backend scaffolding (only if missing)
add("backend/manage.py", r'''
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tracker.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Is it installed and is your virtual environment activated?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
''', overwrite=False)

add("backend/tracker/__init__.py", "", overwrite=False)

add("backend/tracker/wsgi.py", r'''
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tracker.settings")
application = get_wsgi_application()
''', overwrite=False)

add("backend/buses/__init__.py", "", overwrite=False)
add("backend/buses/migrations/__init__.py", "", overwrite=False)
add("backend/buses/management/__init__.py", "", overwrite=False)
add("backend/buses/management/commands/__init__.py", "", overwrite=False)

add("backend/buses/apps.py", r'''
from django.apps import AppConfig


class BusesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "buses"
''', overwrite=False)

# --------------------------------------------------------------------------- env files
ENV_TEXT = r'''
DEBUG=1
SECRET_KEY=dev-only-change-me
ALLOWED_HOSTS=localhost,127.0.0.1
'''
add("backend/.env.example", ENV_TEXT)
add("backend/.env", ENV_TEXT, overwrite=False)   # never clobber a .env you already edited

# --------------------------------------------------------------------------- settings / urls
add("backend/tracker/settings.py", r'''
"""Django settings for the City Bus Tracker. All secrets come from environment variables."""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent   # .../bus-tracker/backend
REPO_ROOT = BASE_DIR.parent                          # .../bus-tracker


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader for local development (real env vars always win)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


DEBUG = env_bool("DEBUG", False)

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key"
    else:
        raise ImproperlyConfigured("The SECRET_KEY environment variable is required when DEBUG is off.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")   # e.g. https://my-app.onrender.com

_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")   # set automatically on Render
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "buses",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",              # must sit above WhiteNoise/CommonMiddleware
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "tracker.urls"
WSGI_APPLICATION = "tracker.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# DATABASE_URL (Postgres on the host); falls back to local SQLite.
if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": dj_database_url.config(conn_max_age=600)}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"      # keep UTC so device timestamps are never reinterpreted
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- Static files + the /web frontend (served by WhiteNoise) ----
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_ROOT = REPO_ROOT / "web"     # web/index.html -> "/", web/app.js -> "/app.js"
WHITENOISE_INDEX_FILE = True

# ---- DRF: JSON only, no session auth (the ingest endpoint uses X-API-Key) ----
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
}

# ---- CORS (only needed when the frontend runs on another origin, e.g. Live Server) ----
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")

# ---- Production hardening ----
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Leave FORCE_HTTPS off while bench-testing the modem over plain HTTP; turn it on afterwards.
    SECURE_SSL_REDIRECT = env_bool("FORCE_HTTPS", False)
    SECURE_HSTS_SECONDS = int(os.environ.get("HSTS_SECONDS", "0"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
''')

add("backend/tracker/urls.py", r'''
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("buses.urls")),
]
''')

# --------------------------------------------------------------------------- buses app
add("backend/buses/models.py", r'''
import secrets

from django.db import models


def generate_api_key() -> str:
    return secrets.token_urlsafe(24)


class Route(models.Model):
    name = models.CharField(max_length=100)
    path = models.JSONField(default=list)   # [[lat, lng], ...]

    def __str__(self):
        return self.name


class Stop(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stops")
    code = models.CharField(max_length=10, blank=True)   # e.g. "S1" from stops.json
    name = models.CharField(max_length=100)
    lat = models.FloatField()
    lng = models.FloatField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.order}. {self.name}"


class Bus(models.Model):
    code = models.CharField(max_length=20, unique=True)   # e.g. BUS-01
    route = models.ForeignKey(Route, null=True, blank=True, on_delete=models.SET_NULL, related_name="buses")
    api_key = models.CharField(max_length=64, default=generate_api_key)

    def __str__(self):
        return self.code


class Position(models.Model):
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE, related_name="positions")
    lat = models.FloatField()
    lng = models.FloatField()
    speed = models.FloatField(default=0)      # km/h
    heading = models.FloatField(default=0)    # degrees
    fix_time = models.DateTimeField(null=True, blank=True)   # when the GPS fix was taken (device, UTC)
    received_at = models.DateTimeField(auto_now_add=True)    # when the server stored it

    class Meta:
        ordering = ["-received_at"]
        indexes = [models.Index(fields=["bus", "-received_at"], name="pos_bus_received_idx")]

    @property
    def delay_seconds(self):
        """End-to-end delay (GPS fix -> server), or None if the device sent no fix_time."""
        if self.fix_time is None:
            return None
        return round((self.received_at - self.fix_time).total_seconds(), 1)

    def __str__(self):
        return f"{self.bus} @ {self.received_at:%H:%M:%S}"
''')

add("backend/buses/admin.py", r'''
from django.contrib import admin

from .models import Bus, Position, Route, Stop


class StopInline(admin.TabularInline):
    model = Stop
    extra = 0
    ordering = ("order",)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("name", "point_count", "stop_count")
    inlines = [StopInline]

    @admin.display(description="Path points")
    def point_count(self, obj):
        return len(obj.path or [])

    @admin.display(description="Stops")
    def stop_count(self, obj):
        return obj.stops.count()


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ("code", "route", "last_seen")

    @admin.display(description="Last seen")
    def last_seen(self, obj):
        p = obj.positions.order_by("-received_at").first()
        return p.received_at if p else None


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("bus", "lat", "lng", "speed", "heading", "fix_time", "received_at", "delay")
    list_filter = ("bus",)
    list_select_related = ("bus",)
    date_hierarchy = "received_at"
    readonly_fields = ("received_at",)

    @admin.display(description="Delay (s)")
    def delay(self, obj):
        return obj.delay_seconds
''')

add("backend/buses/geo.py", r'''
from math import cos, radians

KM_PER_DEG_LAT = 111.32


def route_bbox(path):
    """(min_lat, min_lng, max_lat, max_lng) of a [[lat, lng], ...] path."""
    lats = [p[0] for p in path]
    lngs = [p[1] for p in path]
    return min(lats), min(lngs), max(lats), max(lngs)


def is_near_route_bbox(lat, lng, path, margin_km=5.0):
    """True if the point lies inside the route's bounding box grown by `margin_km` on every side."""
    min_lat, min_lng, max_lat, max_lng = route_bbox(path)
    dlat = margin_km / KM_PER_DEG_LAT
    mid_lat = (min_lat + max_lat) / 2
    dlng = margin_km / (KM_PER_DEG_LAT * max(cos(radians(mid_lat)), 0.01))
    return (min_lat - dlat <= lat <= max_lat + dlat) and (min_lng - dlng <= lng <= max_lng + dlng)
''')

add("backend/buses/serializers.py", r'''
import math
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

MAX_SPEED_KMH = 120.0
MAX_FUTURE_SKEW = timedelta(minutes=5)


class IngestSerializer(serializers.Serializer):
    bus_id = serializers.CharField(max_length=20)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    speed = serializers.FloatField(min_value=0, max_value=MAX_SPEED_KMH, required=False, default=0.0)
    heading = serializers.FloatField(min_value=0, max_value=360, required=False, default=0.0)
    fix_time = serializers.DateTimeField(required=False, allow_null=True, default=None)

    def validate_fix_time(self, value):
        if value and value > timezone.now() + MAX_FUTURE_SKEW:
            raise serializers.ValidationError("fix_time is in the future.")
        return value

    def validate(self, attrs):
        # NaN/Infinity slip through min/max comparisons, so reject them explicitly.
        for name in ("lat", "lng", "speed", "heading"):
            if not math.isfinite(attrs[name]):
                raise serializers.ValidationError({name: "Must be a finite number."})
        return attrs
''')

add("backend/buses/views.py", r'''
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
''')

add("backend/buses/urls.py", r'''
from django.urls import path

from . import views

urlpatterns = [
    path("ingest/", views.ingest, name="ingest"),
    path("buses/", views.buses, name="buses"),
    path("routes/<int:pk>/", views.route_detail, name="route-detail"),
]
''')

add("backend/buses/tests.py", r'''
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Bus, Position, Route

KEY = "test-key-123"


class IngestTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        route = Route.objects.create(name="Test", path=[[24.0, 90.42], [23.95, 90.41], [23.879, 90.4005]])
        Bus.objects.create(code="BUS-01", route=route, api_key=KEY)

    def post(self, overrides=None, key=KEY):
        body = {"bus_id": "BUS-01", "lat": 23.95, "lng": 90.41, "speed": 20, "heading": 90}
        body.update(overrides or {})
        extra = {"HTTP_X_API_KEY": key} if key is not None else {}
        return self.client.post(reverse("ingest"), body, format="json", **extra)

    # --- the 3 required tests ---
    def test_valid_post_is_stored(self):
        res = self.post({"fix_time": timezone.now().isoformat()})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Position.objects.count(), 1)
        self.assertIsNotNone(Position.objects.first().fix_time)

    def test_wrong_api_key_is_rejected(self):
        self.assertEqual(self.post(key="wrong-key").status_code, 401)
        self.assertEqual(self.post(key=None).status_code, 401)
        self.assertEqual(Position.objects.count(), 0)

    def test_out_of_range_coordinates_are_rejected(self):
        self.assertEqual(self.post({"lat": 91}).status_code, 400)
        self.assertEqual(self.post({"lng": -181}).status_code, 400)
        self.assertEqual(Position.objects.count(), 0)

    # --- extras covering the other validation rules ---
    def test_speed_above_120_is_rejected(self):
        self.assertEqual(self.post({"speed": 150}).status_code, 400)

    def test_position_far_from_route_is_rejected(self):
        res = self.post({"lat": 23.78, "lng": 90.40})   # ~11 km south of Abdullahpur
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"], "off_route")
''')

add("backend/buses/management/commands/seed_data.py", r'''
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from buses.models import Bus, Route, Stop, generate_api_key


def _load_json(path: Path):
    if not path.is_file():
        raise CommandError(f"File not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CommandError(f"{path.name} is not valid JSON: {exc}")


class Command(BaseCommand):
    help = "Load data/route.json and data/stops.json and create BUS-01 (safe to re-run)."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", default=str(settings.REPO_ROOT / "data"))
        parser.add_argument("--route-name", default="Gazipur Chowrasta - Abdullahpur")
        parser.add_argument("--bus-code", default="BUS-01")
        parser.add_argument("--reset-key", action="store_true", help="Generate a new API key for the bus.")
        parser.add_argument("--show-key", action="store_true", help="Print the key even if the bus already existed.")

    @transaction.atomic
    def handle(self, *args, **opts):
        data_dir = Path(opts["data_dir"])
        path = _load_json(data_dir / "route.json")
        stops = _load_json(data_dir / "stops.json")

        if not (isinstance(path, list) and len(path) >= 2
                and all(isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p) for p in path)):
            raise CommandError("route.json must be a list of [lat, lng] pairs (at least 2).")
        needed = {"name", "lat", "lng", "order"}
        if not (isinstance(stops, list) and all(isinstance(s, dict) and needed <= s.keys() for s in stops)):
            raise CommandError("stops.json must be a list of objects with name, lat, lng, order.")

        route, route_created = Route.objects.update_or_create(name=opts["route_name"], defaults={"path": path})

        for s in stops:
            Stop.objects.update_or_create(
                route=route, order=s["order"],
                defaults={"code": s.get("id", ""), "name": s["name"], "lat": s["lat"], "lng": s["lng"]},
            )
        route.stops.exclude(order__in=[s["order"] for s in stops]).delete()

        bus, bus_created = Bus.objects.get_or_create(code=opts["bus_code"], defaults={"route": route})
        changed = False
        if bus.route_id != route.pk:
            bus.route, changed = route, True
        if opts["reset_key"]:
            bus.api_key, changed = generate_api_key(), True
        if changed:
            bus.save()

        self.stdout.write(self.style.SUCCESS(
            f"Route '{route.name}' (id={route.pk}, {'created' if route_created else 'updated'}): "
            f"{len(path)} points, {len(stops)} stops."
        ))
        self.stdout.write(self.style.SUCCESS(f"Bus {bus.code} {'created' if bus_created else 'ready'}."))
        if bus_created or opts["reset_key"] or opts["show_key"]:
            self.stdout.write(f"API key for {bus.code}: {bus.api_key}")
''')

# --------------------------------------------------------------------------- frontend
add("web/style.css", r'''
/* style.css - mobile-first styles for the City Bus Tracker. */
:root {
  --accent: #1d6fe8;
  --stop: #ffffff;
  --glass-bg: rgba(255, 255, 255, 0.55);
  --glass-border: rgba(255, 255, 255, 0.7);
  --text: #14202e;
}
*, *::before, *::after { box-sizing: border-box; }
html, body { height: 100%; margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--text); }
#map { position: fixed; inset: 0; z-index: 0; }

/* Floating glassmorphic header */
.glass-header {
  position: fixed; z-index: 1000;
  top: calc(env(safe-area-inset-top, 0px) + 12px); left: 12px; right: 12px;
  padding: 10px 16px; border-radius: 16px;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  -webkit-backdrop-filter: blur(14px) saturate(160%); backdrop-filter: blur(14px) saturate(160%);
  box-shadow: 0 8px 28px rgba(20, 32, 46, 0.18);
}
.glass-header h1 { margin: 0; font-size: 1.05rem; }
.glass-header p { margin: 2px 0 0; font-size: 0.85rem; opacity: 0.8; }
.glass-header .status { font-weight: 600; color: var(--accent); opacity: 1; }
.glass-header .status.stale { color: #6b7480; }
.glass-header .status.error { color: #c92a2a; }

/* Custom circular stop markers (Leaflet divIcon) */
.stop-marker {
  display: grid; place-items: center; width: 26px; height: 26px; border-radius: 50%;
  background: var(--stop); border: 3px solid var(--accent);
  font-size: 12px; font-weight: 700; color: var(--accent);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}
/* Live bus marker with pulse ring */
.bus-marker {
  display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%;
  background: #e5484d; border: 3px solid #fff; color: #fff; font-weight: 800; font-size: 13px;
  box-shadow: 0 0 0 0 rgba(229, 72, 77, 0.6); animation: pulse 1.8s infinite;
  transition: background 0.3s;
}
@keyframes pulse { 70% { box-shadow: 0 0 0 16px rgba(229, 72, 77, 0); } 100% { box-shadow: 0 0 0 0 rgba(229, 72, 77, 0); } }
/* No report for > 60 s: grey, no pulse */
.bus-marker.stale { background: #8a94a3; animation: none; box-shadow: none; }

.error-banner {
  position: fixed; z-index: 1100; left: 12px; right: 12px; bottom: calc(env(safe-area-inset-bottom, 0px) + 16px);
  padding: 14px 16px; border-radius: 12px; background: #fff3f3; border: 1px solid #e5484d; font-size: 0.9rem;
}
.error-banner code { background: #fde0e0; padding: 1px 5px; border-radius: 4px; }

@media (min-width: 768px) {
  .glass-header { right: auto; width: 360px; left: 20px; top: 20px; }
}
@media (prefers-reduced-motion: reduce) { .bus-marker { animation: none; } }
''')

add("web/app.js", r'''
/**
 * app.js - City Bus Tracker (Leaflet.js front end, live API version)
 *
 * Data flow:
 *   ApiClient.loadRoute()  -> GET /api/routes/1/   (path + ordered stops)
 *   MapView                -> map, polyline, fit bounds, stop markers
 *   BusLayer               -> one marker per bus, updated from GET /api/buses/ every 4 s
 *
 * Classic script (not an ES module) so the file:// error banner can still run.
 */
(() => {
  'use strict';

  // VS Code Live Server (port 5500/5501) serves only /web, so point API calls at Django.
  const isDevServer = ['5500', '5501'].includes(location.port);

  const CONFIG = {
    apiBase: window.API_BASE ?? (isDevServer ? 'http://127.0.0.1:8000' : ''),
    routeId: 1,
    pollMs: 4000,          // delay between /api/buses/ polls
    staleAfterS: 60,       // grey the marker after this many seconds without a report
    timeoutMs: 8000,       // per-request timeout
    routeStyle: { color: '#1d6fe8', weight: 5, opacity: 0.85 },
    tileUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors'
  };

  const esc = s => String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const formatAge = seconds => {
    const s = Math.max(0, Math.round(seconds));
    if (s < 120) return `${s} s ago`;
    const m = Math.floor(s / 60);
    return m < 120 ? `${m} min ago` : `${Math.floor(m / 60)} h ago`;
  };

  /** Small JSON client with timeout and status-carrying errors. */
  class ApiClient {
    static async getJson(path) {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), CONFIG.timeoutMs);
      try {
        const res = await fetch(CONFIG.apiBase + path, {
          signal: ctrl.signal, cache: 'no-store', headers: { Accept: 'application/json' }
        });
        if (!res.ok) {
          const err = new Error(`HTTP ${res.status} while loading ${path}`);
          err.status = res.status;
          throw err;
        }
        return await res.json();
      } catch (err) {
        if (err.name === 'AbortError') throw new Error(`Request timed out (${path})`);
        throw err;
      } finally {
        clearTimeout(timer);
      }
    }
    static async loadRoute() {
      const route = await ApiClient.getJson(`/api/routes/${CONFIG.routeId}/`);
      route.stops.sort((a, b) => a.order - b.order);
      return route;
    }
    static loadBuses() { return ApiClient.getJson('/api/buses/'); }
  }

  /** Owns the Leaflet map and static layers. */
  class MapView {
    constructor(elId) {
      this.map = L.map(elId, { zoomControl: false });
      L.control.zoom({ position: 'bottomright' }).addTo(this.map);
      L.tileLayer(CONFIG.tileUrl, { maxZoom: 19, attribution: CONFIG.attribution }).addTo(this.map);
    }
    drawRoute(path) {
      const line = L.polyline(path, CONFIG.routeStyle).addTo(this.map);
      this.map.fitBounds(line.getBounds(), { paddingTopLeft: [20, 110], paddingBottomRight: [20, 30] });
    }
    drawStops(stops) {
      stops.forEach(s => {
        const icon = L.divIcon({
          className: '', iconSize: [26, 26], iconAnchor: [13, 13],
          html: `<div class="stop-marker">${s.order}</div>`
        });
        L.marker([s.lat, s.lng], { icon, title: s.name })
          .addTo(this.map)
          .bindPopup(`<strong>${esc(s.name)}</strong><br>Stop ${s.order}${s.code ? ' &middot; ID ' + esc(s.code) : ''}`);
      });
    }
  }

  /**
   * Live bus markers. Age is computed from the server's `seconds_ago` plus local elapsed time,
   * so it ticks every second between polls and is immune to phone/server clock differences.
   */
  class BusLayer {
    constructor(map) { this.map = map; this.items = new Map(); }

    update(list) {
      const now = Date.now();
      const seen = new Set();
      for (const b of list) {
        seen.add(b.code);
        const latlng = [b.lat, b.lng];
        let it = this.items.get(b.code);
        if (!it) {
          const marker = L.marker(latlng, {
            zIndexOffset: 1000, title: b.code,
            icon: L.divIcon({ className: '', iconSize: [34, 34], iconAnchor: [17, 17],
                              html: '<div class="bus-marker">B</div>' })
          }).addTo(this.map).bindPopup('');
          it = { marker };
          this.items.set(b.code, it);
        } else {
          it.marker.setLatLng(latlng);
        }
        it.code = b.code;
        it.secondsAgo = b.seconds_ago;
        it.receivedAt = now;
        it.marker.setPopupContent(`<strong>${esc(b.code)}</strong><br>${Math.round(b.speed)} km/h`);
      }
      for (const [code, it] of this.items) {
        if (!seen.has(code)) { it.marker.remove(); this.items.delete(code); }
      }
      this.refreshStale();
    }

    age(it) { return it.secondsAgo + (Date.now() - it.receivedAt) / 1000; }

    refreshStale() {
      for (const it of this.items.values()) {
        const el = it.marker.getElement()?.querySelector('.bus-marker');
        if (el) el.classList.toggle('stale', this.age(it) > CONFIG.staleAfterS);
      }
    }

    /** Freshest bus, for the header status line (or null if none has reported). */
    summary() {
      let best = null;
      for (const it of this.items.values()) {
        const age = this.age(it);
        if (!best || age < best.age) best = { code: it.code, age, stale: age > CONFIG.staleAfterS };
      }
      return best;
    }
  }

  /** Friendly banner; special-cases file:// where fetch() is blocked. */
  function showError(err) {
    const banner = document.getElementById('error-banner');
    const isFile = location.protocol === 'file:';
    if (isFile) {
      banner.innerHTML = '<strong>Open via a local server.</strong> Browsers block data loading from <code>file://</code>. ' +
        'Run <code>python manage.py runserver</code> and open <code>http://127.0.0.1:8000/</code> ' +
        '(or use VS Code Live Server with the backend running).';
    } else {
      const hint = err.status === 404 ? ' Did you run <code>python manage.py seed_data</code>?' : '';
      banner.innerHTML = `<strong>Could not load route data.</strong> ${esc(err.message)}${hint}`;
    }
    banner.hidden = false;
    document.getElementById('bus-status').textContent = 'Data unavailable';
  }

  async function main() {
    const statusEl = document.getElementById('bus-status');
    const setStatus = (text, kind = '') => { statusEl.textContent = text; statusEl.className = 'status' + (kind ? ' ' + kind : ''); };

    const view = new MapView('map');
    view.map.setView([23.94, 90.405], 11);   // neutral fallback view

    let route;
    try {
      route = await ApiClient.loadRoute();
    } catch (err) {
      console.error(err);
      showError(err);
      return;
    }
    view.drawRoute(route.path);
    view.drawStops(route.stops);

    const layer = new BusLayer(view.map);
    let online = true;

    const render = () => {
      const s = layer.summary();
      if (!online) {
        setStatus(s ? `Connection lost, retrying... (${s.code} last seen ${formatAge(s.age)})`
                    : 'Connection lost, retrying...', 'error');
      } else if (!s) {
        setStatus('Waiting for a bus to report...');
      } else {
        setStatus(`${s.code} \u00b7 Updated ${formatAge(s.age)}${s.stale ? ' (no recent signal)' : ''}`,
                  s.stale ? 'stale' : '');
      }
    };

    // Chained setTimeout (not setInterval) so slow responses never overlap.
    const poll = async () => {
      try {
        layer.update(await ApiClient.loadBuses());
        online = true;
      } catch (err) {
        console.warn(err);
        online = false;
      }
      render();
      setTimeout(poll, CONFIG.pollMs);
    };

    setInterval(() => { layer.refreshStale(); render(); }, 1000);   // tick "X s ago" and stale colour
    poll();
  }

  document.addEventListener('DOMContentLoaded', main);
})();
''')

# --------------------------------------------------------------------------- tools + docs
add("tools/fake_bus.py", r'''
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
''')

add("docs/api.md", r'''
# City Bus Tracker - API contract

Base URL: `http://127.0.0.1:8000` (local) or your HTTPS host. All bodies are JSON. Times are UTC, ISO 8601.
Changes to this file need agreement from Fahad and Raiyan.

## POST /api/ingest/
Called by the bus unit (or `tools/fake_bus.py`).

Headers: `Content-Type: application/json`, `X-API-Key: <key of the bus named in bus_id>`

| Field     | Type     | Required | Rule |
|-----------|----------|----------|------|
| `bus_id`  | string   | yes      | Must match a `Bus.code`, e.g. `BUS-01` |
| `lat`     | number   | yes      | -90 to 90 |
| `lng`     | number   | yes      | -180 to 180 |
| `speed`   | number   | no (0)   | km/h, 0 to 120 |
| `heading` | number   | no (0)   | degrees, 0 to 360 |
| `fix_time`| string   | no       | UTC time of the GPS fix, e.g. `2026-11-21T10:15:30Z`. Not more than 5 min in the future. Used to measure delay (`received_at - fix_time`). |

Extra rule: the position must lie within 5 km of the route's bounding box, otherwise `off_route`.

| Status | Meaning | Body |
|--------|---------|------|
| 201 | Stored | `{"ok": true, "id": 123}` |
| 400 | Invalid data, malformed JSON, or off route | `{"error": "invalid_data", "details": {...}}` or `{"error": "off_route", "detail": "..."}` |
| 401 | Missing/wrong key or unknown `bus_id` | `{"error": "unauthorized"}` |

```
curl -X POST http://127.0.0.1:8000/api/ingest/ -H "Content-Type: application/json" -H "X-API-Key: YOUR_KEY" \
  -d '{"bus_id":"BUS-01","lat":23.95,"lng":90.40,"speed":20,"heading":90,"fix_time":"2026-11-21T10:15:30Z"}'
```

## GET /api/buses/
Latest position of every bus that has reported at least once. Never cached.

```json
[{
  "code": "BUS-01", "route": 1, "lat": 23.9503, "lng": 90.3997, "speed": 36.0, "heading": 181.4,
  "updated": "2026-11-21T10:15:31.220Z", "seconds_ago": 2,
  "fix_time": "2026-11-21T10:15:30.900Z", "delay_seconds": 0.3
}]
```
`updated` is the server receive time; `seconds_ago` is computed by the server, so clients need no clock sync.
The web app greys a bus when `seconds_ago` (plus elapsed local time) exceeds 60.

## GET /api/routes/<id>/
```json
{ "id": 1, "name": "Gazipur Chowrasta - Abdullahpur",
  "path": [[24.0, 90.42], [23.999803, 90.419789]],
  "stops": [{"id": 1, "code": "S1", "name": "Gazipur Chowrasta", "lat": 24.0, "lng": 90.42, "order": 1}] }
```
`stops` are sorted by `order`. Unknown id returns 404 `{"detail": "Not found."}`.

## Firmware notes
- Send `fix_time` from the GPS UTC clock, not the ESP32 clock.
- Treat only `201` as success; retry on network errors and 5xx, drop the point on 400.
''')

# --------------------------------------------------------------------------- run
PRESERVED = ["data/route.json", "data/stops.json", "tools/gpx_converter.html", "web/index.html"]


def main():
    print(f"Project root: {ROOT}")
    if not ROOT.is_dir():
        sys.exit(f"ERROR: folder does not exist: {ROOT}")

    for rel, (text, overwrite) in FILES.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            print(f"  kept     {rel}  (already exists)")
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"  written  {rel}")

    print("\nLeft untouched:")
    missing = False
    for rel in PRESERVED:
        ok = (ROOT / rel).exists()
        missing = missing or not ok
        print(f"  {'ok     ' if ok else 'MISSING'}  {rel}")
    if missing:
        print("\nWARNING: a file above is missing. data/route.json and data/stops.json are required by seed_data.")
    print("\nDone. Next: create the venv, install requirements, migrate, seed, test, runserver (see the commands you were given).")


if __name__ == "__main__":
    main()
