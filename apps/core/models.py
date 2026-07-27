from django.conf import settings
from django.db import models


class Team(models.Model):
    """A Line of Business (LOB) / team.

    One row per LOB screen. ``slug`` maps to the LOB app's URL namespace
    (e.g. ``operations`` → ``operations:index``) and drives both the sidebar
    links a user sees and the per-view access guard. Admin-managed.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Matches the LOB app / URL namespace, e.g. 'operations'.",
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Sidebar sort order (lower shows first).",
    )

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """Role + team assignment for a user.

    Access model (see also the ``core.access`` helpers):
      * SUPERADMIN / ADMIN — see every team (the ``teams`` M2M is ignored).
      * MANAGER — sees the multiple teams in ``teams``.
      * USER — sees only their single team (first of ``teams``).

    Everyone always sees the shared Dashboard regardless of role.
    """

    class Role(models.TextChoices):
        SUPERADMIN = 'superadmin', 'Super Admin'
        ADMIN = 'admin', 'Admin'
        MANAGER = 'manager', 'Manager'
        USER = 'user', 'User'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.USER,
    )
    teams = models.ManyToManyField(
        Team,
        blank=True,
        related_name='members',
        help_text=(
            "Teams this user can access. Ignored for Super Admin / Admin "
            "(they see everything). A plain User should have exactly one."
        ),
    )

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"

    @property
    def sees_all_teams(self):
        """Super Admin and Admin see every team."""
        return self.role in {self.Role.SUPERADMIN, self.Role.ADMIN}
