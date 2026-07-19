"""NanobaseAI Apache Superset config — embedded canvas + guest JWT.

Secrets come from environment (see configs/superset-bi.env.example).
Mount this file at /app/pythonpath/superset_config.py.
"""

from __future__ import annotations

import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "nanobase_superset_change_me")

FEATURE_FLAGS = {
    "EMBEDDED_SUPERSET": True,
    "EMBEDDABLE_CHARTS": True,
    "DASHBOARD_NATIVE_FILTERS": True,
    "ALERT_REPORTS": False,
}

# Guest embed JWT — MUST match BI_SUPERSET_GUEST_* on nanobase_api
GUEST_ROLE_NAME = os.environ.get("GUEST_ROLE_NAME", "Gamma")
GUEST_TOKEN_JWT_SECRET = os.environ.get(
    "GUEST_TOKEN_JWT_SECRET",
    os.environ.get("BI_SUPERSET_GUEST_SECRET", "changeme_guest_jwt_secret_min_32_chars"),
)
GUEST_TOKEN_JWT_ALGO = "HS256"
GUEST_TOKEN_HEADER_NAME = "X-GuestToken"
GUEST_TOKEN_JWT_EXP_SECONDS = int(os.environ.get("GUEST_TOKEN_JWT_EXP_SECONDS", "1800"))
GUEST_TOKEN_JWT_AUDIENCE = os.environ.get(
    "GUEST_TOKEN_JWT_AUDIENCE",
    os.environ.get("BI_SUPERSET_GUEST_AUDIENCE", "http://0.0.0.0:8080/"),
)

ENABLE_PROXY_FIX = True
ENABLE_CORS = True
_cors = os.environ.get(
    "SUPERSET_CORS_ORIGINS",
    "https://portal.nanobase.ai,https://bi.nanobase.ai,http://localhost:5173,http://127.0.0.1:5173",
)
CORS_OPTIONS = {
    "supports_credentials": True,
    "allow_headers": ["*"],
    "resources": [r"^/api/.*", r"^/superset/.*", r"^/embedded/.*"],
    "origins": [o.strip() for o in _cors.split(",") if o.strip()],
}

# Embedded iframes need relaxed framing; nginx should still restrict by host.
HTTP_HEADERS = {"X-Frame-Options": "ALLOWALL"}
TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = True

# Prefer Redis when available (compose sets REDIS_HOST)
_redis = os.environ.get("REDIS_HOST", "redis")
_redis_port = os.environ.get("REDIS_PORT", "6379")
CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "superset_",
    "CACHE_REDIS_HOST": _redis,
    "CACHE_REDIS_PORT": int(_redis_port),
    "CACHE_REDIS_DB": 1,
}
DATA_CACHE_CONFIG = CACHE_CONFIG
FILTER_STATE_CACHE_CONFIG = CACHE_CONFIG
EXPLORE_FORM_DATA_CACHE_CONFIG = CACHE_CONFIG

SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SQLALCHEMY_DATABASE_URI",
    "postgresql+psycopg2://superset:superset@db:5432/superset",
)

ROW_LIMIT = 10000
SUPERSET_WEBSERVER_TIMEOUT = 120
DEFAULT_LOCALE = os.environ.get("SUPERSET_DEFAULT_LOCALE", "tr")
