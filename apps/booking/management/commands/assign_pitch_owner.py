"""Make a signed-up person the owner of a pitch (they then see its booking requests in the app)."""

from django.core.management.base import BaseCommand, CommandError

from apps.booking.models import Pitch
from apps.users.models import User
from apps.users.phone import InvalidPhone, normalize_phone


class Command(BaseCommand):
    help = "Make the account with this phone the owner of a pitch."

    def add_arguments(self, parser):
        parser.add_argument("--phone", required=True)
        parser.add_argument("--city", required=True)
        parser.add_argument("--pitch", required=True, help="The pitch's name, e.g. 'Agdal'.")

    def handle(self, *args, phone, city, pitch, **options):
        try:
            phone = normalize_phone(phone)
        except InvalidPhone as error:
            raise CommandError(str(error.message)) from None
        user = User.objects.filter(phone=phone).first()
        if user is None:
            raise CommandError(f"No account for {phone}. They need to sign in to the app once first.")
        found = Pitch.objects.filter(city__iexact=city, name__iexact=pitch).first()
        if found is None:
            raise CommandError(f"No pitch named {pitch!r} in {city!r}.")
        found.owner = user
        found.save(update_fields=["owner"])
        self.stdout.write(f"{user} now owns {found}.")
