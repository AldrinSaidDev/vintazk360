"""
Development settings.

Selected by default (see config/settings/__init__.py). Optimized for a fast
local loop: DEBUG on, permissive hosts, and an insecure fallback SECRET_KEY so
a fresh clone runs with zero configuration.
"""

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '[::1]']

# For local development we fall back to a well-known insecure key so the app
# runs without any extra setup. Never rely on this in production.
if not SECRET_KEY:
    SECRET_KEY = 'django-insecure-o5l@kpnc6vd1n+t1ia_)r!d$@o8$&ht9j(&%^vj@mz3w41#o5q'
