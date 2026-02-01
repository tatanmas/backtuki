"""
🚀 ENTERPRISE EXPORT SERVICE

Servicio robusto para exportar toda la plataforma Tuki.
"""

import gzip
import json
import logging
import uuid
import decimal
from datetime import datetime, date
from pathlib import Path
from django.apps import apps
from django.conf import settings
from django.utils import timezone
from django.db import connection

from ..models import MigrationJob, MigrationLog
from ..utils import (
    get_all_models_in_order,
    find_all_file_fields,
    calculate_file_checksum,
    get_database_version,
    get_serializer_for_model,
    format_file_size,
)

logger = logging.getLogger(__name__)


class DjangoJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder que maneja tipos de Django.
    """
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super().default(obj)


class PlatformExportService:
    """
    Servicio enterprise para exportar toda la plataforma.
    
    Features:
    - Export de todos los modelos en orden de dependencias
    - Metadatos de archivos media
    - Compresión gzip
    - Progress tracking
    - Chunked export para grandes datasets
    """
    
    EXPORT_VERSION = "1.0.0"
    
    def __init__(self, job=None):
        """
        Initialize export service.
        
        Args:
            job: MigrationJob instance (opcional, para tracking)
        """
        self.job = job
        self.export_dir = getattr(settings, 'MIGRATION_SYSTEM', {}).get(
            'EXPORT_DIR',
            Path(settings.BASE_DIR) / 'exports'
        )
        self.chunk_size = getattr(settings, 'MIGRATION_SYSTEM', {}).get('CHUNK_SIZE', 1000)
        
        # Crear directorio si no existe
        Path(self.export_dir).mkdir(parents=True, exist_ok=True)
    
    def log(self, level, message, model_name=None, record_count=None, duration_ms=None):
        """Helper para crear logs."""
        if self.job:
            MigrationLog.objects.create(
                job=self.job,
                level=level,
                message=message,
                model_name=model_name,
                record_count=record_count,
                duration_ms=duration_ms
            )
        logger.log(
            getattr(logging, level.upper()),
            f"[Export] {message}"
        )
    
    def export_all(self, output_file=None, **options):
        """
        Exporta toda la plataforma.
        
        Args:
            output_file: Ruta del archivo de salida (opcional)
            **options:
                include_media: bool - Incluir metadatos de archivos (default True)
                compress: bool - Comprimir con gzip (default True)
                chunk_size: int - Tamaño de chunks
                models: list - Modelos específicos a exportar
                exclude_models: list - Modelos a excluir
                
        Returns:
            dict con resultado del export
        """
        start_time = datetime.now()
        self.log('info', "Iniciando export completo de la plataforma")
        
        if self.job:
            self.job.start()
        
        try:
            # Preparar estructura de datos
            export_data = {
                'version': self.EXPORT_VERSION,
                'export_date': timezone.now().isoformat(),
                'source_environment': self._get_environment_name(),
                'database_version': get_database_version(),
                'django_version': self._get_django_version(),
                'models': {},
                'media_files': {},
                'statistics': {}
            }
            
            # Obtener lista de modelos a exportar
            models_to_export = self._get_models_to_export(options)
            total_models = len(models_to_export)
            
            if self.job:
                self.job.total_models = total_models
                self.job.save(update_fields=['total_models'])
            
            self.log('info', f"Exportando {total_models} modelos")
            
            # Exportar cada modelo
            total_records = 0
            for idx, model_path in enumerate(models_to_export, 1):
                self.log('info', f"Exportando {model_path}...", model_name=model_path)
                
                app_label, model_name = model_path.split('.')
                model = apps.get_model(app_label, model_name)
                
                model_start = datetime.now()
                records = self.export_model(model, options.get('chunk_size', self.chunk_size))
                model_duration = (datetime.now() - model_start).total_seconds() * 1000
                
                export_data['models'][model_path] = records
                total_records += len(records)
                
                self.log(
                    'info',
                    f"Exportados {len(records)} registros de {model_path}",
                    model_name=model_path,
                    record_count=len(records),
                    duration_ms=int(model_duration)
                )
                
                # Actualizar progreso
                if self.job:
                    progress = int((idx / total_models) * 80)  # 80% para modelos, 20% para archivos
                    self.job.update_progress(progress, f"Exportando {model_path}")
                    self.job.models_completed = idx
                    self.job.records_processed = total_records
                    self.job.save(update_fields=['models_completed', 'records_processed'])
            
            # Exportar metadatos de archivos media
            if options.get('include_media', True):
                self.log('info', "Exportando metadatos de archivos media")
                export_data['media_files'] = self.export_media_metadata()
                
                if self.job:
                    self.job.update_progress(95, "Metadatos de archivos exportados")
            
            # Generar estadísticas
            export_data['statistics'] = self.generate_statistics(export_data)
            
            if self.job:
                self.job.total_records = total_records
                self.job.total_files = len(export_data['media_files'])
                self.job.save(update_fields=['total_records', 'total_files'])
            
            # Guardar a archivo si se especificó
            if output_file:
                self.log('info', f"Guardando export a {output_file}")
                file_path, file_size = self.save_to_file(
                    export_data,
                    output_file,
                    options.get('compress', True)
                )
                
                if self.job:
                    self.job.export_file_path = file_path
                    self.job.export_file_size_mb = file_size
                    self.job.save(update_fields=['export_file_path', 'export_file_size_mb'])
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if self.job:
                self.job.complete()
            
            self.log('info', f"Export completado en {duration:.2f}s")
            
            return {
                'success': True,
                'file_path': output_file,
                'size_mb': file_size if output_file else None,
                'statistics': export_data['statistics'],
                'duration_seconds': duration
            }
            
        except Exception as e:
            logger.exception("Error durante export")
            if self.job:
                import traceback
                self.job.fail(str(e), traceback.format_exc())
            raise
    
    def export_model(self, model, batch_size=1000):
        """
        Exporta un modelo específico.
        
        Args:
            model: Django model class
            batch_size: Tamaño del batch para procesar
            
        Returns:
            List de registros serializados
        """
        serializer_class = get_serializer_for_model(model)
        
        queryset = model.objects.all()
        total = queryset.count()
        
        logger.debug(f"Exportando {total} registros de {model._meta.label}")
        
        exported = []
        for i in range(0, total, batch_size):
            batch = queryset[i:i+batch_size]
            
            # Serializar batch
            try:
                serializer = serializer_class(batch, many=True)
                exported.extend(serializer.data)
            except Exception as e:
                # Si el serializer falla, usar values() como fallback
                logger.warning(f"Serializer falló para {model._meta.label}, usando values(): {e}")
                batch_data = list(batch.values())
                # Convertir dates/datetimes a strings
                for item in batch_data:
                    for key, value in item.items():
                        if isinstance(value, (datetime, timezone.datetime)):
                            item[key] = value.isoformat()
                exported.extend(batch_data)
        
        return exported
    
    def export_media_metadata(self):
        """
        Exporta metadatos de todos los archivos media.
        
        Returns:
            dict: {file_path: metadata}
        """
        media_files = {}
        file_fields = find_all_file_fields()
        
        self.log('info', f"Encontrados {len(file_fields)} campos de archivo")
        
        for model, field_name in file_fields:
            queryset = model.objects.exclude(**{f"{field_name}": ''}).exclude(**{f"{field_name}__isnull": True})
            
            for obj in queryset:
                try:
                    file_field = getattr(obj, field_name)
                    if file_field and hasattr(file_field, 'name') and file_field.name:
                        # Obtener URL (funciona tanto para GCS como filesystem local)
                        try:
                            file_url = file_field.url
                        except Exception:
                            file_url = None
                        
                        # Calcular checksum
                        checksum = calculate_file_checksum(file_field)
                        
                        media_files[file_field.name] = {
                            'size': file_field.size if hasattr(file_field, 'size') else 0,
                            'checksum': f"md5:{checksum}" if checksum else None,
                            'url': file_url,
                            'model': f"{model._meta.app_label}.{model._meta.object_name}",
                            'field': field_name,
                            'object_id': str(obj.pk)
                        }
                except Exception as e:
                    logger.warning(f"Error procesando archivo de {model._meta.label}.{field_name}: {e}")
                    continue
        
        self.log('info', f"Exportados metadatos de {len(media_files)} archivos")
        return media_files
    
    def generate_statistics(self, export_data):
        """
        Genera estadísticas del export.
        
        Args:
            export_data: dict con datos exportados
            
        Returns:
            dict con estadísticas
        """
        stats = {}
        
        # Contar registros por modelo
        for model_path, records in export_data['models'].items():
            stats[f"count_{model_path}"] = len(records)
        
        # Totales
        stats['total_models'] = len(export_data['models'])
        stats['total_records'] = sum(len(records) for records in export_data['models'].values())
        stats['total_files'] = len(export_data['media_files'])
        
        # Tamaño total de archivos
        total_size = sum(
            meta['size'] for meta in export_data['media_files'].values()
            if meta.get('size')
        )
        stats['total_media_size_bytes'] = total_size
        stats['total_media_size_mb'] = round(total_size / (1024 * 1024), 2)
        
        return stats
    
    def save_to_file(self, export_data, output_file, compress=True):
        """
        Guarda export data a archivo.
        
        Args:
            export_data: dict con datos
            output_file: ruta del archivo
            compress: comprimir con gzip
            
        Returns:
            tuple: (file_path, size_in_mb)
        """
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Serializar a JSON con encoder personalizado
        json_data = json.dumps(export_data, indent=2, ensure_ascii=False, cls=DjangoJSONEncoder)
        
        if compress:
            # Comprimir con gzip
            with gzip.open(output_path, 'wt', encoding='utf-8') as f:
                f.write(json_data)
        else:
            # Guardar sin comprimir
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_data)
        
        # Calcular tamaño
        file_size = output_path.stat().st_size
        size_mb = round(file_size / (1024 * 1024), 2)
        
        self.log('info', f"Archivo guardado: {output_path} ({size_mb} MB)")
        
        return str(output_path), size_mb
    
    def _get_models_to_export(self, options):
        """
        Determina qué modelos exportar basándose en opciones.
        
        Args:
            options: dict con opciones
            
        Returns:
            list de model paths
        """
        all_models = get_all_models_in_order()
        
        # Filtrar por modelos específicos si se especificó
        if options.get('models'):
            specific_models = options['models'].split(',')
            return [m for m in all_models if m in specific_models]
        
        # Excluir modelos si se especificó
        if options.get('exclude_models'):
            exclude = options['exclude_models'].split(',')
            return [m for m in all_models if m not in exclude]
        
        return all_models
    
    def _get_environment_name(self):
        """Obtiene nombre del entorno actual."""
        settings_module = settings.SETTINGS_MODULE
        if 'cloudrun' in settings_module:
            return 'GCP'
        elif 'homeserver' in settings_module:
            return 'HomeServer'
        elif 'production' in settings_module:
            return 'Production'
        elif 'development' in settings_module:
            return 'Development'
        return 'Unknown'
    
    def _get_django_version(self):
        """Obtiene versión de Django."""
        import django
        return django.get_version()
