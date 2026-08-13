"""Forms for the Users screen: creating, editing, and re-keying an account.

A user is two rows, not one: the Django ``User`` (Employee ID, name, email,
active flag) and its ``UserProfile`` (role, teams). These forms are plain
``forms.Form`` rather than a ``ModelForm`` for that reason. A ModelForm would
own one of the two and leave the other to be patched in the view, which is
where the two drift apart.

What may be assigned is decided in ``apps/core/access.py``, not here: the role
choices and the team queryset both come from the actor, so a team-scoped Admin
cannot create an account with more reach than their own. See
``assignable_roles`` for why that matters.
"""

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.db import transaction

from .access import assignable_roles, assignable_teams
from .models import Team, UserProfile

# Shared with the hand-written inputs on the rest of the screens.
INPUT_CLASSES = (
    'w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm '
    'focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20'
)


def _password_field(label, help_text='', role='main'):
    """A password box.

    ``role`` marks it for ``static/js/password-checklist.js``, which ticks the
    policy rules as they are met. It reads the pair out of the surrounding
    ``[data-password-checklist]`` element rather than by id, since the Users
    screen renders one Set password form per row and the ids repeat.
    """
    return forms.CharField(
        label=label,
        help_text=help_text,
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password',
            f'data-password-{role}': '',
        }),
    )


class BaseUserForm(forms.Form):
    """The fields create and edit agree on."""

    first_name = forms.CharField(label='First name', max_length=150, required=False)
    last_name = forms.CharField(label='Last name', max_length=150, required=False)
    email = forms.EmailField(label='Email', required=False)
    role = forms.ChoiceField(label='Role')
    teams = forms.ModelMultipleChoiceField(
        label='Teams',
        queryset=Team.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'h-4 w-4 shrink-0 rounded border-slate-300 accent-brand focus:ring-brand',
        }),
    )

    def __init__(self, *args, actor, target=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.target = target
        # Editing your own account is allowed, changing your own role or team
        # access from here is not: an Admin who demotes themselves by accident
        # cannot undo it, because the screen that would undo it is the one they
        # just lost. Their own password and profile stay in Settings.
        self.editing_self = target is not None and target.pk == actor.pk

        if self.editing_self:
            del self.fields['role']
            del self.fields['teams']
        else:
            self.fields['role'].choices = assignable_roles(actor)
            self.fields['teams'].queryset = assignable_teams(actor)
            # `static/js/role-teams.js` hides the Teams block while one of these
            # roles is selected, since their reach is every team and whatever is
            # ticked would be ignored. The list is emitted from the model rather
            # than written out in the script, so the two cannot drift apart.
            self.fields['role'].widget.attrs.update({
                'data-role-select': '',
                'data-all-team-roles': ','.join(sorted(UserProfile.ALL_TEAM_ROLES)),
            })

        for name, field in self.fields.items():
            if name != 'teams':
                field.widget.attrs.setdefault('class', INPUT_CLASSES)

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        # Super Admin, Admin and Viewer reach every team, so their `teams` M2M is
        # ignored. Every other role reaches ONLY what is assigned here, and
        # saving one with no teams creates an account that can open nothing.
        if 'teams' in self.errors:
            # It already failed on its own, most likely a team the actor cannot
            # assign. Adding "pick at least one" underneath reads as a second,
            # contradictory problem.
            return cleaned
        if role and role not in UserProfile.ALL_TEAM_ROLES and not cleaned.get('teams'):
            self.add_error(
                'teams',
                'Pick at least one team. This role reaches only the teams you assign here.',
            )
        return cleaned

    def _apply(self, user):
        """Write the fields onto the user and their profile."""
        data = self.cleaned_data
        user.first_name = data.get('first_name', '')
        user.last_name = data.get('last_name', '')
        user.email = data.get('email', '')
        user.save()

        if self.editing_self:
            return user

        # The post_save signal creates the profile, but get_or_create keeps
        # this working for an account created before that signal existed.
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = data['role']
        profile.save(update_fields=['role'])
        profile.teams.set(data.get('teams') or [])
        return user


class CreateUserForm(BaseUserForm):
    """A new account, with its first password set by the administrator."""

    username = forms.CharField(
        label='Employee ID',
        max_length=150,
        help_text='This is what the person signs in with, e.g. 2026-01-439.',
    )
    # No help text on either: the live checklist beside the fields lists the
    # same rules and ticks them off as they are met.
    password1 = _password_field('Password')
    password2 = _password_field('Confirm password', role='confirm')

    field_order = [
        'username', 'first_name', 'last_name', 'email',
        'role', 'teams', 'password1', 'password2',
    ]

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        # Django's default backend matches the username exactly, but two
        # accounts differing only in case would be indistinguishable to a
        # person reading the table, so both are refused.
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('An account with that Employee ID already exists.')
        return username

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('The two passwords do not match.')
        if password2:
            password_validation.validate_password(password2)
        return password2

    @transaction.atomic
    def save(self):
        user = get_user_model().objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password2'],
        )
        return self._apply(user)


class EditUserForm(BaseUserForm):
    """An existing account. The Employee ID is not editable.

    It is the sign-in credential and the name on every audit entry, so
    renaming it would rewrite how the log reads. Deactivate and create a new
    account instead.
    """

    @classmethod
    def initial_for(cls, user):
        profile = getattr(user, 'profile', None)
        return {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'role': profile.role if profile else UserProfile.Role.USER,
            'teams': list(profile.teams.all()) if profile else [],
        }

    @transaction.atomic
    def save(self):
        return self._apply(self.target)


class AdminPasswordForm(forms.Form):
    """Set an account's password from the Users screen.

    Django's ``SetPasswordForm`` is the same shape, but it is written for the
    account holder changing their own; the copy here says an administrator is
    setting someone else's, which is a different thing to confirm.

    It covers BOTH cases, because the difference between them is one field and
    one flash message rather than a different screen. When the target is the
    actor the form asks for the current password first, exactly as Settings
    does: an administrator setting somebody else's password cannot be expected
    to know the old one, but a session left open on your own account must not
    be enough to re-key it. ``is_self`` is what the view reads to know it has
    to rotate the session hash after saving.
    """

    password1 = _password_field('New password')
    password2 = _password_field('Confirm new password', role='confirm')

    def __init__(self, *args, target, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.target = target
        self.actor = actor
        self.is_self = actor is not None and actor.pk == target.pk
        if self.is_self:
            self.fields['current_password'] = forms.CharField(
                label='Current password',
                strip=False,
                widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
            )
            # Declared fields come first otherwise, and being asked to confirm
            # the old password below the new one reads as an afterthought.
            self.order_fields(['current_password', 'password1', 'password2'])
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', INPUT_CLASSES)

    def clean_current_password(self):
        current = self.cleaned_data.get('current_password')
        if current and not self.target.check_password(current):
            raise forms.ValidationError('That is not your current password.')
        return current

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('The two passwords do not match.')
        if password2:
            password_validation.validate_password(password2, self.target)
        return password2

    def save(self):
        self.target.set_password(self.cleaned_data['password2'])
        self.target.save(update_fields=['password'])
        return self.target
