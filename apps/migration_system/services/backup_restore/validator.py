"""
Backup Validator - Valida estructura y contenido del backup tar.gz
"""

import tarfile
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class BackupValidator:
    """
    Valida que un backup .tar.gz tenga la estructura esperada.
    ~80 líneas, single responsibility.
    """
    
    REQUIRED_DIRS = ['cloudsql', 'gcs']
    REQUIRED_FILES_PATTERN = {
        'cloudsql': '*.sql.gz',
        'gcs': 'tuki-media-prod-*',
    }
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.metadata: Dict = {}
    
    def validate(self, backup_path: Path) -> Dict:
        """
        Valida el backup completo.
        
        Returns:
            {
                'valid': bool,
                'errors': List[str],
                'warnings': List[str],
                'metadata': Dict
            }
        """
        self.errors = []
        self.warnings = []
        self.metadata = {}
        
        try:
            # 1. Verificar que es tar.gz válido
            if not self._validate_tarfile(backup_path):
                return self._build_result(False)
            
            # 2. Verificar estructura de directorios
            if not self._validate_structure(backup_path):
                return self._build_result(False)
            
            # 3. Verificar archivos SQL
            if not self._validate_sql_dumps(backup_path):
                self.warnings.append("No se encontraron dumps SQL válidos")
            
            # 4. Verificar archivos media
            if not self._validate_media_files(backup_path):
                self.warnings.append("No se encontraron archivos media")
            
            return self._build_result(len(self.errors) == 0)
            
        except Exception as e:
            logger.exception("Error validando backup")
            self.errors.append(f"Error inesperado: {str(e)}")
            return self._build_result(False)
    
    def _validate_tarfile(self, path: Path) -> bool:
        """Verifica que sea un tar.gz válido."""
        try:
            with tarfile.open(path, 'r:gz') as tar:
                self.metadata['total_files'] = len(tar.getmembers())
                return True
        except Exception as e:
            self.errors.append(f"Archivo tar.gz inválido: {str(e)}")
            return False
    
    def _validate_structure(self, path: Path) -> bool:
        """Verifica estructura de directorios."""
        with tarfile.open(path, 'r:gz') as tar:
            members = [m.name for m in tar.getmembers()]
            
            for required_dir in self.REQUIRED_DIRS:
                if not any(required_dir in m for m in members):
                    self.errors.append(f"Directorio requerido no encontrado: {required_dir}/")
                    return False
        
        return True
    
    def _validate_sql_dumps(self, path: Path) -> bool:
        """Verifica que existan dumps SQL."""
        with tarfile.open(path, 'r:gz') as tar:
            sql_files = [m for m in tar.getmembers() if 'cloudsql' in m.name and m.name.endswith('.sql.gz')]
            self.metadata['sql_dumps_count'] = len(sql_files)
            return len(sql_files) > 0
    
    def _validate_media_files(self, path: Path) -> bool:
        """Verifica que existan archivos media."""
        with tarfile.open(path, 'r:gz') as tar:
            media_files = [m for m in tar.getmembers() if 'gcs/tuki-media-prod' in m.name and m.isfile()]
            self.metadata['media_files_count'] = len(media_files)
            total_size_mb = sum(m.size for m in media_files) / (1024 * 1024)
            self.metadata['media_size_mb'] = round(total_size_mb, 2)
            return len(media_files) > 0
    
    def _build_result(self, valid: bool) -> Dict:
        """Construye el resultado de validación."""
        return {
            'valid': valid,
            'errors': self.errors,
            'warnings': self.warnings,
            'metadata': self.metadata
        }
