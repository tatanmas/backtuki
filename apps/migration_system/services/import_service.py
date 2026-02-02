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
        
        # Buffer de logs para evitar corrupciones de transacciones
        self._log_buffer = []
        self._use_log_buffer = False
    
    def log(self, level, message, model_name=None, record_count=None, duration_ms=None):
        """
        Helper para crear logs con soporte de buffering.
        
        Durante transacciones atómicas, los logs se almacenan en buffer y se 
        escriben a DB después del commit para evitar corrupción de transacciones.
        """
        # Siempre logear a Python logger
        logger.log(
            getattr(logging, level.upper()),
            f"[Import] {message}"
        )
        
        # Si estamos en modo buffer, guardar en memoria
        if self._use_log_buffer:
            self._log_buffer.append({
                'level': level,
                'message': message,
                'model_name': model_name,
                'record_count': record_count,
                'duration_ms': duration_ms
            })
        # Si no, escribir directamente a DB
        elif self.job:
            try:
                MigrationLog.objects.create(
                    job=self.job,
                    level=level,
                    message=message,
                    model_name=model_name,
                    record_count=record_count,
                    duration_ms=duration_ms
                )
            except Exception as e:
                # Si falla crear el log en DB, solo logear a consola
                logger.warning(f"No se pudo crear MigrationLog en DB: {e}")
    
    def _flush_log_buffer(self):
        """
        Escribe todos los logs del buffer a la base de datos.
        Se llama después de un commit exitoso.
        """
        if not self.job or not self._log_buffer:
            return
        
        # Crear todos los logs en batch
        logs_to_create = []
        for log_entry in self._log_buffer:
            logs_to_create.append(
                MigrationLog(
                    job=self.job,
                    level=log_entry['level'],
                    message=log_entry['message'],
                    model_name=log_entry.get('model_name'),
                    record_count=log_entry.get('record_count'),
                    duration_ms=log_entry.get('duration_ms')
                )
            )
        
        try:
            # Bulk create para eficiencia
            MigrationLog.objects.bulk_create(logs_to_create, batch_size=100)
            logger.debug(f"Flushed {len(logs_to_create)} logs to database")
        except Exception as e:
            logger.error(f"Error flushing log buffer to DB: {e}")
        finally:
            # Limpiar buffer
            self._log_buffer = []
    
    def _flush_log_buffer_to_file(self):
        """
        Escribe logs del buffer a archivo cuando falla la transacción.
        Útil para debugging cuando el import falla.
        """
        if not self._log_buffer:
            return
        
        try:
            import tempfile
            from pathlib import Path
            
            log_file = Path(tempfile.gettempdir()) / f"migration_import_error_{timezone.now().strftime('%Y%m%d_%H%M%S')}.log"
            
            with open(log_file, 'w') as f:
                f.write(f"Migration Import Error Log - {timezone.now().isoformat()}\n")
                f.write(f"Job ID: {self.job.id if self.job else 'N/A'}\n")
                f.write("=" * 80 + "\n\n")
                
                for log_entry in self._log_buffer:
                    f.write(f"[{log_entry['level'].upper()}] {log_entry['message']}\n")
                    if log_entry.get('model_name'):
                        f.write(f"  Model: {log_entry['model_name']}\n")
                    if log_entry.get('record_count') is not None:
                        f.write(f"  Records: {log_entry['record_count']}\n")
                    if log_entry.get('duration_ms') is not None:
                        f.write(f"  Duration: {log_entry['duration_ms']}ms\n")
                    f.write("\n")
            
            logger.info(f"Logs de error guardados en: {log_file}")
        except Exception as e:
            logger.error(f"No se pudo guardar logs a archivo: {e}")
        finally:
            self._log_buffer = []
    
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
        source_file_path = None  # Guardar ruta para extracción de media
        
        try:
            # Cargar datos si es un archivo
            if isinstance(input_data, str):
                source_file_path = input_data  # Guardar ruta original
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
                # Activar buffer de logs para evitar corrupción de transacciones
                self._use_log_buffer = True
                self._log_buffer = []
                
                try:
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
                            
                            # Actualizar progreso (esto está fuera de log buffer)
                            if self.job:
                                progress = int((idx / total_models) * 90)  # 90% para datos
                                self.job.update_progress(progress, f"Importando {model_path}")
                                self.job.models_completed = idx
                                self.job.records_processed = sum(imported_counts.values())
                                self.job.save(update_fields=['models_completed', 'records_processed'])
                    
                    # Si llegamos aquí, la transacción fue exitosa
                    # Desactivar buffer y escribir logs a DB
                    self._use_log_buffer = False
                    self._flush_log_buffer()
                    
                except Exception as e:
                    # Error durante import - guardar logs a archivo
                    self._use_log_buffer = False
                    self._flush_log_buffer_to_file()
                    raise
            else:
                # Dry run - solo contar
                for model_path, model_data in input_data['models'].items():
                    if model_data:
                        imported_counts[model_path] = len(model_data)
                        self.log('info', f"[DRY RUN] Importaría {len(model_data)} registros de {model_path}")
            
            # Extraer archivos media del archivo fuente (si es tar.gz)
            media_result = {'extracted': 0, 'skipped': 0, 'errors': [], 'checksum_errors': []}
            if source_file_path and not options.get('dry_run'):
                if self.job:
                    self.job.update_progress(92, "Extrayendo archivos media")
                
                # Pasar metadatos de media para validación de checksums
                media_metadata = input_data.get('media_files', {})
                media_result = self.extract_media_files(source_file_path, media_metadata=media_metadata)
                
                if self.job:
                    self.job.files_transferred = media_result['extracted']
                    self.job.save(update_fields=['files_transferred'])
                
                # Advertir sobre errores de checksum
                if media_result.get('checksum_errors'):
                    self.log('warning', f"{len(media_result['checksum_errors'])} archivos con checksums inválidos")
            
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
                'dry_run': options.get('dry_run', False),
                'media_files': media_result
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
        Importa un modelo específico con manejo robusto de conflictos.
        
        Verifica duplicados por:
        - PK (id)
        - Campos con unique=True
        - Combinaciones unique_together
        
        Args:
            model_path: str como 'events.Event'
            data_list: lista de dicts con datos
            **options: opciones de import
                - skip_existing: saltar registros existentes (default: True)
                - overwrite: sobrescribir registros existentes
                - merge: mergear campos no-nulos en existentes
            
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
                
                # Verificar existencia por TODOS los campos únicos (no solo PK)
                exists, existing_instance, conflict_field = self._check_exists_by_unique_fields(
                    model, item_data
                )
                
                if exists:
                    if options.get('skip_existing', False):
                        skipped += 1
                        logger.debug(
                            f"Saltando {model_path} pk={pk} "
                            f"(conflicto en: {conflict_field})"
                        )
                        continue
                    elif options.get('overwrite', False):
                        self._update_instance(existing_instance, item_data)
                        imported += 1
                        logger.debug(
                            f"Actualizado {model_path} pk={pk} "
                            f"(conflicto en: {conflict_field})"
                        )
                    elif options.get('merge', False):
                        self._merge_instance(existing_instance, item_data)
                        imported += 1
                        logger.debug(
                            f"Mergeado {model_path} pk={pk} "
                            f"(conflicto en: {conflict_field})"
                        )
                    else:
                        # Default: skip existentes
                        skipped += 1
                        logger.debug(
                            f"Saltando {model_path} pk={pk} "
                            f"(conflicto en: {conflict_field})"
                        )
                        continue
                else:
                    # No existe, crear nuevo con manejo de IntegrityError
                    self._create_instance_safe(model, item_data)
                    imported += 1
                    
            except Exception as e:
                errors.append({
                    'model': model_path,
                    'pk': pk,
                    'error': str(e)
                })
                logger.error(f"Error importando {model_path} pk={pk}: {e}")
                # NO re-raise para no corromper la transacción
        
        if errors:
            self.log('warning', f"{model_path}: {len(errors)} errores de {len(data_list)} registros")
        if skipped > 0:
            self.log('info', f"{model_path}: {skipped} registros saltados (ya existentes)")
        
        return imported
    
    def _get_unique_fields(self, model):
        """
        Obtiene todos los campos con constraint de unicidad.
        
        Args:
            model: Django model class
            
        Returns:
            tuple: (unique_fields: list, unique_together: list)
                - unique_fields: lista de nombres de campos individuales con unique=True
                - unique_together: lista de tuplas con combinaciones de campos únicos
        """
        unique_fields = []
        unique_together = []
        
        # Campos individuales con unique=True
        for field in model._meta.get_fields():
            if hasattr(field, 'unique') and field.unique and not field.primary_key:
                unique_fields.append(field.name)
        
        # unique_together constraints
        if hasattr(model._meta, 'unique_together') and model._meta.unique_together:
            unique_together = list(model._meta.unique_together)
        
        # También revisar constraints modernos (Django 2.2+)
        if hasattr(model._meta, 'constraints'):
            for constraint in model._meta.constraints:
                # UniqueConstraint
                if constraint.__class__.__name__ == 'UniqueConstraint':
                    if hasattr(constraint, 'fields'):
                        fields_tuple = tuple(constraint.fields)
                        if fields_tuple not in unique_together:
                            unique_together.append(fields_tuple)
        
        return unique_fields, unique_together
    
    def _check_exists_by_unique_fields(self, model, data):
        """
        Verifica si existe una instancia con los mismos valores en campos únicos.
        
        Verifica en este orden:
        1. Por PK (id)
        2. Por campos individuales con unique=True
        3. Por combinaciones unique_together
        
        Args:
            model: Django model class
            data: dict con datos a importar
            
        Returns:
            tuple: (exists: bool, instance: Model|None, conflict_field: str|None)
        """
        # 1. Verificar por PK primero
        pk = data.get('id') or data.get('pk')
        if pk:
            try:
                instance = model.objects.get(pk=pk)
                return True, instance, 'pk'
            except model.DoesNotExist:
                pass
        
        # 2. Obtener campos únicos del modelo
        unique_fields, unique_together = self._get_unique_fields(model)
        
        # 3. Verificar por campos individuales únicos
        for field_name in unique_fields:
            if field_name in data and data[field_name] is not None:
                try:
                    instance = model.objects.get(**{field_name: data[field_name]})
                    return True, instance, field_name
                except model.DoesNotExist:
                    continue
                except model.MultipleObjectsReturned:
                    # Si hay múltiples, hay un problema de datos
                    logger.warning(
                        f"Múltiples instancias de {model.__name__} con "
                        f"{field_name}={data[field_name]}"
                    )
                    instance = model.objects.filter(**{field_name: data[field_name]}).first()
                    return True, instance, field_name
        
        # 4. Verificar por unique_together
        for fields_tuple in unique_together:
            lookup = {}
            all_present = True
            
            for field_name in fields_tuple:
                # Verificar tanto field_name como field_name_id para FKs
                if field_name in data and data[field_name] is not None:
                    lookup[field_name] = data[field_name]
                elif f"{field_name}_id" in data and data[f"{field_name}_id"] is not None:
                    lookup[f"{field_name}_id"] = data[f"{field_name}_id"]
                else:
                    all_present = False
                    break
            
            if all_present and lookup:
                try:
                    instance = model.objects.get(**lookup)
                    conflict_desc = f"unique_together({', '.join(fields_tuple)})"
                    return True, instance, conflict_desc
                except model.DoesNotExist:
                    continue
                except model.MultipleObjectsReturned:
                    logger.warning(
                        f"Múltiples instancias de {model.__name__} con "
                        f"unique_together: {lookup}"
                    )
                    instance = model.objects.filter(**lookup).first()
                    conflict_desc = f"unique_together({', '.join(fields_tuple)})"
                    return True, instance, conflict_desc
        
        return False, None, None
    
    def _resolve_foreign_keys(self, model, data):
        """
        Convierte ForeignKeys nested (dicts) o strings a IDs simples.
        También maneja campos terminados en _id que son FKs.
        
        Args:
            model: Django model class
            data: dict con datos a importar
            
        Returns:
            dict con FKs resueltos a IDs
        """
        resolved_data = data.copy()
        
        for field in model._meta.get_fields():
            # Solo procesar ForeignKey y OneToOne
            if not (hasattr(field, 'related_model') and field.many_to_one):
                continue
            
            field_name = field.name
            field_id_name = f"{field_name}_id"
            
            # Caso 1: Campo FK viene como dict nested (de serializers DRF viejos)
            if field_name in resolved_data and isinstance(resolved_data[field_name], dict):
                fk_dict = resolved_data[field_name]
                fk_id = fk_dict.get('id') or fk_dict.get('pk')
                if fk_id:
                    resolved_data[field_id_name] = fk_id
                # Remover el dict nested
                del resolved_data[field_name]
            
            # Caso 2: Campo FK_id ya viene correcto (de MigrationSerializer)
            elif field_id_name in resolved_data:
                # Ya está en formato correcto, no hacer nada
                pass
            
            # Caso 3: Campo FK viene como string/int directo
            elif field_name in resolved_data and not isinstance(resolved_data[field_name], dict):
                fk_value = resolved_data[field_name]
                if fk_value is not None:
                    resolved_data[field_id_name] = fk_value
                # Remover el campo FK directo
                if field_name in resolved_data:
                    del resolved_data[field_name]
        
        return resolved_data
    
    def _create_instance(self, model, data):
        """
        Crea una nueva instancia del modelo manejando correctamente M2M y FKs.
        
        Args:
            model: Django model class
            data: dict con datos a importar
            
        Returns:
            instancia creada
        """
        # Paso 1: Resolver ForeignKeys nested a IDs simples
        data = self._resolve_foreign_keys(model, data)
        
        # Paso 2: Separar campos M2M del resto
        m2m_data = {}
        clean_data = {}
        
        # Extraer metadata de M2M si existe
        if '_m2m_relations' in data:
            m2m_data = data.pop('_m2m_relations')
        
        # Separar campos según tipo
        for field in model._meta.get_fields():
            # Skip campos auto-creados y reverse relations
            if field.auto_created and not field.concrete:
                continue
            
            field_name = field.name
            
            # Many-to-Many: extraer a m2m_data
            if field.many_to_many:
                if field_name in data:
                    m2m_data[field_name] = data[field_name]
            # Campos normales (incluyendo FKs ya resueltos a _id)
            elif field_name in data:
                clean_data[field_name] = data[field_name]
            # FK fields terminados en _id
            elif hasattr(field, 'related_model') and f"{field_name}_id" in data:
                clean_data[f"{field_name}_id"] = data[f"{field_name}_id"]
        
        # Paso 3: Crear instancia SIN M2M
        instance = model.objects.create(**clean_data)
        
        # Paso 4: Asignar M2M después de crear la instancia
        for field_name, value in m2m_data.items():
            if hasattr(instance, field_name):
                try:
                    # Usar .set() para M2M (no asignación directa)
                    m2m_field = getattr(instance, field_name)
                    if hasattr(m2m_field, 'set'):
                        # value debe ser una lista de IDs
                        if isinstance(value, list):
                            m2m_field.set(value)
                        else:
                            logger.warning(f"M2M field {field_name} tiene valor no-lista: {type(value)}")
                except Exception as e:
                    logger.warning(f"Error asignando M2M {field_name}: {e}")
        
        return instance
    
    def _create_instance_safe(self, model, data):
        """
        Crea instancia con manejo robusto de IntegrityError.
        Si falla por constraint de unicidad, intenta encontrar la instancia existente
        y la retorna en lugar de fallar.
        
        Args:
            model: Django model class
            data: dict con datos a importar
            
        Returns:
            instancia creada o encontrada
            
        Raises:
            Exception: si es un error diferente a IntegrityError de unicidad
        """
        try:
            return self._create_instance(model, data)
        except DBIntegrityError as e:
            error_msg = str(e)
            
            # Verificar si es un error de constraint de unicidad
            if 'duplicate key' in error_msg or 'UNIQUE constraint' in error_msg or 'unique constraint' in error_msg:
                logger.warning(
                    f"IntegrityError al crear {model.__name__}: {error_msg[:200]}"
                )
                
                # Intentar encontrar la instancia existente por campos únicos
                unique_fields, unique_together = self._get_unique_fields(model)
                
                # Buscar por campos individuales únicos
                for field_name in unique_fields:
                    if field_name in data and data[field_name] is not None:
                        try:
                            instance = model.objects.get(**{field_name: data[field_name]})
                            logger.info(
                                f"Encontrada instancia existente de {model.__name__} "
                                f"por campo único: {field_name}={data[field_name]}"
                            )
                            return instance
                        except model.DoesNotExist:
                            continue
                        except model.MultipleObjectsReturned:
                            instance = model.objects.filter(**{field_name: data[field_name]}).first()
                            logger.warning(
                                f"Múltiples instancias encontradas por {field_name}, "
                                f"usando la primera"
                            )
                            return instance
                
                # Buscar por unique_together
                for fields_tuple in unique_together:
                    lookup = {}
                    all_present = True
                    
                    for field_name in fields_tuple:
                        if field_name in data and data[field_name] is not None:
                            lookup[field_name] = data[field_name]
                        elif f"{field_name}_id" in data and data[f"{field_name}_id"] is not None:
                            lookup[f"{field_name}_id"] = data[f"{field_name}_id"]
                        else:
                            all_present = False
                            break
                    
                    if all_present and lookup:
                        try:
                            instance = model.objects.get(**lookup)
                            logger.info(
                                f"Encontrada instancia existente de {model.__name__} "
                                f"por unique_together: {fields_tuple}"
                            )
                            return instance
                        except model.DoesNotExist:
                            continue
                        except model.MultipleObjectsReturned:
                            instance = model.objects.filter(**lookup).first()
                            return instance
                
                # Si no encontramos la instancia por campos únicos, re-raise
                logger.error(
                    f"IntegrityError pero no se pudo encontrar instancia existente "
                    f"para {model.__name__}"
                )
                raise
            else:
                # Otro tipo de IntegrityError (FK inválido, etc.)
                logger.error(f"IntegrityError en {model.__name__}: {error_msg}")
                raise
    
    def _update_instance(self, instance, data):
        """
        Actualiza una instancia existente con nuevos datos.
        Maneja correctamente M2M y FKs.
        """
        model = instance.__class__
        
        # Resolver FKs
        data = self._resolve_foreign_keys(model, data)
        
        # Separar M2M
        m2m_data = {}
        if '_m2m_relations' in data:
            m2m_data = data.pop('_m2m_relations')
        
        # Identificar campos M2M del modelo
        for field in model._meta.get_fields():
            if field.many_to_many and field.name in data:
                m2m_data[field.name] = data.pop(field.name)
        
        # Actualizar campos normales
        model_fields = [f.name for f in model._meta.get_fields() 
                       if not f.many_to_many and (not f.auto_created or f.concrete)]
        
        for key, value in data.items():
            if key in model_fields and hasattr(instance, key):
                setattr(instance, key, value)
            # También manejar campos _id para FKs
            elif key.endswith('_id') and hasattr(instance, key):
                setattr(instance, key, value)
        
        instance.save()
        
        # Actualizar M2M
        for field_name, value in m2m_data.items():
            if hasattr(instance, field_name):
                try:
                    m2m_field = getattr(instance, field_name)
                    if hasattr(m2m_field, 'set') and isinstance(value, list):
                        m2m_field.set(value)
                except Exception as e:
                    logger.warning(f"Error actualizando M2M {field_name}: {e}")
        
        return instance
    
    def _merge_instance(self, instance, data):
        """
        Merge de instancia existente con nuevos datos (solo campos no nulos).
        Maneja correctamente M2M y FKs.
        """
        model = instance.__class__
        
        # Resolver FKs
        data = self._resolve_foreign_keys(model, data)
        
        # Separar M2M
        m2m_data = {}
        if '_m2m_relations' in data:
            m2m_data = data.pop('_m2m_relations')
        
        for field in model._meta.get_fields():
            if field.many_to_many and field.name in data:
                m2m_data[field.name] = data.pop(field.name)
        
        # Merge campos normales (solo si actual es None/vacío)
        model_fields = [f.name for f in model._meta.get_fields() 
                       if not f.many_to_many and (not f.auto_created or f.concrete)]
        
        for key, value in data.items():
            if (key in model_fields or key.endswith('_id')) and value is not None:
                if hasattr(instance, key):
                    current_value = getattr(instance, key)
                    if current_value is None or current_value == '':
                        setattr(instance, key, value)
        
        instance.save()
        
        # Merge M2M solo si actual está vacío
        for field_name, value in m2m_data.items():
            if hasattr(instance, field_name):
                try:
                    m2m_field = getattr(instance, field_name)
                    if hasattr(m2m_field, 'count') and m2m_field.count() == 0:
                        if hasattr(m2m_field, 'set') and isinstance(value, list):
                            m2m_field.set(value)
                except Exception as e:
                    logger.warning(f"Error mergeando M2M {field_name}: {e}")
        
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
        
        # Asegurar que el directorio existe
        checkpoint_dir = Path(self.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # Exportar datos actuales
        export_service = PlatformExportService()
        timestamp = timezone.now().strftime('%Y%m%d-%H%M%S')
        checkpoint_file = checkpoint_dir / f"{name}-{timestamp}.json.gz"
        
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
        Valida que el formato del export sea correcto y completo.
        
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
        
        # Validar estructura de modelos
        if not isinstance(export_data['models'], dict):
            self.log('error', "Campo 'models' debe ser un diccionario")
            return False
        
        # Validar modelos críticos presentes
        critical_models = [
            'users.User',
            'events.Event',
            'events.Order',
            'experiences.Experience',
            'organizers.Organizer',
        ]
        
        missing_critical = []
        for model in critical_models:
            if model not in export_data['models'] or not export_data['models'][model]:
                missing_critical.append(model)
        
        if missing_critical:
            self.log('warning', f"Modelos críticos faltantes: {', '.join(missing_critical)}")
        
        # Validar estructura de cada modelo
        # Nota: El formato puede ser directo (serializer) o Django-style (pk/fields)
        # Ambos son válidos, solo validamos que sean diccionarios con datos
        invalid_models = []
        for model_path, records in export_data['models'].items():
            if records and isinstance(records, list) and len(records) > 0:
                first_record = records[0]
                if not isinstance(first_record, dict):
                    invalid_models.append(f"{model_path}: registros no son diccionarios")
                elif not first_record:  # Diccionario vacío
                    invalid_models.append(f"{model_path}: registros vacíos")
                # No validar 'pk'/'fields' porque el formato puede variar
        
        if invalid_models:
            self.log('error', f"Modelos con estructura inválida: {', '.join(invalid_models[:5])}")
            return False
        
        return True
    
    def verify_import(self, expected_statistics):
        """
        Verifica que el import fue exitoso comparando estadísticas y validando FK.
        
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
        
        # Validar relaciones FK (usando IntegrityVerificationService si existe)
        try:
            from apps.migration_system.services.integrity_verification import IntegrityVerificationService
            integrity_service = IntegrityVerificationService()
            fk_verification = integrity_service.verify_relationships()
            
            if not fk_verification['success']:
                broken_fk_count = len(fk_verification.get('broken_relationships', []))
                if broken_fk_count > 0:
                    errors.append(f"FK rotas detectadas: {broken_fk_count} relaciones")
                    # Agregar detalles de las primeras 5 FK rotas
                    for broken in fk_verification.get('broken_relationships', [])[:5]:
                        warnings.append(f"FK rota: {broken['model']} campo {broken['field']}")
        except (ImportError, AttributeError):
            # IntegrityVerificationService no existe, skip
            pass
        
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
        Detecta automáticamente el tipo de archivo por contenido (magic bytes),
        no por extensión.
        
        Args:
            file_path: ruta del archivo
            
        Returns:
            dict con datos
        """
        import tarfile
        
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
        
        # Leer magic bytes para detectar tipo de archivo
        with open(file_path, 'rb') as f:
            magic = f.read(10)
        
        is_gzip = magic[:2] == b'\x1f\x8b'
        
        # Intentar abrir como TAR.GZ primero (detectar por contenido, no extensión)
        if is_gzip:
            try:
                with tarfile.open(file_path, 'r:gz') as tar:
                    # Buscar el archivo de datos JSON dentro del tar
                    data_file = None
                    for member in tar.getmembers():
                        if member.name == 'data.json.gz' or member.name.endswith('/data.json.gz'):
                            data_file = member
                            break
                        elif member.name == 'data.json' or member.name.endswith('/data.json'):
                            data_file = member
                            break
                    
                    if data_file:
                        # Es un TAR.GZ válido con datos
                        extracted = tar.extractfile(data_file)
                        if extracted is None:
                            raise ValueError(f"No se pudo extraer {data_file.name}")
                        
                        if data_file.name.endswith('.gz'):
                            with gzip.open(extracted, 'rt', encoding='utf-8') as f:
                                return json.load(f)
                        else:
                            return json.loads(extracted.read().decode('utf-8'))
            except tarfile.TarError:
                # No es un tar, intentar como gzip simple
                pass
            
            # Intentar como gzip simple (JSON comprimido)
            try:
                with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                raise ValueError(f"Archivo gzip no contiene JSON válido: {e}")
        
        # Intentar como JSON plano
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def extract_media_files(self, archive_path, target_dir=None, media_metadata=None):
        """
        Extrae archivos media de un archivo TAR.GZ al directorio de media.
        Valida checksums MD5 si se proporcionan metadatos.
        
        Args:
            archive_path: ruta al archivo tar.gz
            target_dir: directorio destino (default: MEDIA_ROOT)
            media_metadata: dict con metadatos de archivos (para validación checksums)
            
        Returns:
            dict con estadísticas de extracción
        """
        import tarfile
        from django.conf import settings
        from django.core.files.storage import default_storage
        from apps.migration_system.utils import calculate_file_checksum_from_path
        
        archive_path = Path(archive_path)
        
        if not archive_path.exists():
            return {'extracted': 0, 'skipped': 0, 'errors': [], 'checksum_errors': []}
        
        # Verificar si es un tar.gz
        with open(archive_path, 'rb') as f:
            magic = f.read(2)
        
        if magic != b'\x1f\x8b':
            self.log('info', "Archivo no es tar.gz, omitiendo extracción de media")
            return {'extracted': 0, 'skipped': 0, 'errors': [], 'checksum_errors': []}
        
        try:
            with tarfile.open(archive_path, 'r:gz') as tar:
                # Buscar directorio media en el tar
                media_members = [m for m in tar.getmembers() 
                               if m.name.startswith('media/') and m.isfile()]
                
                if not media_members:
                    self.log('info', "No hay archivos media en el archivo")
                    return {'extracted': 0, 'skipped': 0, 'errors': [], 'checksum_errors': []}
                
                self.log('info', f"Encontrados {len(media_members)} archivos media para extraer")
                
                # Determinar directorio destino
                if target_dir is None:
                    target_dir = Path(settings.MEDIA_ROOT)
                else:
                    target_dir = Path(target_dir)
                
                target_dir.mkdir(parents=True, exist_ok=True)
                
                extracted = 0
                skipped = 0
                errors = []
                checksum_errors = []
                
                for member in media_members:
                    try:
                        # Ruta relativa sin el prefijo 'media/'
                        relative_path = member.name[6:]  # Quitar 'media/'
                        dest_path = target_dir / relative_path
                        
                        # Verificar si ya existe
                        if dest_path.exists():
                            skipped += 1
                            continue
                        
                        # Crear directorio padre si no existe
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Extraer archivo
                        file_obj = tar.extractfile(member)
                        if file_obj:
                            with open(dest_path, 'wb') as dest_file:
                                import shutil
                                shutil.copyfileobj(file_obj, dest_file)
                            
                            # Validar checksum si se proporcionaron metadatos
                            if media_metadata and relative_path in media_metadata:
                                expected_checksum = media_metadata[relative_path].get('checksum')
                                if expected_checksum:
                                    actual_checksum = calculate_file_checksum_from_path(str(dest_path))
                                    if actual_checksum != expected_checksum:
                                        checksum_errors.append({
                                            'file': relative_path,
                                            'expected': expected_checksum,
                                            'actual': actual_checksum
                                        })
                                        logger.error(f"Checksum inválido para {relative_path}: esperado {expected_checksum}, actual {actual_checksum}")
                            
                            extracted += 1
                            
                            # Actualizar progreso cada 10 archivos
                            if extracted % 10 == 0 and self.job:
                                self.job.files_transferred = extracted
                                self.job.save(update_fields=['files_transferred'])
                    
                    except Exception as e:
                        errors.append(f"{member.name}: {str(e)}")
                        logger.warning(f"Error extrayendo {member.name}: {e}")
                
                self.log('info', f"Media extraídos: {extracted}, omitidos: {skipped}, errores: {len(errors)}")
                if checksum_errors:
                    self.log('warning', f"Archivos con checksum inválido: {len(checksum_errors)}")
                
                return {
                    'extracted': extracted,
                    'skipped': skipped,
                    'errors': errors,
                    'checksum_errors': checksum_errors
                }
                
        except tarfile.TarError as e:
            self.log('warning', f"Error abriendo archivo tar: {e}")
            return {'extracted': 0, 'skipped': 0, 'errors': [str(e)], 'checksum_errors': []}
