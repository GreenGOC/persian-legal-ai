from django.core.management.base import BaseCommand
from django.db import transaction

from ...models import LegalRelationship

class Command(BaseCommand):
    help = "Delete all legal relationships and their contexts."

    @transaction.atomic
    def handle(self, *args, **options):
        count = LegalRelationship.objects.count()
        if count == 0:
            self.stdout.write(self.style.WARNING("No legal relationships found."))
            return

        LegalRelationship.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} legal relationships."))