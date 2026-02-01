"""
Management command para exportar toda la plataforma.
"""

from django.core.management.base import BaseCommand, CommandError
from apps.migration_system.services import PlatformExportService
from apps.migration_system.models import MigrationJob


class Command(BaseCommand):
    help = 'Exporta toda la plataforma Tuki a un archivo'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            required=True,
            help='Archivo de salida (ej: /tmp/tuki-export.json.gz)'
        )
        parser.add_argument(
            '--include-media',
            action='store_true',
            default=True,
            help='Incluir metadatos de archivos media (default: True)'
        )
        parser.add_argument(
            '--no-media',
            action='store_true',
            help='No incluir archivos media'
        )
        parser.add_argument(
            '--compress',
            action='store_true',
            default=True,
            help='Comprimir con gzip (default: True)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular sin exportar realmente'
        )
        parser.add_argument(
            '--models',
            help='Modelos específicos a exportar (comma-separated)'
        )
        parser.add_argument(
            '--exclude-models',
            help='Modelos a excluir (comma-separated)'
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=1000,
            help='Tamaño de chunks para modelos grandes (default: 1000)'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Iniciando export de plataforma...'))
        self.stdout.write('')
        
        # Crear job para tracking
        job = MigrationJob.objects.create(
            direction='export',
            status='pending',
            config=options
        )
        
        self.stdout.write(f"Job ID: {job.id}")
        self.stdout.write('')
        
        # Dry run
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('[DRY RUN] Simulando export...'))
            self.stdout.write('')
        
        try:
            # Configurar opciones
            export_options = {
                'include_media': not options['no_media'] if options.get('no_media') else options.get('include_media', True),
                'compress': options.get('compress', True),
                'chunk_size': options.get('chunk_size', 1000),
            }
            
            if options.get('models'):
                export_options['models'] = options['models']
            if options.get('exclude_models'):
                export_options['exclude_models'] = options['exclude_models']
            
            # Ejecutar export
            service = PlatformExportService(job=job)
            
            if not options['dry_run']:
                result = service.export_all(
                    output_file=options['output'],
                    **export_options
                )
                
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS('✅ Export completado exitosamente!'))
                self.stdout.write('')
                self.stdout.write('📊 ESTADÍSTICAS:')
                self.stdout.write(f"  - Archivo: {result['file_path']}")
                self.stdout.write(f"  - Tamaño: {result['size_mb']} MB")
                self.stdout.write(f"  - Modelos: {result['statistics']['total_models']}")
                self.stdout.write(f"  - Registros: {result['statistics']['total_records']}")
                self.stdout.write(f"  - Archivos: {result['statistics']['total_files']}")
                self.stdout.write(f"  - Media size: {result['statistics']['total_media_size_mb']} MB")
                self.stdout.write(f"  - Duración: {result['duration_seconds']:.2f}s")
                self.stdout.write('')
            else:
                self.stdout.write(self.style.SUCCESS('[DRY RUN] Export simulado exitosamente'))
                
        except Exception as e:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'❌ Error durante export: {str(e)}'))
            raise CommandError(f'Export falló: {e}')
