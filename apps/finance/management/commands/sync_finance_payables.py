from django.core.management.base import BaseCommand

from apps.finance.services import set_next_payment_dates, sync_all_payables


class Command(BaseCommand):
    help = "Sync organizer and creator payables into the finance ledger."

    def handle(self, *args, **options):
        result = sync_all_payables()
        set_next_payment_dates()
        self.stdout.write(self.style.SUCCESS(f"Finance sync complete: {result}"))
