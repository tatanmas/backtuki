"""
Management command para importar datos desde archivo export.
"""

from django.core.management.base import BaseCommand, CommandError
from apps.migration_system.services import PlatformImportService
from apps.migration_system.models import MigrationJob


class Command(BaseCommand):
    help = 'Importa datos desde un archivo export de plataforma'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--input',
            required=True,
            help='Archivo de entrada (ej: /tmp/tuki-export.json.gz)'
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            default=True,
            help='Verificar integridad post-import (default: True)'
        )
        parser.add_argument(
            '--no-verify',
            action='store_true',
            help='No verificar integridad'
        )
        parser.add_argument(
            '--create-checkpoint',
            action='store_true',
            default=True,
            help='Crear checkpoint antes de importar (default: True)'
        )
        parser.add_argument(
            '--no-checkpoint',
            action='store_true',
            help='No crear checkpoint'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular sin importar realmente'
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Sobrescribir registros existentes'
        )
        parser.add_argument(
            '--merge',
            action='store_true',
            help='Merge con registros existentes (actualizar solo campos no nulos)'
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            default=True,
            help='Saltar registros que ya existen (default: True)'
        )
        parser.add_argument(
            '--skip-media',
            action='store_true',
            help='No descargar archivos media'
        )
        parser.add_argument(
            '--auto-rollback',
            action='store_true',
            default=True,
            help='Rollback automático si falla (default: True)'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Iniciando import de plataforma...'))
        self.stdout.write('')
        
        # Crear job para tracking
        job = MigrationJob.objects.create(
            direction='import',
            status='pending',
            config=options
        )
        
        self.stdout.write(f"Job ID: {job.id}")
        self.stdout.write('')
        
        # Warnings
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('[DRY RUN] Simulando import...'))
        
        if options.get('no_checkpoint'):
            self.stdout.write(self.style.WARNING('⚠️  No se creará checkpoint. No podrás hacer rollback.'))
        
        if options.get('overwrite'):
            self.stdout.write(self.style.WARNING('⚠️  Modo overwrite: se sobrescribirán registros existentes'))
        
        self.stdout.write('')
        
        try:
            # Configurar opciones
            import_options = {
                'dry_run': options.get('dry_run', False),
                'create_checkpoint': not options.get('no_checkpoint', False) and options.get('create_checkpoint', True),
                'verify': not options.get('no_verify', False) and options.get('verify', True),
                'overwrite': options.get('overwrite', False),
                'merge': options.get('merge', False),
                'skip_existing': options.get('skip_existing', True),
                'skip_media': options.get('skip_media', False),
                'auto_rollback': options.get('auto_rollback', True),
            }
            
            # Ejecutar import
            service = PlatformImportService(job=job)
            result = service.import_all(
                input_data=options['input'],
                **import_options
            )
            
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✅ Import completado exitosamente!'))
            self.stdout.write('')
            self.stdout.write('📊 RESULTADOS:')
            
            if result.get('dry_run'):
                self.stdout.write('  [DRY RUN] Simulación completada')
            
            self.stdout.write(f"  - Duración: {result['duration_seconds']:.2f}s")
            
            if result.get('checkpoint_id'):
                self.stdout.write(f"  - Checkpoint ID: {result['checkpoint_id']}")
            
            self.stdout.write('')
            self.stdout.write('  Registros importados por modelo:')
            for model_path, count in result['imported_counts'].items():
                self.stdout.write(f"    • {model_path}: {count}")
            
            self.stdout.write('')
            
        except Exception as e:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'❌ Error durante import: {str(e)}'))
            
            if options.get('auto_rollback') and not options.get('no_checkpoint'):
                self.stdout.write(self.style.WARNING('Rollback automático debería haberse ejecutado'))
            
            raise CommandError(f'Import falló: {e}')
