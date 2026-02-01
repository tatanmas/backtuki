"""
🚀 ENTERPRISE COMMAND: Push to Target

Management command para hacer push de datos a un backend destino.
"""

import requests
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand, CommandError
from apps.migration_system.services import PlatformExportService, FileTransferService
from apps.migration_system.models import MigrationJob
from apps.migration_system.utils import find_all_file_fields

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Push de toda la plataforma a un backend destino'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--target-url',
            required=True,
            help='URL del backend destino (ej: https://tukitickets.duckdns.org:8000)'
        )
        parser.add_argument(
            '--target-token',
            required=True,
            help='Token de autenticación del backend destino'
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            default=True,
            help='Verificar integridad en destino (default: True)'
        )
        parser.add_argument(
            '--no-verify',
            action='store_true',
            help='No verificar integridad'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular sin enviar datos'
        )
        parser.add_argument(
            '--skip-media',
            action='store_true',
            help='No transferir archivos media'
        )
        parser.add_argument(
            '--parallel-transfers',
            type=int,
            default=5,
            help='Número de transferencias paralelas de archivos (default: 5)'
        )
    
    def handle(self, *args, **options):
        target_url = options['target_url'].rstrip('/')
        target_token = options['target_token']
        
        self.stdout.write(self.style.SUCCESS('🚀 PUSH TO TARGET - ENTERPRISE'))
        self.stdout.write('=' * 60)
        self.stdout.write(f"Destino: {target_url}")
        self.stdout.write('')
        
        # Crear job para tracking
        job = MigrationJob.objects.create(
            direction='push',
            status='pending',
            target_url=target_url,
            config=options
        )
        
        self.stdout.write(f"Job ID: {job.id}")
        self.stdout.write('')
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('[DRY RUN] Simulando push...'))
            self.stdout.write('')
        
        try:
            # PASO 1: Exportar datos localmente
            self.stdout.write(self.style.SUCCESS('PASO 1: Exportando datos localmente...'))
            
            export_service = PlatformExportService(job=job)
            export_data = export_service.export_all(
                output_file=None,  # No guardar a archivo, mantener en memoria
                include_media=not options['skip_media'],
                compress=False  # No comprimir para enviar directo
            )
            
            self.stdout.write(f"  ✓ Exportados {export_data['statistics']['total_records']} registros")
            self.stdout.write(f"  ✓ Modelos: {export_data['statistics']['total_models']}")
            self.stdout.write(f"  ✓ Archivos: {export_data['statistics']['total_files']}")
            self.stdout.write('')
            
            if options['dry_run']:
                self.stdout.write(self.style.SUCCESS('[DRY RUN] Export simulado exitosamente'))
                return
            
            # PASO 2: Enviar datos al destino
            self.stdout.write(self.style.SUCCESS('PASO 2: Enviando datos al destino...'))
            
            headers = {'Authorization': f'MigrationToken {target_token}'}
            
            response = requests.post(
                f"{target_url}/api/v1/migration/receive-import/",
                json=export_data,
                headers=headers,
                timeout=600
            )
            
            if response.status_code != 200:
                raise CommandError(f"Error al enviar datos: {response.text}")
            
            import_job_id = response.json()['job_id']
            self.stdout.write(f"  ✓ Import iniciado en destino: {import_job_id}")
            self.stdout.write('')
            
            # PASO 3: Transferir archivos media
            if not options['skip_media']:
                self.stdout.write(self.style.SUCCESS('PASO 3: Transfiriendo archivos media...'))
                
                media_files = export_data.get('media_files', {})
                total_files = len(media_files)
                
                if total_files > 0:
                    self.stdout.write(f"  Total archivos: {total_files}")
                    
                    file_transfer = FileTransferService(job=job)
                    transferred = 0
                    errors = []
                    
                    # Transferir en paralelo
                    with ThreadPoolExecutor(max_workers=options['parallel_transfers']) as executor:
                        futures = {}
                        
                        for file_path, file_info in media_files.items():
                            future = executor.submit(
                                file_transfer.transfer_file_to_backend,
                                file_path,
                                target_url,
                                target_token
                            )
                            futures[future] = file_path
                        
                        for future in as_completed(futures):
                            file_path = futures[future]
                            try:
                                result = future.result()
                                if result['success']:
                                    transferred += 1
                                    self.stdout.write(f"  ✓ {file_path} ({transferred}/{total_files})", ending='\r')
                                    self.stdout.flush()
                                else:
                                    errors.append(f"{file_path}: {result['error']}")
                                    self.stdout.write(self.style.ERROR(f"  ✗ {file_path}"))
                            except Exception as e:
                                errors.append(f"{file_path}: {str(e)}")
                                self.stdout.write(self.style.ERROR(f"  ✗ {file_path}: {e}"))
                    
                    self.stdout.write('')
                    self.stdout.write(f"  ✓ Transferidos: {transferred}/{total_files}")
                    
                    if errors:
                        self.stdout.write(self.style.WARNING(f"  ⚠ Errores: {len(errors)}"))
                        for error in errors[:5]:  # Mostrar solo primeros 5
                            self.stdout.write(f"    - {error}")
                        if len(errors) > 5:
                            self.stdout.write(f"    ... y {len(errors) - 5} más")
                else:
                    self.stdout.write('  No hay archivos media para transferir')
                
                self.stdout.write('')
            
            # PASO 4: Verificar integridad en destino
            if not options.get('no_verify') and options.get('verify', True):
                self.stdout.write(self.style.SUCCESS('PASO 4: Verificando integridad en destino...'))
                
                verify_response = requests.post(
                    f"{target_url}/api/v1/migration/verify/",
                    json={'job_id': import_job_id},
                    headers=headers,
                    timeout=300
                )
                
                if verify_response.status_code == 200:
                    verification = verify_response.json()
                    
                    if verification['success']:
                        self.stdout.write('  ✓ Verificación exitosa')
                    else:
                        self.stdout.write(self.style.ERROR('  ✗ Verificación falló'))
                        for error in verification.get('errors', [])[:10]:
                            self.stdout.write(f"    - {error}")
                else:
                    self.stdout.write(self.style.WARNING('  ⚠ No se pudo verificar integridad'))
                
                self.stdout.write('')
            
            # Marcar job como completado
            job.complete()
            
            # RESUMEN FINAL
            self.stdout.write('')
            self.stdout.write('=' * 60)
            self.stdout.write(self.style.SUCCESS('✅ PUSH COMPLETADO EXITOSAMENTE'))
            self.stdout.write('=' * 60)
            self.stdout.write('')
            self.stdout.write('📊 RESUMEN:')
            self.stdout.write(f"  - Job ID: {job.id}")
            self.stdout.write(f"  - Registros: {export_data["statistics"]["total_records"]}')
            self.stdout.write(f"  - Modelos: {export_data['statistics']['total_models']}")
            self.stdout.write(f"  - Archivos: {export_data['statistics']['total_files']}")
            self.stdout.write('')
            self.stdout.write('📋 PRÓXIMOS PASOS:')
            self.stdout.write('  1. Verificar que el destino funcione correctamente')
            self.stdout.write('  2. Actualizar DNS si es necesario')
            self.stdout.write('  3. Apagar origen si migración es permanente')
            self.stdout.write('')
            
        except Exception as e:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'❌ Error durante push: {str(e)}'))
            raise CommandError(f'Push falló: {e}')
