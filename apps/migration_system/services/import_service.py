"""
🚀 ENTERPRISE IMPORT SERVICE

Servicio robusto para importar datos con checkpoint y rollback.
"""

import gzip
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from django.apps import apps
from django.conf import settings
from django.utils import timezone
from django.db import transaction, IntegrityError as DBIntegrityError
from django.core.files.storage import default_storage

from ..models import MigrationJob, MigrationLog, MigrationCheckpoint
from ..utils import (
    get_all_models_in_order,
    get_database_version,
    get_serializer_for_model,
)
from .export_service import PlatformExportService

logger = logging.getLogger(__name__)


class IntegrityError(Exception):
    """Custom exception for integrity errors."""
    pass


class PlatformImportService:
    """
    Servicio enterprise para importar datos con checkpoint y rollback.
    
    Features:
    - Import con validación de integridad
    - Checkpoint antes de cambios críticos
    - Rollback automático si falla
    - Manejo de conflictos (skip, overwrite, merge)
    - Dry-run mode
    """
    
    # Mismo orden que export (respeta dependencias)
    MODEL_IMPORT_ORDER = get_all_models_in_order()
    
    def __init__(self, job=None):
        """
        Initialize import service.
        
        Args:
            job: MigrationJob instance (opcional, para tracking)
        """
        self.job = job
        self.checkpoint_dir = getattr(settings, 'MIGRATION_SYSTEM', {}).get(
            'CHECKPOINT_DIR',
            Path(settings.BASE_DIR) / 'checkpoints'
        )
        
        # Crear directorio si no existe
        Path(self.checkpoint_dir).mkdir(parents=True, exist_ok=True)
    
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
            f"[Import] {message}"
        )
    
    def import_all(self, input_data, **options):
        """
        Importa toda la plataforma desde export.
        
        Args:
            input_data: dict o path a archivo export
            **options:
                dry_run: bool - Simular sin aplicar cambios
                create_checkpoint: bool - Crear punto de restauración
                verify: bool - Verificar integridad post-import
                overwrite: bool - Sobrescribir registros existentes
                merge: bool - Merge con datos existentes
                skip_existing: bool - Saltar registros existentes
                auto_rollback: bool - Rollback automático si falla
                
        Returns:
            dict con resultado
        """
        start_time = datetime.now()
        self.log('info', "Iniciando import de plataforma")
        
        if self.job:
            self.job.start()
        
        checkpoint = None
        
        try:
            # Cargar datos si es un archivo
            if isinstance(input_data, str):
                input_data = self.load_from_file(input_data)
            
            # Validar formato
            if not self.validate_export_format(input_data):
                raise ValueError("Formato de export inválido o incompatible")
            
            # Crear checkpoint si se solicita
            if options.get('create_checkpoint', True) and not options.get('dry_run'):
                self.log('info', "Creando checkpoint antes de importar")
                checkpoint = self.create_checkpoint()
                
                if self.job:
                    self.job.checkpoint = checkpoint
                    self.job.save(update_fields=['checkpoint'])
            
            # Preparar estadísticas
            total_models = len([m for m in input_data['models'] if input_data['models'][m]])
            
            if self.job:
                self.job.total_models = total_models
                self.job.total_records = input_data['statistics'].get('total_records', 0)
                self.job.total_files = input_data['statistics'].get('total_files', 0)
                self.job.save(update_fields=['total_models', 'total_records', 'total_files'])
            
            # Importar modelos
            imported_counts = {}
            
            if not options.get('dry_run'):
                with transaction.atomic():
                    for idx, model_path in enumerate(self.MODEL_IMPORT_ORDER, 1):
                        model_data = input_data['models'].get(model_path, [])
                        
                        if not model_data:
                            continue
                        
                        self.log('info', f"Importando {model_path}...", model_name=model_path)
                        
                        model_start = datetime.now()
                        count = self.import_model(model_path, model_data, **options)
                        model_duration = (datetime.now() - model_start).total_seconds() * 1000
                        
                        imported_counts[model_path] = count
                        
                        self.log(
                            'info',
                            f"Importados {count}/{len(model_data)} registros de {model_path}",
                            model_name=model_path,
                            record_count=count,
                            duration_ms=int(model_duration)
                        )
                        
                        # Actualizar progreso
                        if self.job:
                            progress = int((idx / total_models) * 90)  # 90% para datos
                            self.job.update_progress(progress, f"Importando {model_path}")
                            self.job.models_completed = idx
                            self.job.records_processed = sum(imported_counts.values())
                            self.job.save(update_fields=['models_completed', 'records_processed'])
            else:
                # Dry run - solo contar
                for model_path, model_data in input_data['models'].items():
                    if model_data:
                        imported_counts[model_path] = len(model_data)
                        self.log('info', f"[DRY RUN] Importaría {len(model_data)} registros de {model_path}")
            
            # Verificar integridad si se solicita
            if options.get('verify', True) and not options.get('dry_run'):
                self.log('info', "Verificando integridad post-import")
                verification = self.verify_import(input_data['statistics'])
                
                if not verification['success']:
                    raise IntegrityError(f"Verificación falló: {verification['errors']}")
                
                self.log('info', "Verificación de integridad exitosa")
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if self.job and not options.get('dry_run'):
                self.job.complete()
            
            self.log('info', f"Import completado en {duration:.2f}s")
            
            return {
                'success': True,
                'imported_counts': imported_counts,
                'checkpoint_id': checkpoint.id if checkpoint else None,
                'duration_seconds': duration,
                'dry_run': options.get('dry_run', False)
            }
            
        except Exception as e:
            logger.exception("Error durante import")
            
            # Rollback automático si está configurado
            if checkpoint and options.get('auto_rollback', True) and not options.get('dry_run'):
                self.log('error', f"Error durante import: {e}. Ejecutando rollback...")
                try:
                    self.rollback_to_checkpoint(checkpoint.id)
                    self.log('info', "Rollback completado")
                except Exception as rollback_error:
                    self.log('critical', f"Error durante rollback: {rollback_error}")
            
            if self.job:
                import traceback
                self.job.fail(str(e), traceback.format_exc())
            
            raise
    
    def import_model(self, model_path, data_list, **options):
        """
        Importa un modelo específico.
        
        Args:
            model_path: str como 'events.Event'
            data_list: lista de dicts con datos
            **options: opciones de import
            
        Returns:
            int: cantidad de registros importados
        """
        app_label, model_name = model_path.split('.')
        model = apps.get_model(app_label, model_name)
        
        imported = 0
        skipped = 0
        errors = []
        
        for item_data in data_list:
            try:
                pk = item_data.get('id') or item_data.get('pk')
                
                # Verificar si existe
                exists = model.objects.filter(pk=pk).exists() if pk else False
                
                if exists:
                    if options.get('skip_existing', False):
                        skipped += 1
                        continue
                    elif options.get('overwrite', False):
                        instance = model.objects.get(pk=pk)
                        self._update_instance(instance, item_data)
                        imported += 1
                    elif options.get('merge', False):
                        instance = model.objects.get(pk=pk)
                        self._merge_instance(instance, item_data)
                        imported += 1
                    else:
                        # Default: skip existentes
                        skipped += 1
                        continue
                else:
                    # Crear nuevo
                    self._create_instance(model, item_data)
                    imported += 1
                    
            except Exception as e:
                errors.append({
                    'model': model_path,
                    'pk': pk,
                    'error': str(e)
                })
                logger.error(f"Error importando {model_path} pk={pk}: {e}")
        
        if errors:
            self.log('warning', f"{model_path}: {len(errors)} errores de {len(data_list)} registros")
        if skipped:
            self.log('info', f"{model_path}: {skipped} registros saltados (ya existentes)")
        
        return imported
    
    def _create_instance(self, model, data):
        """Crea una nueva instancia del modelo."""
        # Remover campos que no son del modelo
        model_fields = [f.name for f in model._meta.get_fields()]
        clean_data = {k: v for k, v in data.items() if k in model_fields}
        
        # Crear instancia
        instance = model.objects.create(**clean_data)
        return instance
    
    def _update_instance(self, instance, data):
        """Actualiza una instancia existente con nuevos datos."""
        model_fields = [f.name for f in instance._meta.get_fields()]
        
        for key, value in data.items():
            if key in model_fields and hasattr(instance, key):
                setattr(instance, key, value)
        
        instance.save()
        return instance
    
    def _merge_instance(self, instance, data):
        """Merge de instancia existente con nuevos datos (solo campos no nulos)."""
        model_fields = [f.name for f in instance._meta.get_fields()]
        
        for key, value in data.items():
            if key in model_fields and value is not None and hasattr(instance, key):
                # Solo actualizar si el valor actual es None o vacío
                current_value = getattr(instance, key)
                if current_value is None or current_value == '':
                    setattr(instance, key, value)
        
        instance.save()
        return instance
    
    def create_checkpoint(self, name=None, description=None):
        """
        Crea un checkpoint de los datos actuales.
        
        Args:
            name: nombre del checkpoint
            description: descripción
            
        Returns:
            MigrationCheckpoint instance
        """
        if not name:
            name = f"checkpoint-{timezone.now().strftime('%Y%m%d-%H%M%S')}"
        
        self.log('info', f"Creando checkpoint: {name}")
        
        # Exportar datos actuales
        export_service = PlatformExportService()
        timestamp = timezone.now().strftime('%Y%m%d-%H%M%S')
        checkpoint_file = Path(self.checkpoint_dir) / f"{name}-{timestamp}.json.gz"
        
        result = export_service.export_all(
            output_file=str(checkpoint_file),
            include_media=False,  # No incluir archivos en checkpoint (solo metadata)
            compress=True
        )
        
        # Crear registro de checkpoint
        checkpoint = MigrationCheckpoint.objects.create(
            name=name,
            description=description or f"Checkpoint automático antes de import",
            snapshot_file_path=str(checkpoint_file),
            snapshot_size_mb=result['size_mb'],
            total_models=result['statistics']['total_models'],
            total_records=result['statistics']['total_records'],
            total_files=result['statistics'].get('total_files', 0),
            database_version=get_database_version(),
            environment=export_service._get_environment_name(),
            expires_at=timezone.now() + timedelta(days=30)  # Expira en 30 días
        )
        
        self.log('info', f"Checkpoint creado: {checkpoint.id}")
        return checkpoint
    
    def rollback_to_checkpoint(self, checkpoint_id):
        """
        Revierte a un checkpoint anterior.
        
        Args:
            checkpoint_id: UUID del checkpoint
            
        Returns:
            dict con resultado
        """
        checkpoint = MigrationCheckpoint.objects.get(id=checkpoint_id)
        
        if not checkpoint.is_valid:
            raise ValueError("Checkpoint no es válido")
        
        if checkpoint.is_expired:
            raise ValueError("Checkpoint expiró")
        
        self.log('warning', f"Iniciando rollback a checkpoint: {checkpoint.name}")
        
        # Cargar datos del checkpoint
        checkpoint_data = self.load_from_file(checkpoint.snapshot_file_path)
        
        # Importar datos del checkpoint (esto restaura el estado anterior)
        result = self.import_all(
            checkpoint_data,
            create_checkpoint=False,  # No crear otro checkpoint durante rollback
            verify=True,
            overwrite=True,  # Sobrescribir con datos del checkpoint
            auto_rollback=False  # Evitar recursión infinita
        )
        
        # Marcar checkpoint como usado
        checkpoint.mark_as_used()
        
        self.log('info', "Rollback completado exitosamente")
        
        return result
    
    def validate_export_format(self, export_data):
        """
        Valida que el formato del export sea correcto.
        
        Args:
            export_data: dict con datos exportados
            
        Returns:
            bool
        """
        required_keys = ['version', 'export_date', 'models', 'statistics']
        
        for key in required_keys:
            if key not in export_data:
                self.log('error', f"Formato inválido: falta clave '{key}'")
                return False
        
        # Verificar versión
        if export_data['version'] != PlatformExportService.EXPORT_VERSION:
            self.log('warning', f"Versión de export diferente: {export_data['version']}")
        
        return True
    
    def verify_import(self, expected_statistics):
        """
        Verifica que el import fue exitoso comparando estadísticas.
        
        Args:
            expected_statistics: dict con estadísticas esperadas
            
        Returns:
            dict con resultado de verificación
        """
        errors = []
        warnings = []
        
        # Verificar counts por modelo
        for key, expected_count in expected_statistics.items():
            if key.startswith('count_'):
                model_path = key.replace('count_', '')
                
                try:
                    app_label, model_name = model_path.split('.')
                    model = apps.get_model(app_label, model_name)
                    actual_count = model.objects.count()
                    
                    if actual_count < expected_count:
                        errors.append(f"{model_path}: esperados {expected_count}, actual {actual_count}")
                    elif actual_count > expected_count:
                        warnings.append(f"{model_path}: más registros de lo esperado ({actual_count} vs {expected_count})")
                    
                except LookupError:
                    warnings.append(f"Modelo {model_path} no encontrado en destino")
        
        success = len(errors) == 0
        
        if errors:
            self.log('error', f"Verificación falló con {len(errors)} errores")
        if warnings:
            self.log('warning', f"Verificación con {len(warnings)} warnings")
        
        return {
            'success': success,
            'errors': errors,
            'warnings': warnings
        }
    
    def load_from_file(self, file_path):
        """
        Carga datos desde archivo export.
        
        Args:
            file_path: ruta del archivo
            
        Returns:
            dict con datos
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
        
        # Detectar si está comprimido
        if file_path.suffix == '.gz':
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                data = json.load(f)
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        return data
