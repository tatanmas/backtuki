"""
Restore Service - Orquestador principal del restore desde backup GCP
"""

import tarfile
import tempfile
import logging
import shutil
from pathlib import Path
from typing import Dict

from .validator import BackupValidator
from .sql_restore import SQLRestoreService
from .media_restore import MediaRestoreService

logger = logging.getLogger(__name__)


class RestoreService:
    """
    Orquestador principal del restore desde backup.
    ~140 líneas, coordina validación, SQL y media restore.
    """
    
    def __init__(self, job):
        self.job = job
        self.validator = BackupValidator()
        self.sql_service = SQLRestoreService(job)
        self.media_service = MediaRestoreService(job)
        self.temp_dir = None
    
    def execute(self) -> Dict:
        """
        Ejecuta el restore completo.
        
        Returns:
            {
                'success': bool,
                'summary': {
                    'sql_records': int,
                    'media_files': int,
                    'media_size_mb': float
                },
                'errors': List[str]
            }
        """
        errors = []
        summary = {
            'sql_records': 0,
            'media_files': 0,
            'media_size_mb': 0.0
        }
        
        try:
            self.job.start()
            
            # 1. Extraer tar.gz
            self.job.update_progress(5, "Extrayendo backup...")
            self.temp_dir = self._extract_backup()
            
            # 2. Validar estructura
            self.job.update_progress(10, "Validando estructura...")
            validation = self.validator.validate(Path(self.job.backup_file.path))
            
            if not validation['valid']:
                errors.extend(validation['errors'])
                raise Exception("Backup inválido: " + ", ".join(errors))
            
            # Guardar metadata
            self.job.backup_metadata = validation['metadata']
            self.job.save(update_fields=['backup_metadata'])
            
            # 3. Restore SQL (si está habilitado)
            if self.job.restore_sql:
                self.job.update_progress(15, "Iniciando restore SQL...")
                sql_result = self._restore_sql()
                
                if not sql_result['success']:
                    errors.extend(sql_result['errors'])
                    raise Exception("Restore SQL falló")
                
                summary['sql_records'] = sql_result['records_restored']
                self.job.sql_records_restored = sql_result['records_restored']
                self.job.safety_backup_path = sql_result.get('safety_backup', '')
                self.job.save(update_fields=['sql_records_restored', 'safety_backup_path'])
            
            # 4. Restore Media (si está habilitado)
            if self.job.restore_media:
                self.job.update_progress(60, "Iniciando restore media...")
                media_result = self._restore_media()
                
                if not media_result['success']:
                    errors.extend(media_result['errors'])
                    # No fallar por media, solo advertir
                    logger.warning(f"Media restore tuvo errores: {media_result['errors']}")
                
                summary['media_files'] = media_result['files_copied']
                summary['media_size_mb'] = media_result['total_size_mb']
                self.job.media_files_restored = media_result['files_copied']
                self.job.media_size_mb = media_result['total_size_mb']
                self.job.save(update_fields=['media_files_restored', 'media_size_mb'])
            
            # 5. Cleanup
            self.job.update_progress(98, "Limpiando archivos temporales...")
            self._cleanup()
            
            # 6. Completar
            self.job.complete()
            
            return {
                'success': True,
                'summary': summary,
                'errors': errors
            }
            
        except Exception as e:
            logger.exception("Error en restore")
            self.job.fail(str(e), traceback=str(e))
            self._cleanup()
            return {
                'success': False,
                'summary': summary,
                'errors': errors + [str(e)]
            }
    
    def _extract_backup(self) -> Path:
        """Extrae el tar.gz a directorio temporal."""
        temp_dir = Path(tempfile.mkdtemp(prefix='tuki_restore_'))
        
        with tarfile.open(self.job.backup_file.path, 'r:gz') as tar:
            tar.extractall(temp_dir)
        
        logger.info(f"Backup extraído a: {temp_dir}")
        return temp_dir
    
    def _restore_sql(self) -> Dict:
        """Ejecuta restore SQL."""
        # Buscar archivo SQL dump
        sql_dumps = list(self.temp_dir.rglob('cloudsql/*.sql.gz'))
        
        if not sql_dumps:
            return {
                'success': False,
                'records_restored': 0,
                'errors': ['No se encontró dump SQL en el backup']
            }
        
        # Usar el primer dump encontrado
        sql_dump_path = sql_dumps[0]
        logger.info(f"Usando dump SQL: {sql_dump_path}")
        
        return self.sql_service.restore(sql_dump_path)
    
    def _restore_media(self) -> Dict:
        """Ejecuta restore media."""
        # Buscar directorio media
        media_dirs = list(self.temp_dir.glob('gcs/tuki-media-prod-*'))
        
        if not media_dirs:
            return {
                'success': False,
                'files_copied': 0,
                'total_size_mb': 0.0,
                'errors': ['No se encontró directorio media en el backup']
            }
        
        # Usar el primer directorio encontrado
        media_dir = media_dirs[0]
        logger.info(f"Usando directorio media: {media_dir}")
        
        return self.media_service.restore(media_dir)
    
    def _cleanup(self):
        """Limpia archivos temporales."""
        if self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"Directorio temporal eliminado: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"No se pudo eliminar temp dir: {e}")
