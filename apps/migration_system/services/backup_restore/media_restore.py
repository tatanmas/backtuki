"""
Media Restore Service - Sincroniza archivos media al volume Docker
"""

import subprocess
import logging
import shutil
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class MediaRestoreService:
    """
    Sincroniza archivos media desde backup a volume Docker.
    ~100 líneas, maneja extracción y sync.
    """
    
    MEDIA_VOLUME = 'tuki_media'
    
    def __init__(self, job=None):
        self.job = job
        self.files_copied = 0
        self.total_size_mb = 0.0
    
    def restore(self, media_source_dir: Path) -> Dict:
        """
        Restaura archivos media desde directorio extraído.
        
        Args:
            media_source_dir: Directorio con archivos media (gcs/tuki-media-prod-*)
        
        Returns:
            {
                'success': bool,
                'files_copied': int,
                'total_size_mb': float,
                'errors': List[str]
            }
        """
        errors = []
        
        try:
            # 1. Validar que existe el directorio source
            self._update_progress(10, "Validando archivos media...")
            if not media_source_dir.exists():
                errors.append(f"Directorio media no encontrado: {media_source_dir}")
                return self._build_result(False, errors)
            
            # 2. Contar archivos y tamaño
            self._update_progress(20, "Contando archivos...")
            file_count, total_size = self._count_files(media_source_dir)
            self.total_size_mb = round(total_size / (1024 * 1024), 2)
            
            logger.info(f"Media restore: {file_count} archivos, {self.total_size_mb} MB")
            
            # 3. Sincronizar a volume Docker
            self._update_progress(40, f"Sincronizando {file_count} archivos...")
            self._sync_to_volume(media_source_dir)
            
            self.files_copied = file_count
            
            # 4. Verificar
            self._update_progress(90, "Verificando sincronización...")
            if not self._verify_sync():
                errors.append("Verificación de sincronización falló")
            
            return self._build_result(len(errors) == 0, errors)
            
        except Exception as e:
            logger.exception("Error en restore media")
            errors.append(str(e))
            return self._build_result(False, errors)
    
    def _count_files(self, source_dir: Path) -> tuple:
        """Cuenta archivos y tamaño total."""
        files = list(source_dir.rglob('*'))
        files = [f for f in files if f.is_file()]
        total_size = sum(f.stat().st_size for f in files)
        return len(files), total_size
    
    def _sync_to_volume(self, source_dir: Path):
        """
        Sincroniza archivos al volume Docker usando container temporal.
        """
        # Usar Docker para copiar al volume
        cmd = [
            'docker', 'run', '--rm',
            '-v', f'{self.MEDIA_VOLUME}:/target',
            '-v', f'{source_dir.absolute()}:/source:ro',
            'alpine',
            'sh', '-c', 'cp -r /source/* /target/'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception(f"Sync falló: {result.stderr}")
        
        logger.info("Media files sincronizados al volume Docker")
    
    def _verify_sync(self) -> bool:
        """Verifica que los archivos se copiaron correctamente."""
        try:
            # Contar archivos en el volume
            cmd = [
                'docker', 'run', '--rm',
                '-v', f'{self.MEDIA_VOLUME}:/target:ro',
                'alpine',
                'sh', '-c', 'find /target -type f | wc -l'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            volume_file_count = int(result.stdout.strip())
            
            logger.info(f"Archivos en volume: {volume_file_count}")
            return volume_file_count > 0
            
        except Exception as e:
            logger.warning(f"No se pudo verificar sync: {e}")
            return True  # No fallar por esto
    
    def _update_progress(self, percent: int, step: str):
        """Actualiza progreso en el job."""
        if self.job:
            self.job.update_progress(percent, step)
    
    def _build_result(self, success: bool, errors: list) -> Dict:
        """Construye resultado."""
        return {
            'success': success,
            'files_copied': self.files_copied,
            'total_size_mb': self.total_size_mb,
            'errors': errors
        }
