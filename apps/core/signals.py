"""Signal receivers for core: profile creation, and the authentication trail.

Without a profile a user has no role/team, so ``accessible_teams`` grants
them nothing (they only see the shared Dashboard). Auto-creating the profile
on user creation means admins can assign role/teams immediately.
"""
from django.conf import settings
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.db.models.signals import post_save
from django.dispatch import receiver

from .audit import log_action
from .models import AuditLog, UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        role = UserProfile.Role.SUPERADMIN if instance.is_superuser else UserProfile.Role.USER
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={'role': role},
        )


# --- authentication trail ---------------------------------------------------
#
# `AuditLog.Action` has carried LOGIN and LOGOUT since the table was built, but
# nothing wrote them, so the Logs page could never answer "who signed in?" —
# the most basic question a log gets asked. Django already fires these signals;
# all that was missing was the receivers.


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    log_action(
        request,
        action=AuditLog.Action.LOGIN,
        entity_type='session',
        entity_name=user.get_username(),
        user=user,
    )


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    # Django fires this even when nobody was signed in (an anonymous POST to
    # /logout/), and a logout with no user is not an event worth a row.
    if user is None:
        return
    log_action(
        request,
        action=AuditLog.Action.LOGOUT,
        entity_type='session',
        entity_name=user.get_username(),
        user=user,
    )


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request=None, **kwargs):
    # `credentials` is already scrubbed of the password by Django's
    # `sensitive_variables` handling, but only the username is read here so a
    # future extra field cannot leak into the log by accident.
    log_action(
        request,
        action=AuditLog.Action.LOGIN_FAILED,
        entity_type='session',
        entity_name=str(credentials.get('username', ''))[:120],
    )
