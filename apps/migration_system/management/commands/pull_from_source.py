"""
🚀 ENTERPRISE COMMAND: Pull from Source

Management command para hacer pull de datos desde un backend origen.
"""

import requests
import logging
from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from apps.migration_system.services import PlatformImportService, FileTransferService
from apps.migration_system.models import MigrationJob

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Pull de toda la plataforma desde un backend origen'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--source-url',
            required=True,
            help='URL del backend origen (ej: https://prop.cl)'
        )
        parser.add_argument(
            '--source-token',
            required=True,
            help='Token de autenticación del backend origen'
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
            '--dry-run',
            action='store_true',
            help='Simular sin aplicar cambios'
        )
        parser.add_argument(
            '--skip-media',
            action='store_true',
            help='No descargar archivos media'
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Sobrescribir registros existentes'
        )
        parser.add_argument(
            '--parallel-downloads',
            type=int,
            default=5,
            help='Número de descargas paralelas de archivos (default: 5)'
        )
    
    def handle(self, *args, **options):
        source_url = options['source_url'].rstrip('/')
        source_token = options['source_token']
        
        self.stdout.write(self.style.SUCCESS('🚀 PULL FROM SOURCE - ENTERPRISE'))
        self.stdout.write('=' * 60)
        self.stdout.write(f"Origen: {source_url}")
        self.stdout.write('')
        
        # Crear job para tracking
        job = MigrationJob.objects.create(
            direction='pull',
            status='pending',
            source_url=source_url,
            config=options
        )
        
        self.stdout.write(f"Job ID: {job.id}")
        self.stdout.write('')
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('[DRY RUN] Simulando pull...'))
            self.stdout.write('')
        
        try:
            # PASO 1: Solicitar export al backend origen
            self.stdout.write(self.style.SUCCESS('PASO 1: Solicitando export al origen...'))
            
            headers = {'Authorization': f'MigrationToken {source_token}'}
            
            response = requests.post(
                f"{source_url}/api/v1/migration/export/",
                json={
                    'include_media': not options['skip_media'],
                    'compress': True
                },
                headers=headers,
                timeout=600
            )
            
            if response.status_code != 200:
                raise CommandError(f"Error al solicitar export: {response.text}")
            
            export_job_id = response.json()['job_id']
            self.stdout.write(f"  Export iniciado en origen: {export_job_id}")
            self.stdout.write('')
            
            # PASO 2: Esperar a que el export complete (polling)
            self.stdout.write(self.style.SUCCESS('PASO 2: Esperando export...'))
            
            export_completed = False
            max_attempts = 60  # 10 minutos máximo
            attempt = 0
            
            while not export_completed and attempt < max_attempts:
                import time
                time.sleep(10)  # Esperar 10 segundos entre checks
                
                status_response = requests.get(
                    f"{source_url}/api/v1/migration/export-status/{export_job_id}/",
                    headers=headers,
                    timeout=30
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    progress = status_data.get('progress_percent', 0)
                    current_step = status_data.get('current_step', '')
                    
                    self.stdout.write(f"  Progreso: {progress}% - {current_step}", ending='\r')
                    self.stdout.flush()
                    
                    if status_data['status'] == 'completed':
                        export_completed = True
                        self.stdout.write('')
                        self.stdout.write('  ✓ Export completado en origen')
                    elif status_data['status'] == 'failed':
                        raise CommandError(f"Export falló en origen: {status_data.get('error_message')}")
                
                attempt += 1
            
            if not export_completed:
                raise CommandError("Timeout esperando export en origen")
            
            self.stdout.write('')
            
            # PASO 3: Descargar export desde origen
            self.stdout.write(self.style.SUCCESS('PASO 3: Descargando export...'))
            
            download_response = requests.get(
                f"{source_url}/api/v1/migration/download-export/{export_job_id}/",
                headers=headers,
                stream=True,
                timeout=600
            )
            
            if download_response.status_code != 200:
                raise CommandError(f"Error al descargar export: {download_response.text}")
            
            # Guardar archivo temporalmente
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json.gz')
            
            total_size = 0
            for chunk in download_response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
                    total_size += len(chunk)
            
            temp_file.close()
            
            size_mb = round(total_size / (1024 * 1024), 2)
            self.stdout.write(f"  ✓ Descargado: {size_mb} MB")
            self.stdout.write('')
            
            # PASO 4: Importar datos localmente
            self.stdout.write(self.style.SUCCESS('PASO 4: Importando datos...'))
            
            import_service = PlatformImportService(job=job)
            
            import_options = {
                'dry_run': options.get('dry_run', False),
                'create_checkpoint': not options.get('dry_run') and options.get('create_checkpoint', True),
                'verify': not options.get('no_verify', False) and options.get('verify', True),
                'overwrite': options.get('overwrite', False),
                'skip_existing': not options.get('overwrite', False),
                'skip_media': options.get('skip_media', False),
                'auto_rollback': True,
            }
            
            result = import_service.import_all(
                input_data=temp_file.name,
                **import_options
            )
            
            self.stdout.write('')
            
            # PASO 5: Descargar archivos media si es necesario
            if not options['skip_media'] and not options['dry_run']:
                self.stdout.write(self.style.SUCCESS('PASO 5: Descargando archivos media...'))
                
                # Obtener lista de archivos
                media_response = requests.get(
                    f"{source_url}/api/v1/migration/media-list/",
                    headers=headers,
                    timeout=60
                )
                
                if media_response.status_code == 200:
                    media_files = media_response.json()['files']
                    total_files = len(media_files)
                    
                    self.stdout.write(f"  Total archivos: {total_files}")
                    
                    file_transfer = FileTransferService(job=job)
                    downloaded = 0
                    errors = []
                    
                    for file_info in media_files:
                        file_url = f"{source_url}/api/v1/migration/download-file/?path={file_info['path']}"
                        destination = file_info['path']
                        
                        download_result = file_transfer.download_file_from_url(
                            file_url,
                            destination,
                            auth_token=source_token
                        )
                        
                        if download_result['success']:
                            downloaded += 1
                            self.stdout.write(f"  ✓ {file_info['path']} ({downloaded}/{total_files})", ending='\r')
                            self.stdout.flush()
                        else:
                            errors.append(download_result['error'])
                    
                    self.stdout.write('')
                    self.stdout.write(f"  ✓ Descargados: {downloaded}/{total_files}")
                    
                    if errors:
                        self.stdout.write(self.style.WARNING(f"  ⚠ Errores: {len(errors)}"))
                
                self.stdout.write('')
            
            # Limpiar archivo temporal
            import os
            os.unlink(temp_file.name)
            
            # RESUMEN FINAL
            self.stdout.write('')
            self.stdout.write('=' * 60)
            self.stdout.write(self.style.SUCCESS('✅ PULL COMPLETADO EXITOSAMENTE'))
            self.stdout.write('=' * 60)
            self.stdout.write('')
            self.stdout.write('📊 RESUMEN:')
            self.stdout.write(f"  - Job ID: {job.id}")
            self.stdout.write(f"  - Duración: {result['duration_seconds']:.2f}s")
            
            if result.get('checkpoint_id'):
                self.stdout.write(f"  - Checkpoint: {result['checkpoint_id']}")
            
            self.stdout.write('')
            self.stdout.write('  Registros importados:')
            for model_path, count in result['imported_counts'].items():
                self.stdout.write(f"    • {model_path}: {count}")
            
            self.stdout.write('')
            self.stdout.write('📋 PRÓXIMOS PASOS:')
            self.stdout.write('  1. Verificar que los servicios funcionen correctamente')
            self.stdout.write('  2. Probar funcionalidades críticas')
            self.stdout.write('  3. Si todo está OK, apagar backend origen')
            self.stdout.write('')
            
        except Exception as e:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'❌ Error durante pull: {str(e)}'))
            raise CommandError(f'Pull falló: {e}')
