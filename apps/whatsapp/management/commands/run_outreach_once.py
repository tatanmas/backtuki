"""
Ejecuta una ronda de outreach (primer mensaje) para todos los grupos con outreach activado.

Útil cuando:
- Celery Beat no está corriendo y quieres ejecutar el envío manualmente.
- Quieres probar el envío automático (ej. python manage.py run_outreach_once).
- Usas cron en lugar de Beat: */12 * * * * cd /app && python manage.py run_outreach_once

El envío automático por Celery requiere:
- Celery Beat corriendo (programa la tarea cada 12 min).
- Celery Worker corriendo y consumiendo la cola 'default'.
"""
import logging

from django.core.management.base import BaseCommand

from apps.whatsapp.models import GroupOutreachConfig
from apps.whatsapp.services.group_outreach_service import run_outreach_for_config

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run one outreach cycle for all enabled group configs (same as Celery task run_group_outreach)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only show which configs would run, do not send',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        configs = list(GroupOutreachConfig.objects.filter(enabled=True).select_related('group'))
        if not configs:
            self.stdout.write(self.style.WARNING('No hay configuraciones de outreach activadas.'))
            return
        self.stdout.write(f'Configs con outreach activado: {len(configs)}')
        for c in configs:
            self.stdout.write(f'  - {c.group.name} (id={c.group_id})')
        if dry_run:
            self.stdout.write(self.style.SUCCESS('Dry-run: no se envió ningún mensaje.'))
            return
        total_sent = 0
        total_errors = 0
        for config in configs:
            try:
                result = run_outreach_for_config(config)
                sent = result.get('sent', 0)
                errors = result.get('errors', 0)
                total_sent += sent
                total_errors += errors
                if sent or errors:
                    self.stdout.write(
                        f'  {config.group.name}: sent={sent}, errors={errors}'
                    )
            except Exception as e:
                logger.exception('Outreach run failed for config %s: %s', config.id, e)
                total_errors += 1
                self.stdout.write(self.style.ERROR(f'  {config.group.name}: exception {e}'))
        self.stdout.write(
            self.style.SUCCESS(f'Listo. Total enviados={total_sent}, errores={total_errors}')
        )
