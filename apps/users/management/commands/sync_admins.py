"""Promote the phones in GLOCAL_ADMIN_PHONES to staff. Runs at every start; never creates accounts.

The person creates an account in the app, then is promoted here; they sign in to /admin/ with
the same phone number and password.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.users.models import User
from apps.users.phone import InvalidPhone, normalize_phone


class Command(BaseCommand):
    help = "Promote the phones listed in GLOCAL_ADMIN_PHONES to staff and superuser."

    def handle(self, *args, **options):
        for raw in settings.GLOCAL_ADMIN_PHONES:
            try:
                phone = normalize_phone(raw)
            except InvalidPhone:
                self.stderr.write(f"Skipped an invalid number in GLOCAL_ADMIN_PHONES: {raw!r}")
                continue
            updated = User.objects.filter(phone=phone).update(is_staff=True, is_superuser=True)
            if updated:
                self.stdout.write(f"Admin: {phone}")
            else:
                self.stdout.write(f"No account yet for {phone}; sign in once in the app, then restart.")
