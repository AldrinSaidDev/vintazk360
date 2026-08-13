"""
Base Django settings shared by all environments.

Environment-specific settings live in ``dev.py`` and ``prod.py`` and import
everything from this module. Select one with the ``DJANGO_SETTINGS_MODULE``
environment variable, e.g. ``config.settings.dev`` (the default) or
``config.settings.prod``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/topics/settings/
"""

import os
from pathlib import Path
from urllib.parse import urlparse

import dj_database_url
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# This file is config/settings/base.py, so the project root is three levels up.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / '.env')


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# Overridable via env; dev.py falls back to an insecure default.
SECRET_KEY = os.environ.get('SECRET_KEY', '')

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG and ALLOWED_HOSTS are set per-environment in dev.py / prod.py.
DEBUG = False

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django_icons',
    'apps.core',
    # KPI definitions, actuals and import history — shared by every LOB below.
    'apps.kpi',
    'apps.dashboard',
    # Line-of-business (LOB) screens
    'apps.sales',
    'apps.hr',
    'apps.academy',
    'apps.operations',
    'apps.finance',
    'apps.sitelead',
    # VCT / SMM / Content Writing are three separate departments, not one team.
    'apps.vct',
    'apps.smm',
    'apps.content',
    'apps.nexzys',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Idle sign-out. Reads request.user and writes a message, so it has to come
    # after both AuthenticationMiddleware and MessageMiddleware.
    'apps.core.middleware.SessionIdleTimeoutMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.navigation',
                'apps.core.context_processors.permissions',
                'apps.core.context_processors.tour',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    raise RuntimeError(
        'DATABASE_URL is not set. Development runs on Docker Compose (Postgres); '
        'staging/production point at Render Postgres. See .env.example.'
    )

# SSL is required for remote databases (e.g. Render Postgres) but must be OFF
# for the local Postgres container, which does not serve SSL. Local hosts are
# detected automatically; set DATABASE_SSL=require or =disable to override.
DATABASE_HOST = urlparse(DATABASE_URL).hostname
LOCAL_DB_HOSTS = {'localhost', '127.0.0.1', 'db'}

_ssl_env = os.environ.get('DATABASE_SSL', '').strip().lower()
if _ssl_env in {'require', 'true', '1'}:
    DATABASE_SSL_REQUIRED = True
elif _ssl_env in {'disable', 'false', '0'}:
    DATABASE_SSL_REQUIRED = False
else:
    DATABASE_SSL_REQUIRED = DATABASE_HOST not in LOCAL_DB_HOSTS

DATABASES = {
    'default': dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=DATABASE_SSL_REQUIRED,
    )
}


# Cache
# https://docs.djangoproject.com/en/6.0/topics/cache/
#
# A THIRD channel, independent of the two below it: Redis (a Valkey container in
# development, Render Key Value in staging). Postgres above is the source of
# truth for application data and nothing else; everything stored here is a
# derived answer that can be rebuilt from it, which is why losing the whole
# cache costs one slow page and never a figure.
#
# Not local memory: that is per PROCESS, and staging runs gunicorn with several
# workers. A KPI edit handled by worker 1 would leave workers 2 and 3 serving
# the old figure until their own copies went stale, so "an edit is visible
# immediately" would hold only for whichever worker took the next request. The
# cache has to be shared for invalidation to mean anything.
#
# Not a table in Postgres either, which is what this replaced. Every cache read
# was a query against the same database the cache exists to spare, every write
# an INSERT, and the culling pass a DELETE over a table the application also
# depends on. Redis keeps that traffic off the database entirely.
#
# The backend is Django's own `RedisCache`, which needs `redis` (see
# requirements/base.txt) and speaks to Valkey unchanged: it is the same wire
# protocol.
REDIS_URL = (os.environ.get('REDIS_URL') or os.environ.get('CACHE_URL') or '').strip()

if not REDIS_URL:
    raise RuntimeError(
        'REDIS_URL is not set. Development runs on Docker Compose (the `cache` '
        'Valkey container, injected automatically); staging points at Render '
        'Key Value. See .env.example.'
    )

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        # The default TTL for anything that does not name its own. Never None:
        # a key with no expiry is a key nothing ever reclaims, and the free Key
        # Value plan is 25MB.
        'TIMEOUT': int(os.environ.get('CACHE_GC_SECONDS', '1800')),
        # Namespaces our keys, so one Key Value instance could serve another
        # service without either being able to read the other's entries.
        'KEY_PREFIX': os.environ.get('CACHE_KEY_PREFIX', 'vz360'),
        'OPTIONS': {
            # A cache is an optimisation, so it gets seconds, not minutes. If
            # Key Value is slow or unreachable the request should fall back to
            # Postgres promptly rather than hold a worker (apps/core/cache.py
            # treats any failure as a miss).
            'socket_connect_timeout': 2,
            'socket_timeout': 2,
            'retry_on_timeout': True,
            # Render's free instances idle out long-lived TCP connections; this
            # pings a pooled one rather than handing over a dead socket.
            'health_check_interval': 30,
        },
    }
}

