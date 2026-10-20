from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm
from django.utils.translation import gettext_lazy as _

from . import services
from .models import User
from .phone import InvalidPhone, normalize_phone


class UserCreationForm(AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("phone",)

    def clean_phone(self):
        try:
            return normalize_phone(self.cleaned_data["phone"])
        except InvalidPhone as error:
            raise self.error_class([error.message]) from None


class UserChangeForm(BaseUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    ordering = ["-created_at"]
    list_display = ["phone", "name", "age_range", "gender", "is_staff", "is_active", "created_at"]
    list_filter = ["is_staff", "is_active", "gender", "age_range"]
    search_fields = ["phone", "name"]
    readonly_fields = ["created_at", "updated_at", "last_login"]
    fieldsets = [
        (None, {"fields": ["phone", "password"]}),
        (_("Profile"), {"fields": ["name", "age_range", "gender"]}),
        (_("Access"), {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
        (_("Dates"), {"fields": ["last_login", "created_at", "updated_at"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["phone", "usable_password", "password1", "password2"]}),
    ]
    actions = ["remove_access"]

    @admin.action(description=_("Remove access (disable and sign out everywhere)"))
    def remove_access(self, request, queryset):
        count = 0
        for user in queryset.exclude(pk=request.user.pk):
            services.remove_access(user)
            count += 1
        self.message_user(request, _("%(count)d account(s) disabled.") % {"count": count}, messages.SUCCESS)
