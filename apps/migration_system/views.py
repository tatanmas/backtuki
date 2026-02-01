"""
🚀 ENTERPRISE MIGRATION API VIEWS

API endpoints para el sistema de migración.
"""

import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.http import FileResponse, Http404
from django.core.files.storage import default_storage
from pathlib import Path

from .models import MigrationJob, MigrationLog, MigrationCheckpoint
from .serializers import (
    MigrationJobSerializer,
    MigrationLogSerializer,
    MigrationCheckpointSerializer
)
from .services import (
    PlatformExportService,
    PlatformImportService,
    IntegrityVerificationService
)
from .permissions import (
    HasMigrationToken,
    IsSuperUserOrHasMigrationToken,
    CanExport,
    CanImport
)
from .utils import sanitize_filename

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([CanExport])
def start_export(request):
    """
    Inicia un export completo de la plataforma.
    
    Body:
        {
            "include_media": true,
            "compress": true,
            "output_filename": "tuki-export.json.gz"
        }
        
    Response:
        {
            "job_id": "uuid",
            "status": "in_progress",
            "message": "Export iniciado"
        }
    """
    try:
        # Crear job
        job = MigrationJob.objects.create(
            direction='export',
            status='pending',
            executed_by=request.user if request.user.is_authenticated else None,
            config=request.data
        )
        
        # Configurar opciones
        include_media = request.data.get('include_media', True)
        compress = request.data.get('compress', True)
        output_filename = request.data.get('output_filename', f'tuki-export-{job.id}.tar.gz')
        output_filename = sanitize_filename(output_filename)
        
        # Ejecutar export en background (o síncronamente para datasets pequeños)
        from django.conf import settings
        export_dir = Path(getattr(settings, 'MIGRATION_SYSTEM', {}).get('EXPORT_DIR', '/tmp/exports'))
        export_dir.mkdir(parents=True, exist_ok=True)
        output_file = export_dir / output_filename
        
        service = PlatformExportService(job=job)
        
        # TODO: Para producción, ejecutar en Celery task
        # Por ahora, ejecutar síncronamente
        result = service.export_all(
            output_file=str(output_file),
            include_media=include_media,
            compress=compress
        )
        
        return Response({
            'job_id': str(job.id),
            'status': job.status,
            'message': 'Export completado',
            'file_path': str(output_file),
            'size_mb': result['size_mb'],
            'statistics': result['statistics']
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("Error en start_export")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([HasMigrationToken])
def export_status(request, job_id):
    """
    Obtiene el estado de un export en progreso.
    
    Response:
        {
            "job_id": "uuid",
            "status": "in_progress",
            "progress_percent": 45,
            "current_step": "Exportando events.Event",
            "models_completed": 5,
            "total_models": 15
        }
    """
    try:
        job = MigrationJob.objects.get(id=job_id)
        serializer = MigrationJobSerializer(job)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except MigrationJob.DoesNotExist:
        raise Http404("Job no encontrado")


@api_view(['GET'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def download_export(request, job_id):
    """
    Descarga el archivo de export generado.
    
    Response:
        Binary file (application/gzip)
    """
    try:
        job = MigrationJob.objects.get(id=job_id)
        
        if job.status != 'completed':
            return Response({
                'error': 'Export no completado',
                'status': job.status
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not job.export_file_path:
            return Response({
                'error': 'Archivo de export no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        
        file_path = Path(job.export_file_path)
        
        if not file_path.exists():
            return Response({
                'error': 'Archivo no existe en disco'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Retornar archivo
        response = FileResponse(
            open(file_path, 'rb'),
            content_type='application/gzip',
            as_attachment=True,
            filename=file_path.name
        )
        
        return response
        
    except MigrationJob.DoesNotExist:
        raise Http404("Job no encontrado")


@api_view(['POST'])
@permission_classes([CanImport])
def receive_import(request):
    """
    Recibe datos para importar desde otro backend.
    
    Body (multipart/form-data):
        - export_file: archivo export.json.gz
        - verify: bool (default: true)
        - create_checkpoint: bool (default: true)
        - overwrite: bool (default: false)
        
    Response:
        {
            "job_id": "uuid",
            "status": "in_progress",
            "message": "Import iniciado"
        }
    """
    try:
        # Validar que se envió archivo
        if 'export_file' not in request.FILES:
            return Response({
                'error': 'Se requiere archivo export_file'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        export_file = request.FILES['export_file']
        
        # Log para debugging
        logger.info(f"Recibido archivo para import: {export_file.name}, size={export_file.size}")
        
        # Crear config excluyendo el archivo (no es serializable a JSON)
        config_data = {k: v for k, v in request.data.items() if k != 'export_file'}
        
        # Crear job
        job = MigrationJob.objects.create(
            direction='import',
            status='pending',
            executed_by=request.user if request.user.is_authenticated else None,
            config=config_data
        )
        
        # Guardar archivo temporalmente
        import tempfile
        import os as os_module
        
        # Determinar el sufijo basado en el nombre original del archivo
        original_name = export_file.name.lower()
        if original_name.endswith('.tar.gz') or original_name.endswith('.tgz'):
            suffix = '.tar.gz'
        elif original_name.endswith('.gz'):
            suffix = '.json.gz'
        else:
            suffix = os_module.path.splitext(original_name)[1] or '.json'
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        
        for chunk in export_file.chunks():
            temp_file.write(chunk)
        
        temp_file.close()
        
        # Configurar opciones
        import_options = {
            'verify': request.data.get('verify', 'true').lower() == 'true',
            'create_checkpoint': request.data.get('create_checkpoint', 'true').lower() == 'true',
            'overwrite': request.data.get('overwrite', 'false').lower() == 'true',
            'skip_existing': not request.data.get('overwrite', 'false').lower() == 'true',
            'auto_rollback': True,
        }
        
        # Ejecutar import
        service = PlatformImportService(job=job)
        
        # TODO: Para producción, ejecutar en Celery task
        # Por ahora, ejecutar síncronamente
        result = service.import_all(
            input_data=temp_file.name,
            **import_options
        )
        
        # Limpiar archivo temporal
        import os
        os.unlink(temp_file.name)
        
        return Response({
            'job_id': str(job.id),
            'status': job.status,
            'message': 'Import completado',
            'imported_counts': result['imported_counts'],
            'checkpoint_id': result.get('checkpoint_id')
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("Error en receive_import")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([HasMigrationToken])
def receive_file(request):
    """
    Recibe un archivo media individual.
    
    Body (multipart/form-data):
        - file: archivo
        - path: ruta relativa en media/
        - checksum: MD5 esperado (opcional)
        
    Response:
        {
            "success": true,
            "path": "events/images/foto.jpg",
            "size": 45678
        }
    """
    try:
        if 'file' not in request.FILES:
            return Response({
                'error': 'Se requiere archivo'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        file = request.FILES['file']
        path = request.data.get('path')
        expected_checksum = request.data.get('checksum')
        
        if not path:
            return Response({
                'error': 'Se requiere path'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Sanitizar path
        path = sanitize_filename(path)
        
        # Guardar archivo
        file_path = default_storage.save(path, file)
        
        # Verificar checksum si se proporcionó
        if expected_checksum:
            from .utils import calculate_file_checksum
            
            # Obtener archivo guardado
            saved_file = default_storage.open(file_path, 'rb')
            actual_checksum = calculate_file_checksum(saved_file)
            saved_file.close()
            
            if actual_checksum != expected_checksum:
                # Eliminar archivo si checksum no coincide
                default_storage.delete(file_path)
                return Response({
                    'error': 'Checksum mismatch',
                    'expected': expected_checksum,
                    'actual': actual_checksum
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': True,
            'path': file_path,
            'size': file.size
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("Error en receive_file")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([HasMigrationToken])
def media_list(request):
    """
    Retorna lista de todos los archivos media.
    
    Response:
        {
            "files": [
                {
                    "path": "events/images/foto.jpg",
                    "size": 45678,
                    "checksum": "md5:abc123...",
                    "url": "https://..."
                }
            ],
            "total_files": 234,
            "total_size_mb": 450.5
        }
    """
    try:
        from .utils import find_all_file_fields, calculate_file_checksum
        
        media_files = []
        total_size = 0
        
        file_fields = find_all_file_fields()
        
        for model, field_name in file_fields:
            queryset = model.objects.exclude(**{f"{field_name}": ''}).exclude(**{f"{field_name}__isnull": True})
            
            for obj in queryset:
                try:
                    file_field = getattr(obj, field_name)
                    if file_field and hasattr(file_field, 'name') and file_field.name:
                        file_size = file_field.size if hasattr(file_field, 'size') else 0
                        total_size += file_size
                        
                        media_files.append({
                            'path': file_field.name,
                            'size': file_size,
                            'checksum': f"md5:{calculate_file_checksum(file_field)}",
                            'url': file_field.url if hasattr(file_field, 'url') else None
                        })
                except Exception as e:
                    logger.warning(f"Error procesando archivo: {e}")
                    continue
        
        return Response({
            'files': media_files,
            'total_files': len(media_files),
            'total_size_mb': round(total_size / (1024 * 1024), 2)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("Error en media_list")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([HasMigrationToken])
def download_file(request):
    """
    Descarga un archivo media individual.
    
    Query params:
        - path: ruta del archivo
        
    Response:
        Binary file
    """
    try:
        file_path = request.query_params.get('path')
        
        if not file_path:
            return Response({
                'error': 'Se requiere parámetro path'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verificar que el archivo existe
        if not default_storage.exists(file_path):
            raise Http404("Archivo no encontrado")
        
        # Abrir y retornar archivo
        file = default_storage.open(file_path, 'rb')
        
        response = FileResponse(
            file,
            as_attachment=True,
            filename=Path(file_path).name
        )
        
        return response
        
    except Http404:
        raise
    except Exception as e:
        logger.exception("Error en download_file")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def verify_integrity(request):
    """
    Verifica la integridad de los datos.
    
    Body:
        {
            "job_id": "uuid",  # opcional
            "expected_statistics": {...}  # opcional
        }
        
    Response:
        {
            "success": true,
            "errors": [],
            "warnings": [],
            "report": "..."
        }
    """
    try:
        job_id = request.data.get('job_id')
        expected_statistics = request.data.get('expected_statistics')
        
        service = IntegrityVerificationService()
        result = service.verify_all(
            expected_statistics=expected_statistics,
            verify_files=True
        )
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("Error en verify_integrity")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def rollback_migration(request, job_id):
    """
    Revierte una migración usando su checkpoint.
    
    Response:
        {
            "success": true,
            "message": "Rollback completado",
            "checkpoint_id": "uuid"
        }
    """
    try:
        job = MigrationJob.objects.get(id=job_id)
        
        if not job.checkpoint:
            return Response({
                'error': 'Job no tiene checkpoint asociado'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Ejecutar rollback
        service = PlatformImportService()
        result = service.rollback_to_checkpoint(job.checkpoint.id)
        
        # Actualizar job
        job.status = 'rolled_back'
        job.save(update_fields=['status'])
        
        return Response({
            'success': True,
            'message': 'Rollback completado',
            'checkpoint_id': str(job.checkpoint.id),
            'result': result
        }, status=status.HTTP_200_OK)
        
    except MigrationJob.DoesNotExist:
        raise Http404("Job no encontrado")
    except Exception as e:
        logger.exception("Error en rollback_migration")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def list_jobs(request):
    """
    Lista todos los jobs de migración.
    
    Query params:
        - status: filtrar por estado
        - direction: filtrar por dirección
        - limit: límite de resultados (default: 50)
        
    Response:
        {
            "jobs": [...],
            "total": 123
        }
    """
    try:
        queryset = MigrationJob.objects.all()
        
        # Filtros
        if request.query_params.get('status'):
            queryset = queryset.filter(status=request.query_params['status'])
        
        if request.query_params.get('direction'):
            queryset = queryset.filter(direction=request.query_params['direction'])
        
        # Límite
        limit = int(request.query_params.get('limit', 50))
        queryset = queryset[:limit]
        
        serializer = MigrationJobSerializer(queryset, many=True)
        
        return Response({
            'jobs': serializer.data,
            'total': MigrationJob.objects.count()
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("Error en list_jobs")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def job_logs(request, job_id):
    """
    Obtiene los logs de un job específico.
    
    Response:
        {
            "logs": [...],
            "total": 456
        }
    """
    try:
        job = MigrationJob.objects.get(id=job_id)
        logs = job.logs.all()
        
        serializer = MigrationLogSerializer(logs, many=True)
        
        return Response({
            'logs': serializer.data,
            'total': logs.count()
        }, status=status.HTTP_200_OK)
        
    except MigrationJob.DoesNotExist:
        raise Http404("Job no encontrado")


# ==========================================
# MIGRATION TOKENS MANAGEMENT
# ==========================================

@api_view(['GET', 'POST'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def manage_migration_tokens(request):
    """
    Gestionar tokens de migración.
    
    GET: Lista tokens activos del usuario autenticado
    POST: Crea un nuevo token
    
    POST Body:
        {
            "description": "Token para migración GCP -> Local",
            "permissions": "admin",  # read, write, read_write, admin
            "expires_in_hours": 24,
            "allowed_ips": ["192.168.1.1"],  # opcional
            "allowed_domains": ["tuki.cl"],  # opcional
            "is_single_use": false
        }
    """
    from .models import MigrationToken
    from .serializers import MigrationTokenSerializer
    from django.utils import timezone
    from datetime import timedelta
    import secrets
    
    # Solo superusers pueden gestionar tokens
    if not request.user.is_superuser:
        return Response({
            'error': 'Solo superusers pueden gestionar tokens'
        }, status=status.HTTP_403_FORBIDDEN)
    
    if request.method == 'GET':
        # Listar tokens activos
        tokens = MigrationToken.objects.filter(
            created_by=request.user
        ).order_by('-created_at')
        
        serializer = MigrationTokenSerializer(tokens, many=True)
        
        return Response({
            'tokens': serializer.data,
            'total': tokens.count()
        }, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        # Crear nuevo token
        description = request.data.get('description', '')
        permissions = request.data.get('permissions', 'read')
        expires_in_hours = request.data.get('expires_in_hours', 24)
        allowed_ips = request.data.get('allowed_ips', [])
        allowed_domains = request.data.get('allowed_domains', [])
        is_single_use = request.data.get('is_single_use', False)
        
        # Validar permisos
        valid_permissions = ['read', 'write', 'read_write', 'admin']
        if permissions not in valid_permissions:
            return Response({
                'error': f'Permisos inválidos. Debe ser uno de: {", ".join(valid_permissions)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generar token seguro
        token_value = secrets.token_urlsafe(32)
        
        # Calcular fecha de expiración
        expires_at = timezone.now() + timedelta(hours=expires_in_hours)
        
        # Crear token
        token = MigrationToken.objects.create(
            token=token_value,
            description=description,
            permissions=permissions,
            allowed_ips=allowed_ips,
            allowed_domains=allowed_domains,
            expires_at=expires_at,
            is_single_use=is_single_use,
            created_by=request.user
        )
        
        serializer = MigrationTokenSerializer(token)
        
        logger.info(f"✅ Token de migración creado por {request.user.email}: {description}")
        
        # Incluir el token real en la respuesta (solo se muestra una vez)
        token_data = serializer.data
        token_data['token'] = token_value
        
        return Response({
            'success': True,
            'message': 'Token creado exitosamente',
            'token': token_data
        }, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def revoke_migration_token(request, token_id):
    """
    Revocar/eliminar un token de migración.
    
    DELETE /api/v1/migration/tokens/{token_id}/
    """
    from .models import MigrationToken
    
    # Solo superusers pueden revocar tokens
    if not request.user.is_superuser:
        return Response({
            'error': 'Solo superusers pueden revocar tokens'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        token = MigrationToken.objects.get(id=token_id, created_by=request.user)
        token_desc = token.description
        token.delete()
        
        logger.info(f"✅ Token de migración revocado por {request.user.email}: {token_desc}")
        
        return Response({
            'success': True,
            'message': f'Token "{token_desc}" revocado exitosamente'
        }, status=status.HTTP_200_OK)
        
    except MigrationToken.DoesNotExist:
        return Response({
            'error': 'Token no encontrado o no tienes permisos para revocarlo'
        }, status=status.HTTP_404_NOT_FOUND)


# ==========================================
# BACKUP RESTORE ENDPOINTS
# ==========================================

@api_view(['POST'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def upload_backup(request):
    """
    Sube un backup .tar.gz desde GCP para restaurar.
    
    POST /api/v1/migration/upload-backup/
    Body (multipart/form-data):
        - backup_file: archivo .tar.gz
        - restore_sql: bool (default: true)
        - restore_media: bool (default: true)
        
    Response:
        {
            "job_id": "uuid",
            "status": "uploaded",
            "file_size_mb": 123.45,
            "original_filename": "backup.tar.gz"
        }
    """
    from .models import BackupJob
    from .serializers import BackupJobSerializer
    
    # Solo superusers
    if not request.user.is_superuser:
        return Response({
            'error': 'Solo superusers pueden subir backups'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        # Validar archivo
        if 'backup_file' not in request.FILES:
            return Response({
                'error': 'Se requiere archivo backup_file'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        backup_file = request.FILES['backup_file']
        
        # Validar extensión
        if not backup_file.name.endswith('.tar.gz'):
            return Response({
                'error': 'El archivo debe ser .tar.gz'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calcular tamaño en MB
        file_size_mb = round(backup_file.size / (1024 * 1024), 2)
        
        # Crear job
        job = BackupJob.objects.create(
            backup_file=backup_file,
            file_size_mb=file_size_mb,
            original_filename=backup_file.name,
            restore_sql=request.data.get('restore_sql', 'true').lower() == 'true',
            restore_media=request.data.get('restore_media', 'true').lower() == 'true',
            uploaded_by=request.user,
            status='uploaded'
        )
        
        logger.info(f"✅ Backup subido por {request.user.email}: {file_size_mb}MB")
        
        serializer = BackupJobSerializer(job, context={'request': request})
        
        return Response({
            'success': True,
            'message': 'Backup subido exitosamente',
            'job': serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.exception("Error subiendo backup")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def restore_backup(request, job_id):
    """
    Ejecuta el restore desde un backup subido.
    
    POST /api/v1/migration/restore-backup/<job_id>/
    Body:
        {
            "confirm": true  # REQUIRED para seguridad
        }
        
    Response:
        {
            "job_id": "uuid",
            "status": "restoring",
            "message": "Restore iniciado"
        }
    """
    from .models import BackupJob
    from .services.backup_restore import RestoreService
    
    # Solo superusers
    if not request.user.is_superuser:
        return Response({
            'error': 'Solo superusers pueden ejecutar restore'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        job = BackupJob.objects.get(id=job_id)
        
        # Validar estado
        if job.status not in ['uploaded', 'validated', 'failed']:
            return Response({
                'error': f'No se puede restaurar desde estado: {job.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Requerir confirmación explícita
        if not request.data.get('confirm'):
            return Response({
                'error': 'Se requiere confirmación explícita (confirm: true)',
                'warning': '⚠️ ESTE RESTORE REEMPLAZARÁ TODOS LOS DATOS ACTUALES'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Ejecutar restore en thread separado (o Celery en producción)
        import threading
        
        def run_restore():
            service = RestoreService(job)
            service.execute()
        
        thread = threading.Thread(target=run_restore, daemon=True)
        thread.start()
        
        logger.info(f"✅ Restore iniciado por {request.user.email} - Job: {job_id}")
        
        return Response({
            'success': True,
            'job_id': str(job.id),
            'status': 'restoring',
            'message': 'Restore iniciado. Monitorea el progreso en /restore-status/'
        }, status=status.HTTP_200_OK)
        
    except BackupJob.DoesNotExist:
        return Response({
            'error': 'Backup job no encontrado'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Error iniciando restore")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def restore_status(request, job_id):
    """
    Obtiene el estado de un restore en progreso.
    
    GET /api/v1/migration/restore-status/<job_id>/
    
    Response:
        {
            "job_id": "uuid",
            "status": "restoring",
            "progress_percent": 45,
            "current_step": "Restaurando SQL...",
            "sql_records_restored": 1234,
            "media_files_restored": 567
        }
    """
    from .models import BackupJob
    from .serializers import BackupJobSerializer
    
    try:
        job = BackupJob.objects.get(id=job_id)
        serializer = BackupJobSerializer(job, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except BackupJob.DoesNotExist:
        return Response({
            'error': 'Backup job no encontrado'
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsSuperUserOrHasMigrationToken])
def list_backup_jobs(request):
    """
    Lista todos los backup jobs.
    
    GET /api/v1/migration/backup-jobs/
    Query params:
        - status: filtrar por estado
        - limit: límite de resultados (default: 20)
        
    Response:
        {
            "jobs": [...],
            "total": 10
        }
    """
    from .models import BackupJob
    from .serializers import BackupJobSerializer
    
    try:
        queryset = BackupJob.objects.all()
        
        # Filtros
        if request.query_params.get('status'):
            queryset = queryset.filter(status=request.query_params['status'])
        
        # Límite
        limit = int(request.query_params.get('limit', 20))
        queryset = queryset[:limit]
        
        serializer = BackupJobSerializer(queryset, many=True, context={'request': request})
        
        return Response({
            'jobs': serializer.data,
            'total': BackupJob.objects.count()
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("Error listando backup jobs")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
