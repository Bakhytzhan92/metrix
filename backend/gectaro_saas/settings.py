from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-key-change-me")

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

_allowed_extra = os.getenv("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]
if _allowed_extra.strip():
    ALLOWED_HOSTS.extend(h.strip() for h in _allowed_extra.split(",") if h.strip())
_railway_host = os.getenv("RAILWAY_PUBLIC_DOMAIN")
if _railway_host:
    ALLOWED_HOSTS.append(_railway_host.strip())
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))

_csrf_origins = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in _csrf_origins.split(",") if o.strip()
]

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.AccessControlMiddleware",
    "core.platform_middleware.PlatformAccountMiddleware",
]

ROOT_URLCONF = "gectaro_saas.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.company_context",
                "core.context_processors.impersonation_context",
                "core.context_processors.saas_superadmin_context",
            ],
        },
    },
]

WSGI_APPLICATION = "gectaro_saas.wsgi.application"

# PostgreSQL if DATABASE_URL set, else SQLite for local run without DB
_db_url = os.getenv("DATABASE_URL")
if _db_url:
    DATABASES = {
        "default": dj_database_url.parse(_db_url, conn_max_age=600),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"

TIME_ZONE = "Europe/Moscow"

USE_I18N = True

USE_TZ = True

STATIC_URL = "/static/"
_static_dir = BASE_DIR / "static"
if _static_dir.exists():
    STATICFILES_DIRS = [_static_dir]
else:
    STATICFILES_DIRS = []
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
