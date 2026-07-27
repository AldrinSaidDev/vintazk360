from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Team, UserProfile

User = get_user_model()


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order')
    list_editable = ('order',)
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug')


class UserProfileInline(admin.StackedInline):
    """Edit role + teams right on the User page."""
    model = UserProfile
    can_delete = False
    filter_horizontal = ('teams',)
    extra = 0
    verbose_name_plural = 'Role & Teams'


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = BaseUserAdmin.list_display + ('get_role',)

    @admin.display(description='Role')
    def get_role(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.get_role_display() if profile else '—'


# Re-register User with the profile inline attached.
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
