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
    'apps.dashboard',
    # Line-of-business (LOB) screens
    'apps.sales',
    'apps.hr',
    'apps.academy',
    'apps.operations',
    'apps.finance',
    'apps.sitelead',
    'apps.marketing',
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
        'production points at Supabase. See .env.example.'
    )

# SSL is required for remote databases (e.g. Supabase) but must be OFF for the
# local Postgres container, which does not serve SSL. Local hosts are detected
# automatically; set DATABASE_SSL=require or DATABASE_SSL=disable to override.
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


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Authentication
# https://docs.djangoproject.com/en/6.0/topics/auth/

# Unauthenticated users hitting a protected view are sent here.
LOGIN_URL = 'login'
# Where users land after a successful login / logout.
LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'login'


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
