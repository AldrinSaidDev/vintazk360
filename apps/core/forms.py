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

from .access import assignable_roles, assignable_teams, can_manage_role
from .models import Team, UserProfile
from .validators import (
    EMPLOYEE_ID_EXAMPLE,
    EMPLOYEE_ID_HTML_PATTERN,
    validate_employee_id,
)

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
            'class': f'{INPUT_CLASSES} pr-11',
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
        # An Admin administers accounts up to their own level. The role, teams
        # and active flag of an account holding a role they cannot assign are
        # closed to them: a Super Admin's, or a Finance or HR account, whose
        # department they cannot reach themselves. Otherwise an Admin could
        # simply demote every Super Admin and take the top of the system, which
        # is granting themselves the role arrived at from the other end. The
        # name, email and password stay editable: those are housekeeping.
        self.role_locked = target is not None and not can_manage_role(actor, target)

        if self.editing_self or self.role_locked:
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

        if self.editing_self or self.role_locked:
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

    # The shape is YYYY-MM-NNN (hire year, hire month, then three issued digits).
    # The `pattern` and `maxlength` attributes are the same rule in the browser's
    # dialect and turn a typo into a message before the round trip;
    # `validate_employee_id` is what actually decides, since a hand-made POST
    # never meets the input.
    #
    # No `max_length` on the FIELD, deliberately: the validator already bounds
    # the length, and a second rule saying "at most 11 characters" only stacks a
    # redundant sentence under the one that explains the format.
    username = forms.CharField(
        label='Employee ID',
        validators=[validate_employee_id],
        help_text=f'Hire year, hire month, then three digits. For example {EMPLOYEE_ID_EXAMPLE}.',
        widget=forms.TextInput(attrs={
            'placeholder': EMPLOYEE_ID_EXAMPLE,
            'pattern': EMPLOYEE_ID_HTML_PATTERN,
            'inputmode': 'numeric',
            'autocomplete': 'off',
            'maxlength': '11',
        }),
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
        # Re-checked after the strip, because the field validators ran on the
        # raw value: " 2026-07-462 " would otherwise be stored trimmed but
        # never actually checked in the shape it is stored in.
        validate_employee_id(username)
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
        self._apply(user)
        # Only when the details were actually left out. The name and email are
        # optional on this form precisely so an administrator can add a dozen
        # colleagues in one sitting, and THAT is what the setup card is for: the
        # person is asked for what nobody else supplied. An administrator who
        # typed all three has already answered it, so asking them again the
        # first time they sign in is a form with nothing left to fill in.
        #
        # Deliberately NOT keyed off "has this account signed in yet": whether
        # somebody has been here before is a different question from whether
        # their details are known, and using it as the basis showed the card to
        # every new account however completely it had been set up.
        UserProfile.objects.filter(user=user).update(needs_setup=self.details_missing)
        return user

    @property
    def details_missing(self):
        """True when the administrator left the person's own details blank."""
        data = self.cleaned_data
        return not all(
            (data.get(field) or '').strip()
            for field in ('first_name', 'last_name', 'email')
        )


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
                widget=forms.PasswordInput(attrs={
                    'autocomplete': 'current-password',
                    # Room for the visibility toggle, same as `_password_field`.
                    # It reads back what you typed, which is the whole reason a
                    # mistyped current password is worth being able to check.
                    'class': f'{INPUT_CLASSES} pr-11',
                }),
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


class AccountSetupForm(forms.Form):
    """What a newly created account fills in the first time it signs in.

    The other side of ``CreateUserForm``: an administrator types an Employee ID
    and generates a password, and the person themselves supplies the details
    that are theirs to give. Name and email are REQUIRED here even though they
    are optional on the create form, which is the whole point of the split. The
    administrator does not have to know a colleague's email to make them an
    account, and the account does not get to stay nameless either.

    Changing the password is optional and deliberately so. It is the sensible
    thing to do with a password that was generated by somebody else and read out
    or pasted into a chat, but forcing it would mean a person who has already
    saved the generated one into a password manager has to invent a second.
    Leaving both boxes empty keeps the one they signed in with.
    """

    first_name = forms.CharField(label='First name', max_length=150)
    last_name = forms.CharField(label='Last name', max_length=150)
    email = forms.EmailField(label='Email')
    password1 = _password_field('New password')
    password2 = _password_field('Confirm new password', role='confirm')

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Empty means "keep the password I signed in with", so neither box can
        # be required. `clean_password2` is what pairs them up once one is used.
        self.fields['password1'].required = False
        self.fields['password2'].required = False
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', INPUT_CLASSES)

    @property
    def password_fields(self):
        """The two password boxes, for the template's own section of the card."""
        return [self['password1'], self['password2']]

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if not password1 and not password2:
            return ''
        if not password1:
            raise forms.ValidationError('Enter the new password in both boxes.')
        if password1 != password2:
            raise forms.ValidationError('The two passwords do not match.')
        password_validation.validate_password(password2, self.user)
        return password2

    @property
    def password_changed(self):
        """True when a new password was actually set.

        The view reads this to know it has to rotate the session hash, which is
        what stops the change signing the person straight back out.
        """
        return bool(self.cleaned_data.get('password2'))

    @transaction.atomic
    def save(self):
        user = self.user
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        if self.password_changed:
            user.set_password(self.cleaned_data['password2'])
        user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.needs_setup = False
        profile.save(update_fields=['needs_setup'])
        return user