# Read-through policy, applied by `apps.core.cache`. Stale time is how long a
# cached answer is served; GC time is the key's TTL in Redis, and the only thing
# bounding the keyspace. Neither delays a write: saving a KPI, a record or an
# import retires its team's cache on the spot. That module's docstring explains
# why all three exist.
CACHE_STALE_SECONDS = int(os.environ.get('CACHE_STALE_SECONDS', '300'))    # 5 minutes
CACHE_GC_SECONDS = int(os.environ.get('CACHE_GC_SECONDS', '1800'))        # 30 minutes
# Version tokens have to outlive the entries they stamp. Long, but not forever:
# a token nobody has read in a month belongs to a team nobody has opened in a
# month. Losing one early only costs a recomputation.
CACHE_VERSION_SECONDS = int(os.environ.get('CACHE_VERSION_SECONDS', '2592000'))  # 30 days


# Object storage — Cloudflare R2
# https://developers.cloudflare.com/r2/api/s3/api/
#
# Two INDEPENDENT channels, don't confuse them:
#   1. DATABASE_URL (above) — Django's ORM speaking Postgres. Development keeps
#      pointing this at the local Docker container; staging points it at Render
#      Postgres.
#   2. The settings below — uploaded files (KPI import CSVs), which live in a
#      Cloudflare R2 bucket and are reached over the S3 API through
#      ``apps.core.storage``. The database stores only a pointer to them.
#
# R2 is S3-compatible, so the endpoint is derived from the account ID unless
# R2_ENDPOINT_URL overrides it. The bucket must be PRIVATE — reads go through a
# Django view that checks team access and returns a short-lived signed URL.

def _r2_env(name, default=''):
    """Read ``R2_<name>`` from the environment, trimmed."""
    return (os.environ.get(f'R2_{name}') or default).strip()


R2_ACCOUNT_ID = _r2_env('ACCOUNT_ID')
R2_ACCESS_KEY_ID = _r2_env('ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = _r2_env('SECRET_ACCESS_KEY')
R2_BUCKET = _r2_env('BUCKET', 'vintazk360-imports')

# Cloudflare's S3 endpoint for the account. Set R2_ENDPOINT_URL only if you use
# a jurisdiction-specific endpoint (e.g. `…r2.cloudflarestorage.com/eu`).
R2_ENDPOINT_URL = _r2_env('ENDPOINT_URL').rstrip('/') or (
    f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com' if R2_ACCOUNT_ID else ''
)

# R2 has no regions, but the S3 API requires the field — `auto` is what
# Cloudflare's own examples pass. Timeout and signed-URL lifetime in seconds.
R2_REGION = _r2_env('REGION', 'auto')
R2_TIMEOUT = int(_r2_env('TIMEOUT', '10'))
R2_SIGNED_URL_TTL = int(_r2_env('SIGNED_URL_TTL', '300'))

# True once the endpoint, bucket and both keys are present. Feature code should
# ask ``apps.core.storage.is_configured()`` rather than reading this directly.
R2_ENABLED = bool(
    R2_ENDPOINT_URL and R2_BUCKET and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY
)


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

# House rule only (see apps/core/validators.py): 6+ characters, one uppercase,
# one special character. Django's four defaults are deliberately not used —
# their combined help text was long and the rules overlapped this one.
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'apps.core.validators.PasswordPolicyValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

# The org runs out of the Philippines, and every timestamp on screen (the
# activity log, an import's "uploaded at", a record's "last updated") is read by
# somebody sitting in that office. Left at UTC they read eight hours early,
# which looks like a bug rather than a timezone. `USE_TZ` stays on, so the
# database still stores UTC and only the rendering moves.
TIME_ZONE = 'Asia/Manila'

USE_I18N = True

USE_TZ = True


# Authentication
# https://docs.djangoproject.com/en/6.0/topics/auth/

# Unauthenticated users hitting a protected view are sent here.
LOGIN_URL = 'login'
# Where users land after a successful login / logout.
LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'login'


# Sessions
# https://docs.djangoproject.com/en/6.0/topics/http/sessions/
#
# One hour of INACTIVITY signs a user out, not one hour from sign-in. Somebody
# entering a month of KPI figures is working, and a hard cap would throw away a
# half-filled Add Record form to prove a point. The clock restarts on every
# request they make.
SESSION_IDLE_TIMEOUT = int(os.environ.get('SESSION_IDLE_TIMEOUT', '3600'))  # 1 hour

# Re-stamps the session cookie on every response, which is what makes the window
# roll. Without it the cookie would expire an hour after sign-in no matter how
# busy the user was, which is the absolute timeout we are deliberately not using.
SESSION_SAVE_EVERY_REQUEST = True

# The cookie outlives the idle window by two minutes ON PURPOSE. Both enforce
# the same hour, but `SessionIdleTimeoutMiddleware` is the one that can log the
# sign-out and say why it happened; if the cookie went first the browser would
# just stop sending it and the user would land on a bare login screen with no
# explanation. The margin is what guarantees the server gets asked.
SESSION_COOKIE_AGE = SESSION_IDLE_TIMEOUT + 120

# The session survives closing the browser, up to the same idle window. Closing
# a tab by accident should not mean signing in again; an hour away should.
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Session data stays server-side in the database (Django's default engine). The
# browser holds only the opaque session key, so no role, team or KPI figure is
# ever readable in a cookie.
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# The session cookie is not readable from JavaScript, and is not sent on
# cross-site navigations. (`Secure` is added in prod.py, where there is TLS.)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'


# Icons (django-icons) — render Font Awesome via {% icon 'name' %}.
# https://django-icons.readthedocs.io/
DJANGO_ICONS = {
    'DEFAULTS': {
        'renderer': 'fontawesome4',
    },
    'RENDERERS': {
        'fontawesome4': 'FontAwesome4Renderer',
    },
}


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files (user uploads)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/6.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
