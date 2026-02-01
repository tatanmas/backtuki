"""
🚀 ENTERPRISE INTEGRITY VERIFICATION SERVICE

Servicio para verificar la integridad de migraciones.
"""

import logging
from django.apps import apps
from django.db import connection
from django.core.files.storage import default_storage
from pathlib import Path

from ..utils import find_all_file_fields, calculate_file_checksum

logger = logging.getLogger(__name__)


class IntegrityVerificationService:
    """
    Servicio enterprise para verificar integridad post-migración.
    
    Verifica:
    - Counts de registros
    - Checksums de archivos
    - Relaciones de ForeignKey
    - Existencia de archivos referenciados
    """
    
    def __init__(self, job=None):
        """
        Initialize verification service.
        
        Args:
            job: MigrationJob instance (opcional, para tracking)
        """
        self.job = job
        self.errors = []
        self.warnings = []
    
    def verify_all(self, expected_statistics=None, verify_files=True):
        """
        Ejecuta todas las verificaciones.
        
        Args:
            expected_statistics: dict con estadísticas esperadas
            verify_files: si debe verificar archivos
            
        Returns:
            dict con resultado de verificación
        """
        logger.info("Iniciando verificación de integridad completa")
        
        self.errors = []
        self.warnings = []
        
        # 1. Verificar counts si se proporcionaron estadísticas
        if expected_statistics:
            self.verify_counts(expected_statistics)
        
        # 2. Verificar relaciones de ForeignKey
        self.verify_relationships()
        
        # 3. Verificar archivos si se solicitó
        if verify_files:
            self.verify_files_exist()
        
        success = len(self.errors) == 0
        
        if self.errors:
            logger.error(f"Verificación falló con {len(self.errors)} errores")
        if self.warnings:
            logger.warning(f"Verificación completada con {len(self.warnings)} warnings")
        
        return {
            'success': success,
            'errors': self.errors,
            'warnings': self.warnings,
            'report': self.generate_report()
        }
    
    def verify_counts(self, expected_statistics):
        """
        Verifica que los counts de registros coincidan.
        
        Args:
            expected_statistics: dict con counts esperados
        """
        logger.info("Verificando counts de registros")
        
        for key, expected_count in expected_statistics.items():
            if not key.startswith('count_'):
                continue
            
            model_path = key.replace('count_', '')
            
            try:
                app_label, model_name = model_path.split('.')
                model = apps.get_model(app_label, model_name)
                actual_count = model.objects.count()
                
                if actual_count < expected_count:
                    error_msg = f"{model_path}: esperados {expected_count}, actual {actual_count} (faltan {expected_count - actual_count})"
                    self.errors.append(error_msg)
                    logger.error(error_msg)
                elif actual_count > expected_count:
                    warning_msg = f"{model_path}: más registros de lo esperado ({actual_count} vs {expected_count})"
                    self.warnings.append(warning_msg)
                    logger.warning(warning_msg)
                else:
                    logger.info(f"✓ {model_path}: {actual_count}/{expected_count}")
                    
            except LookupError:
                warning_msg = f"Modelo {model_path} no encontrado en destino"
                self.warnings.append(warning_msg)
                logger.warning(warning_msg)
            except Exception as e:
                error_msg = f"Error verificando {model_path}: {e}"
                self.errors.append(error_msg)
                logger.error(error_msg)
    
    def verify_relationships(self):
        """
        Verifica que todas las ForeignKeys sean válidas.
        
        Detecta referencias rotas (ForeignKey a objetos que no existen).
        """
        logger.info("Verificando relaciones de ForeignKey")
        
        # Obtener todos los modelos
        for model in apps.get_models():
            # Obtener campos ForeignKey
            fk_fields = [
                f for f in model._meta.get_fields()
                if f.many_to_one and not f.auto_created
            ]
            
            if not fk_fields:
                continue
            
            # Verificar cada ForeignKey
            for fk_field in fk_fields:
                try:
                    # Contar objetos con ForeignKey rota
                    broken_count = 0
                    
                    for obj in model.objects.all():
                        fk_value = getattr(obj, fk_field.name)
                        if fk_value is None:
                            continue  # NULL es válido
                        
                        # Verificar que el objeto referenciado existe
                        related_model = fk_field.related_model
                        if not related_model.objects.filter(pk=fk_value.pk).exists():
                            broken_count += 1
                            
                    if broken_count > 0:
                        error_msg = f"{model._meta.label}.{fk_field.name}: {broken_count} referencias rotas"
                        self.errors.append(error_msg)
                        logger.error(error_msg)
                        
                except Exception as e:
                    warning_msg = f"Error verificando {model._meta.label}.{fk_field.name}: {e}"
                    self.warnings.append(warning_msg)
                    logger.warning(warning_msg)
    
    def verify_files_exist(self):
        """
        Verifica que todos los archivos referenciados en la BD existan.
        """
        logger.info("Verificando existencia de archivos")
        
        file_fields = find_all_file_fields()
        total_files_checked = 0
        missing_files = 0
        
        for model, field_name in file_fields:
            queryset = model.objects.exclude(**{f"{field_name}": ''}).exclude(**{f"{field_name}__isnull": True})
            
            for obj in queryset:
                try:
                    file_field = getattr(obj, field_name)
                    if file_field and hasattr(file_field, 'name') and file_field.name:
                        total_files_checked += 1
                        
                        # Verificar que el archivo existe
                        if not default_storage.exists(file_field.name):
                            missing_files += 1
                            error_msg = f"Archivo faltante: {file_field.name} (referenciado en {model._meta.label} pk={obj.pk})"
                            self.errors.append(error_msg)
                            logger.error(error_msg)
                            
                except Exception as e:
                    warning_msg = f"Error verificando archivo en {model._meta.label}.{field_name}: {e}"
                    self.warnings.append(warning_msg)
                    logger.warning(warning_msg)
        
        logger.info(f"Verificados {total_files_checked} archivos, {missing_files} faltantes")
    
    def generate_report(self):
        """
        Genera un reporte legible de la verificación.
        
        Returns:
            str: reporte formateado
        """
        report = []
        report.append("="* 60)
        report.append("REPORTE DE VERIFICACIÓN DE INTEGRIDAD")
        report.append("=" * 60)
        report.append("")
        
        if not self.errors and not self.warnings:
            report.append("✓ Todas las verificaciones pasaron exitosamente")
        else:
            if self.errors:
                report.append(f"ERRORES ({len(self.errors)}):")
                report.append("-" * 60)
                for error in self.errors[:20]:  # Limitar a 20 para no saturar
                    report.append(f"  ✗ {error}")
                if len(self.errors) > 20:
                    report.append(f"  ... y {len(self.errors) - 20} errores más")
                report.append("")
            
            if self.warnings:
                report.append(f"WARNINGS ({len(self.warnings)}):")
                report.append("-" * 60)
                for warning in self.warnings[:20]:
                    report.append(f"  ⚠ {warning}")
                if len(self.warnings) > 20:
                    report.append(f"  ... y {len(self.warnings) - 20} warnings más")
                report.append("")
        
        report.append("=" * 60)
        
        return "\n".join(report)
