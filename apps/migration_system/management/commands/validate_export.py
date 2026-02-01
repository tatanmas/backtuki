"""
Django management command para validar un archivo de export antes de importar.
"""

import sys
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from apps.migration_system.services.import_service import PlatformImportService
from apps.migration_system.services.export_service import PlatformExportService
from apps.migration_system.utils import calculate_file_checksum_from_path


class Command(BaseCommand):
    help = 'Valida un archivo de export antes de importarlo'

    def add_arguments(self, parser):
        parser.add_argument(
            'export_file',
            type=str,
            help='Ruta al archivo de export (.tar.gz o .json.gz)'
        )
        parser.add_argument(
            '--check-checksums',
            action='store_true',
            help='Validar checksums MD5 de archivos media'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Mostrar detalles adicionales'
        )

    def handle(self, *args, **options):
        export_file = options['export_file']
        check_checksums = options['check_checksums']
        verbose = options['verbose']
        
        self.stdout.write(self.style.MIGRATE_HEADING('=== Validación de Export ===\n'))
        
        # Verificar que el archivo existe
        file_path = Path(export_file)
        if not file_path.exists():
            raise CommandError(f"Archivo no encontrado: {export_file}")
        
        self.stdout.write(f"Archivo: {file_path}")
        self.stdout.write(f"Tamaño: {file_path.stat().st_size / (1024*1024):.2f} MB\n")
        
        # Crear servicio de import para validación
        service = PlatformImportService()
        
        # Paso 1: Cargar el archivo
        self.stdout.write(self.style.WARNING('[1/4] Cargando archivo...'))
        try:
            export_data = service.load_from_file(str(file_path))
            self.stdout.write(self.style.SUCCESS('✓ Archivo cargado correctamente\n'))
        except Exception as e:
            raise CommandError(f"Error cargando archivo: {e}")
        
        # Paso 2: Validar formato
        self.stdout.write(self.style.WARNING('[2/4] Validando formato...'))
        if not service.validate_export_format(export_data):
            raise CommandError("Formato de export inválido")
        self.stdout.write(self.style.SUCCESS('✓ Formato válido\n'))
        
        # Paso 3: Verificar estadísticas
        self.stdout.write(self.style.WARNING('[3/4] Verificando estadísticas...'))
        stats = export_data.get('statistics', {})
        
        total_models = stats.get('total_models', 0)
        total_records = stats.get('total_records', 0)
        total_files = stats.get('total_files', 0)
        
        self.stdout.write(f"  Modelos: {total_models}")
        self.stdout.write(f"  Registros: {total_records:,}")
        self.stdout.write(f"  Archivos media: {total_files}")
        
        # Mostrar counts por modelo si verbose
        if verbose:
            self.stdout.write("\n  Registros por modelo:")
            for key, value in stats.items():
                if key.startswith('count_'):
                    model_name = key.replace('count_', '')
                    self.stdout.write(f"    - {model_name}: {value:,}")
        
        self.stdout.write(self.style.SUCCESS('\n✓ Estadísticas válidas\n'))
        
        # Paso 4: Validar checksums de archivos media (si se solicitó)
        if check_checksums:
            self.stdout.write(self.style.WARNING('[4/4] Validando checksums de archivos media...'))
            
            media_files = export_data.get('media_files', {})
            if not media_files:
                self.stdout.write(self.style.WARNING('  ⚠ No hay archivos media en el export'))
            else:
                # Extraer archivos temporalmente para validar checksums
                import tarfile
                import tempfile
                
                try:
                    with tarfile.open(file_path, 'r:gz') as tar:
                        media_members = [m for m in tar.getmembers() 
                                       if m.name.startswith('media/') and m.isfile()]
                        
                        if not media_members:
                            self.stdout.write(self.style.WARNING('  ⚠ No hay archivos media en el TAR'))
                        else:
                            # Validar checksums de algunos archivos (máx 10 para no demorar)
                            sample_size = min(10, len(media_members))
                            checksum_errors = 0
                            
                            with tempfile.TemporaryDirectory() as temp_dir:
                                for member in media_members[:sample_size]:
                                    relative_path = member.name[6:]  # Quitar 'media/'
                                    
                                    # Extraer a temp
                                    tar.extract(member, temp_dir)
                                    temp_file = Path(temp_dir) / member.name
                                    
                                    # Calcular checksum
                                    actual_checksum = calculate_file_checksum_from_path(str(temp_file))
                                    expected_checksum = media_files.get(relative_path, {}).get('checksum')
                                    
                                    if expected_checksum and actual_checksum != expected_checksum:
                                        checksum_errors += 1
                                        if verbose:
                                            self.stdout.write(self.style.ERROR(
                                                f"  ✗ {relative_path}: checksum inválido"
                                            ))
                            
                            if checksum_errors == 0:
                                self.stdout.write(self.style.SUCCESS(
                                    f'  ✓ Checksums válidos (muestra de {sample_size} archivos)'
                                ))
                            else:
                                self.stdout.write(self.style.ERROR(
                                    f'  ✗ {checksum_errors}/{sample_size} archivos con checksums inválidos'
                                ))
                
                except tarfile.TarError as e:
                    self.stdout.write(self.style.WARNING(f'  ⚠ No se pudo validar checksums: {e}'))
        else:
            self.stdout.write(self.style.WARNING('[4/4] Validación de checksums omitida (usa --check-checksums)'))
        
        # Resumen final
        self.stdout.write('\n' + self.style.SUCCESS('=== Validación Completada ==='))
        self.stdout.write(self.style.SUCCESS('✓ El archivo de export es válido y puede importarse'))
        self.stdout.write(f"\nPara importar, usa:")
        self.stdout.write(f"  docker exec backtuki-backend-1 python manage.py import_data {export_file}\n")
