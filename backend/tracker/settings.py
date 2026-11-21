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
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

if not DEBUG:
    ALLOWED_HOSTS.append(".onrender.com")
    CSRF_TRUSTED_ORIGINS.append("https://*.onrender.com")

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
    "corsheaders.middleware.CorsMiddleware",
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

# Ensure backend/templates exists so Django never warns or fails on dashboard templates
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [TEMPLATES_DIR],
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

# DATABASE_URL (Postgres on Render); falls back to local SQLite.
_db_url = os.environ.get("DATABASE_URL", "").strip()
if _db_url:
    DATABASES = {
        "default": dj_database_url.parse(
            _db_url,
            conn_max_age=600,
            ssl_require=not DEBUG and "render.com" in _db_url,
        )
    }
else:
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
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

WEB_DIR = REPO_ROOT / "web"
if WEB_DIR.is_dir():
    WHITENOISE_ROOT = WEB_DIR
    WHITENOISE_INDEX_FILE = True

# ---- DRF: JSON only, custom X-API-Key auth on ingest, rate limiting ready ----
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "DEFAULT_THROTTLE_RATES": {
        "ingest": "60/minute",
    },
}

# ---- CORS (only needed when frontend runs on a separate port, e.g. Live Server) ----
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")

# ---- Referrer policy: OpenStreetMap requires Referer header for tiles ----
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# ---- Production hardening ----
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("FORCE_HTTPS", False)
    SECURE_HSTS_SECONDS = int(os.environ.get("HSTS_SECONDS", "0"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}