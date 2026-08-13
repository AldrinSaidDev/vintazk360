"""Session handling that Django's settings alone cannot express.

`SESSION_COOKIE_AGE` plus `SESSION_SAVE_EVERY_REQUEST` already gives a rolling
idle window: the cookie is re-stamped on every response, so an hour of silence
expires it. What that cannot do is SAY so. An expired session simply stops
existing, the next request arrives anonymous, and `@login_required` bounces the
user to the login screen with no explanation and nothing in the activity log.
For a dashboard whose log is expected to answer "who was signed in, and when did
they stop?", a sign-out that leaves no trace is a gap.

So the timeout is enforced here instead, from a timestamp in the session. The
middleware owns the decision, which lets it do the two things a cookie expiry
cannot: call `auth.logout()`, which fires `user_logged_out` and writes the audit
row the existing receiver in `signals.py` already knows how to write, and put a
message on the login screen saying what happened.

The cookie age is still set, and deliberately set a little LONGER than the idle
window (see `config/settings/base.py`). Both are enforcing the same hour; the
cookie is the backstop for a session record that outlives its browser, and the
extra couple of minutes are what guarantee the server gets to explain itself
rather than the browser silently dropping the cookie first.
"""
from __future__ import annotations

import time

from django.conf import settings
from django.contrib import auth, messages
from django.contrib.auth.views import redirect_to_login

# Wall-clock seconds of the last request this session made. Stored under a
# private name because it is machinery, not something a view should read.
LAST_ACTIVITY_KEY = '_last_activity'

EXPIRED_MESSAGE = (
    'You were signed out after an hour without activity. '
    'Please sign in again to continue.'
)


class SessionIdleTimeoutMiddleware:
    """Sign a user out after `SESSION_IDLE_TIMEOUT` seconds of inactivity.

    Must sit after `AuthenticationMiddleware` (it reads `request.user`) and
    after `MessageMiddleware` (it writes a message). See the MIDDLEWARE list.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, 'SESSION_IDLE_TIMEOUT', 3600)

    def __call__(self, request):
        if self._tracked(request):
            expired = self._enforce(request)
            if expired is not None:
                return expired
        return self.get_response(request)

    def _tracked(self, request):
        """Whether this request should count as activity.

        Asset requests are excluded. Under `runserver` they come through the
        whole middleware stack, so a single page would otherwise re-stamp the
        session dozens of times and, worse, a browser sitting on a page quietly
        pulling a font would keep an abandoned session alive.
        """
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return False
        if not hasattr(request, 'session'):
            return False

        path = request.path
        for url in (settings.STATIC_URL, settings.MEDIA_URL):
            if url and path.startswith(url if url.startswith('/') else f'/{url}'):
                return False
        return True

    def _enforce(self, request):
        """A redirect to the login screen when the session has gone idle."""
        now = time.time()
        last = request.session.get(LAST_ACTIVITY_KEY)

        if last is not None and now - last > self.timeout:
            # `logout()` flushes the session, so the message has to be added
            # afterwards or it would be flushed with everything else. Adding it
            # after starts a fresh anonymous session to carry it, which is
            # exactly what the login page needs.
            auth.logout(request)
            messages.info(request, EXPIRED_MESSAGE)
            # `next` is the page they were on, so signing back in resumes it.
            # The two-stage render needs nothing special here: async-content.js
            # already watches for a redirected fetch and hands over to the real
            # login screen rather than injecting it into the page frame.
            return redirect_to_login(request.get_full_path())

        request.session[LAST_ACTIVITY_KEY] = now
        return None
