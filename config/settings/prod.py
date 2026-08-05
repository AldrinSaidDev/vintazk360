"""
Production settings.

Select with ``DJANGO_SETTINGS_MODULE=config.settings.prod``. Everything that
must be locked down for a public deployment lives here. Required secrets are
read from the environment and the process refuses to start without them.
"""

import os

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE as _BASE_MIDDLEWARE
from .base import SECRET_KEY

DEBUG = False

if not SECRET_KEY:
    raise RuntimeError(
        'SECRET_KEY environment variable is required in production.'
    )

# Comma-separated list of hostnames, e.g. "example.com,www.example.com".
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('ALLOWED_HOSTS', '').split(',')
    if host.strip()
]

# Render injects the service's public hostname (e.g. "vintazk360.onrender.com")
# as RENDER_EXTERNAL_HOSTNAME. Trusting it automatically means a deploy works
# before anyone has typed the generated URL into ALLOWED_HOSTS by hand.
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip()
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Security hardening (safe defaults for a TLS-terminated deployment).
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', '1') == '1'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# CSRF trusted origins must include the scheme, e.g. "https://example.com".
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

if RENDER_EXTERNAL_HOSTNAME:
    _render_origin = f'https://{RENDER_EXTERNAL_HOSTNAME}'
    if _render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_render_origin)


# Static files.
#
# There is no separate web server in front of the app on Render — gunicorn is
# the only process — so WhiteNoise serves /static/ straight from the container.
# It must sit immediately after SecurityMiddleware to see every request.
MIDDLEWARE = [
    _BASE_MIDDLEWARE[0],
    'whitenoise.middleware.WhiteNoiseMiddleware',
    *_BASE_MIDDLEWARE[1:],
]

STORAGES = {
    # Media (user uploads) is NOT Django-managed: KPI import files go to
    # Cloudflare R2 through apps/core/storage.py, which stores its own pointer.
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    # Hashed filenames + precompressed copies, so static assets cache forever.
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}
