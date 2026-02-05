"""
Management command to create a test reservation code for WhatsApp flow.

Usage:
    python manage.py create_reservation_code
    python manage.py create_reservation_code --experience "Test Tour"

The code is always created with RES- prefix for proper detection by the message parser.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import hashlib
import uuid

from apps.whatsapp.models import WhatsAppReservationCode
from apps.experiences.models import Experience


class Command(BaseCommand):
    help = 'Create a test reservation code with RES- prefix for WhatsApp flow testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--experience',
            type=str,
            default='Test Tour',
            help='Experience title or slug to link (default: Test Tour)',
        )
        parser.add_argument(
            '--free',
            action='store_true',
            help='Create code for free activity (total=0, customer confirms with SI)',
        )

    def handle(self, *args, **options):
        exp_title = options['experience']
        experience = (
            Experience.objects.filter(title__icontains=exp_title).first()
            or Experience.objects.filter(slug__icontains=exp_title).first()
        )
        if not experience:
            self.stdout.write(
                self.style.ERROR(f'Experience not found: {exp_title}')
            )
            self.stdout.write('Available experiences:')
            for e in Experience.objects.all()[:10]:
                self.stdout.write(f'  - {e.title} (slug: {e.slug})')
            return

        date_str = timezone.now().strftime('%Y%m%d')
        unique_hash = hashlib.sha256(
            str(uuid.uuid4()).encode()
        ).hexdigest()[:8].upper()
        code_str = f'RES-TEST-{date_str}-{unique_hash}'

        is_free = options.get('free', False)
        total = 0 if is_free else 50000
        code = WhatsAppReservationCode.objects.create(
            code=code_str,
            experience=experience,
            status='pending',
            checkout_data={
                'participants': {'adults': 2, 'children': 0},
                'date': '2026-02-15',
                'time': '10:00',
                'total_price': total,
                'pricing': {'total': total, 'currency': 'CLP'},
            },
            expires_at=timezone.now() + timedelta(hours=24),
        )

        self.stdout.write(self.style.SUCCESS(f'Created reservation code: {code.code}'))
        self.stdout.write(f'  Experience: {experience.title}')
        if is_free:
            self.stdout.write('  Type: FREE (customer confirms with SI)')
        self.stdout.write('')
        self.stdout.write('Send this message to the Tuki WhatsApp number:')
        self.stdout.write(f'  Hola! Quiero reservar {code.code}')
        self.stdout.write('')
