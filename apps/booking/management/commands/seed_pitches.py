"""Create the launch pitches and their evening slots for the coming days.

Safe to run again: existing pitches and slots are left as they are, only missing ones are added.
"""

import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.booking.models import Match, Pitch

PITCHES = {
    "Rabat": ["Agdal", "Hay Riad", "Hay El Fath"],
    "Casablanca": ["Maarif", "Oulfa", "Bernoussi"],
    "Marrakesh": ["Gueliz", "Mhamid", "Targa"],
}
# 4 PM to 11 PM, one hour each.
START_HOURS = range(16, 23)


class Command(BaseCommand):
    help = "Create the launch pitches and one-hour evening slots (4-11 PM) for the coming days."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14, help="How many days ahead, starting today.")
        parser.add_argument("--capacity", type=int, default=10)

    def handle(self, *args, days, capacity, **options):
        pitches = []
        for city, names in PITCHES.items():
            for name in names:
                pitch, _ = Pitch.objects.get_or_create(city=city, name=name)
                pitches.append(pitch)

        today = timezone.localdate()
        created = 0
        for offset in range(days):
            date = today + datetime.timedelta(days=offset)
            for pitch in pitches:
                for hour in START_HOURS:
                    _, was_created = Match.objects.get_or_create(
                        pitch=pitch,
                        date=date,
                        start_time=datetime.time(hour),
                        defaults={"end_time": datetime.time(hour + 1), "capacity": capacity},
                    )
                    created += was_created
        self.stdout.write(f"{len(pitches)} pitches; {created} new slots from {today} for {days} day(s).")
