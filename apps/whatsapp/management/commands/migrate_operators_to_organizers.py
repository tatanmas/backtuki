"""Management command to migrate existing operators to link with organizers."""
from django.core.management.base import BaseCommand
from apps.whatsapp.models import TourOperator
from apps.organizers.models import Organizer
from apps.experiences.models import Experience
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate existing TourOperators to link with Organizers based on experiences'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        self.stdout.write('Starting operator-organizer migration...')
        
        # 1. Para cada Organizer con experiencias, crear TourOperator si no existe
        organizers_with_experiences = Organizer.objects.filter(
            has_experience_module=True,
            experiences__isnull=False
        ).distinct()
        
        created_count = 0
        for organizer in organizers_with_experiences:
            # Verificar si ya tiene un operador
            existing_operator = TourOperator.objects.filter(organizer=organizer).first()
            
            if not existing_operator:
                if not dry_run:
                    operator = TourOperator.objects.create(
                        name=organizer.name,
                        contact_name=organizer.representative_name or '',
                        contact_phone=organizer.representative_phone or '',
                        contact_email=organizer.representative_email or '',
                        organizer=organizer,
                        is_system_created=True,
                        is_active=True
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Created operator "{operator.name}" for organizer "{organizer.name}"')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'[DRY RUN] Would create operator for organizer "{organizer.name}"')
                    )
                created_count += 1
        
        # 2. Intentar vincular operadores existentes a organizadores por nombre/email
        unlinked_operators = TourOperator.objects.filter(organizer__isnull=True, is_active=True)
        linked_count = 0
        
        for operator in unlinked_operators:
            # Buscar organizador por nombre exacto
            organizer = Organizer.objects.filter(name=operator.name).first()
            
            # Si no se encuentra por nombre, buscar por email
            if not organizer and operator.contact_email:
                organizer = Organizer.objects.filter(
                    representative_email__iexact=operator.contact_email
                ).first()
            
            if organizer:
                if not dry_run:
                    operator.organizer = organizer
                    operator.is_system_created = False  # Ya existía, no fue auto-creado
                    operator.save(update_fields=['organizer', 'is_system_created'])
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Linked operator "{operator.name}" to organizer "{organizer.name}"')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'[DRY RUN] Would link operator "{operator.name}" to organizer "{organizer.name}"')
                    )
                linked_count += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'\nMigration completed:\n'
            f'  - Created operators: {created_count}\n'
            f'  - Linked existing operators: {linked_count}\n'
            f'  - Total operators processed: {created_count + linked_count}'
        ))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nThis was a DRY RUN. Run without --dry-run to apply changes.'))

