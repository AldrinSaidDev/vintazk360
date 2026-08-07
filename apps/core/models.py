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


class AuditLog(models.Model):
    """One activity trail for the whole system.

    Deliberately NOT KPI-specific: KPI edits, imports, branches, categories,
    logins and user management all write here. One generic table replaces the
    per-feature log tables (``kpi_change_log``, ``user_activity``, …) that
    would otherwise multiply and leave every screen querying a different shape.

    It lives in ``core`` rather than ``apps.kpi`` precisely because it spans
    every app — ``core`` is the layer everything else already imports.

    This is the flat feed a human reads ("what happened this week?").
    ``KpiTargetHistory`` / ``KpiFormulaHistory`` are different: they are domain
    records the scoring engine queries ("what was in force in July?"). A
    formula change writes to both.

    Nothing is edited or deleted here — append only. Write rows with
    ``apps.core.audit.log_action()``.
    """

    class Action(models.TextChoices):
        CREATED = 'created', 'Created'
        UPDATED = 'updated', 'Updated'
        DELETED = 'deleted', 'Deleted'
        IMPORTED = 'imported', 'Imported'
        FORMULA_CHANGED = 'formula_changed', 'Formula changed'
        TARGET_CHANGED = 'target_changed', 'Target changed'
        LOGIN = 'login', 'Logged in'
        LOGOUT = 'logout', 'Logged out'
        # A rejected sign-in has no user to attach to, so the attempted
        # username goes in `entity_name`. This is the only action that is a
        # record of something NOT happening, which is exactly why it is worth
        # keeping: a missing row otherwise means "nobody tried".
        LOGIN_FAILED = 'login_failed', 'Failed sign-in'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_entries',
        help_text='Empty for system actions.',
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_entries',
        help_text='Scope, when the action belongs to a team.',
    )

    action = models.CharField(max_length=50, choices=Action.choices)
    entity_type = models.CharField(
        max_length=50, help_text="'kpi_definition', 'kpi_import_batch', 'user', …"
    )
    entity_id = models.BigIntegerField(null=True, blank=True, help_text="The row's primary key.")
    entity_name = models.CharField(
        max_length=120,
        blank=True,
        help_text='Denormalised on purpose, so the log still reads after the row is deleted.',
    )

    old_values = models.JSONField(null=True, blank=True, help_text='Changed fields, before.')
    new_values = models.JSONField(null=True, blank=True, help_text='Changed fields, after.')

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['team', '-created_at'], name='audit_log_team_recent'),
            models.Index(fields=['entity_type', 'entity_id'], name='audit_log_entity'),
        ]
        verbose_name = 'audit log entry'
        verbose_name_plural = 'audit log'

    def __str__(self):
        who = self.user.get_username() if self.user else 'system'
        return f'{who} {self.action} {self.entity_type} {self.entity_name}'.strip()
