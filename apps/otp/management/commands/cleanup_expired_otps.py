from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.otp.models import OTP
from apps.otp.services import OTPService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Limpia códigos OTP expirados de la base de datos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué se eliminaría sin hacer cambios reales',
        )
        parser.add_argument(
            '--older-than-hours',
            type=int,
            default=24,
            help='Eliminar códigos más antiguos que X horas (default: 24)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        older_than_hours = options['older_than_hours']

        self.stdout.write(
            self.style.SUCCESS(f'🔍 Iniciando limpieza de códigos OTP...')
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('🔥 MODO DRY-RUN: No se realizarán cambios reales')
            )

        # Obtener códigos a eliminar
        cutoff_time = timezone.now() - timezone.timedelta(hours=older_than_hours)
        
        expired_codes = OTP.objects.filter(
            expires_at__lt=timezone.now()
        )
        
        old_codes = OTP.objects.filter(
            created_at__lt=cutoff_time
        )

        total_expired = expired_codes.count()
        total_old = old_codes.count()
        total_to_delete = expired_codes.union(old_codes).count()

        self.stdout.write(f'📊 Códigos encontrados:')
        self.stdout.write(f'   • Expirados: {total_expired}')
        self.stdout.write(f'   • Antiguos (>{older_than_hours}h): {total_old}')
        self.stdout.write(f'   • Total a eliminar: {total_to_delete}')

        if total_to_delete == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ No hay códigos para eliminar')
            )
            return

        if dry_run:
            # Mostrar detalles sin eliminar
            self.stdout.write('\n🔍 Detalles de códigos que se eliminarían:')
            
            codes_to_show = expired_codes.union(old_codes)[:10]  # Mostrar solo 10
            for otp in codes_to_show:
                status = "EXPIRADO" if otp.is_expired else "ANTIGUO"
                self.stdout.write(
                    f'   • {otp.email} - {otp.get_purpose_display()} - {status} - {otp.created_at}'
                )
            
            if total_to_delete > 10:
                self.stdout.write(f'   ... y {total_to_delete - 10} más')

        else:
            # Realizar limpieza real
            try:
                deleted_count = OTPService.cleanup_expired_codes()
                
                # También eliminar códigos antiguos
                old_deleted = old_codes.delete()[0]
                total_deleted = deleted_count + old_deleted

                self.stdout.write(
                    self.style.SUCCESS(f'✅ Limpieza completada: {total_deleted} códigos eliminados')
                )
                
                logger.info(f'OTP cleanup completed: {total_deleted} codes deleted')

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error durante la limpieza: {str(e)}')
                )
                logger.error(f'Error in OTP cleanup: {str(e)}')
                raise

        # Estadísticas finales
        remaining_codes = OTP.objects.count()
        active_codes = OTP.objects.filter(
            is_used=False,
            expires_at__gt=timezone.now()
        ).count()

        self.stdout.write(f'\n📈 Estadísticas finales:')
        self.stdout.write(f'   • Códigos restantes: {remaining_codes}')
        self.stdout.write(f'   • Códigos activos: {active_codes}')
        
        self.stdout.write(
            self.style.SUCCESS('🎉 Proceso completado exitosamente')
        )
