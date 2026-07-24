"""
Settings package.

``DJANGO_SETTINGS_MODULE`` should point at one of the concrete modules in this
package — ``config.settings.dev`` (default) or ``config.settings.prod``. The
project's entrypoints (manage.py, wsgi.py, asgi.py) default to ``dev`` so a
fresh clone runs with no extra configuration; production sets the env var to
``config.settings.prod``.
"""
