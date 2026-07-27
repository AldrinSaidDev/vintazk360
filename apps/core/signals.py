"""Ensure every User has a UserProfile.

Without a profile a user has no role/team, so ``accessible_teams`` grants
them nothing (they only see the shared Dashboard). Auto-creating the profile
on user creation means admins can assign role/teams immediately.
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        role = UserProfile.Role.SUPERADMIN if instance.is_superuser else UserProfile.Role.USER
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={'role': role},
        )
