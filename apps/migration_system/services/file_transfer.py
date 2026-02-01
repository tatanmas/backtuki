"""
🚀 ENTERPRISE FILE TRANSFER SERVICE

Servicio para transferir archivos entre GCS, filesystem local y backends.
"""

import hashlib
import logging
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

# Import condicional de google-cloud-storage
try:
    from google.cloud import storage as gcs_storage
    HAS_GCS = True
except ImportError:
    HAS_GCS = False
    logger.warning("google-cloud-storage no disponible. GCS transfers no funcionarán.")


class FileTransferService:
    """
    Servicio enterprise para transferir archivos entre diferentes backends.
    
    Soporta:
    - GCS → Filesystem local
    - Filesystem local → GCS
    - Backend → Backend (vía HTTP)
    """
    
    def __init__(self, job=None):
        """
        Initialize file transfer service.
        
        Args:
            job: MigrationJob instance (opcional, para tracking)
        """
        self.job = job
        self.max_workers = getattr(settings, 'MIGRATION_SYSTEM', {}).get('PARALLEL_TRANSFERS', 5)
        self.chunk_size_mb = getattr(settings, 'MIGRATION_SYSTEM', {}).get('FILE_CHUNK_SIZE_MB', 10)
        self.chunk_size_bytes = self.chunk_size_mb * 1024 * 1024
    
    def transfer_from_gcs_to_local(self, bucket_name, local_path, file_list=None):
        """
        Transfiere archivos desde Google Cloud Storage a filesystem local.
        
        Args:
            bucket_name: nombre del bucket GCS
            local_path: ruta local destino
            file_list: lista de archivos a transferir (None = todos)
            
        Returns:
            dict con resultado
        """
        if not HAS_GCS:
            raise ImportError("google-cloud-storage no está instalado")
        
        logger.info(f"Transfiriendo desde gs://{bucket_name} a {local_path}")
        
        # Inicializar cliente GCS
        client = gcs_storage.Client()
        bucket = client.bucket(bucket_name)
        
        # Obtener lista de archivos si no se especificó
        if file_list is None:
            file_list = [blob.name for blob in bucket.list_blobs()]
        
        total_files = len(file_list)
        transferred = 0
        errors = []
        
        # Crear directorio local
        Path(local_path).mkdir(parents=True, exist_ok=True)
        
        # Transferir en paralelo
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self._download_from_gcs,
                    bucket,
                    file_name,
                    Path(local_path) / file_name
                ): file_name
                for file_name in file_list
            }
            
            for future in as_completed(futures):
                file_name = futures[future]
                try:
                    result = future.result()
                    if result['success']:
                        transferred += 1
                        
                        if self.job:
                            self.job.files_transferred = transferred
                            progress = 80 + int((transferred / total_files) * 20)  # 80-100%
                            self.job.update_progress(progress, f"Archivos: {transferred}/{total_files}")
                    else:
                        errors.append(result['error'])
                except Exception as e:
                    errors.append(f"{file_name}: {str(e)}")
                    logger.error(f"Error transfiriendo {file_name}: {e}")
        
        logger.info(f"Transferidos {transferred}/{total_files} archivos")
        
        return {
            'success': len(errors) == 0,
            'transferred': transferred,
            'total': total_files,
            'errors': errors
        }
    
    def _download_from_gcs(self, bucket, blob_name, destination_path):
        """
        Descarga un archivo individual de GCS.
        
        Args:
            bucket: GCS bucket object
            blob_name: nombre del blob
            destination_path: ruta destino
            
        Returns:
            dict con resultado
        """
        try:
            blob = bucket.blob(blob_name)
            
            # Crear directorio si no existe
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Descargar
            blob.download_to_filename(str(destination_path))
            
            return {
                'success': True,
                'file': blob_name,
                'size': blob.size
            }
        except Exception as e:
            return {
                'success': False,
                'file': blob_name,
                'error': str(e)
            }
    
    def transfer_from_local_to_gcs(self, local_path, bucket_name, file_list=None):
        """
        Transfiere archivos desde filesystem local a Google Cloud Storage.
        
        Args:
            local_path: ruta local origen
            bucket_name: nombre del bucket GCS destino
            file_list: lista de archivos a transferir (None = todos)
            
        Returns:
            dict con resultado
        """
        if not HAS_GCS:
            raise ImportError("google-cloud-storage no está instalado")
        
        logger.info(f"Transfiriendo desde {local_path} a gs://{bucket_name}")
        
        # Inicializar cliente GCS
        client = gcs_storage.Client()
        bucket = client.bucket(bucket_name)
        
        local_path = Path(local_path)
        
        # Obtener lista de archivos si no se especificó
        if file_list is None:
            file_list = [
                str(p.relative_to(local_path))
                for p in local_path.rglob('*')
                if p.is_file()
            ]
        
        total_files = len(file_list)
        transferred = 0
        errors = []
        
        # Transferir en paralelo
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self._upload_to_gcs,
                    bucket,
                    local_path / file_name,
                    file_name
                ): file_name
                for file_name in file_list
            }
            
            for future in as_completed(futures):
                file_name = futures[future]
                try:
                    result = future.result()
                    if result['success']:
                        transferred += 1
                        
                        if self.job:
                            self.job.files_transferred = transferred
                            progress = 80 + int((transferred / total_files) * 20)
                            self.job.update_progress(progress, f"Archivos: {transferred}/{total_files}")
                    else:
                        errors.append(result['error'])
                except Exception as e:
                    errors.append(f"{file_name}: {str(e)}")
                    logger.error(f"Error transfiriendo {file_name}: {e}")
        
        logger.info(f"Transferidos {transferred}/{total_files} archivos")
        
        return {
            'success': len(errors) == 0,
            'transferred': transferred,
            'total': total_files,
            'errors': errors
        }
    
    def _upload_to_gcs(self, bucket, local_file_path, blob_name):
        """
        Sube un archivo individual a GCS.
        
        Args:
            bucket: GCS bucket object
            local_file_path: Path al archivo local
            blob_name: nombre del blob en GCS
            
        Returns:
            dict con resultado
        """
        try:
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(str(local_file_path))
            
            return {
                'success': True,
                'file': blob_name,
                'size': local_file_path.stat().st_size
            }
        except Exception as e:
            return {
                'success': False,
                'file': blob_name,
                'error': str(e)
            }
    
    def transfer_file_to_backend(self, file_path, target_url, auth_token):
        """
        Transfiere un archivo a otro backend vía HTTP.
        
        Args:
            file_path: ruta del archivo local
            target_url: URL del backend destino
            auth_token: token de autenticación
            
        Returns:
            dict con resultado
        """
        try:
            # Leer archivo
            with open(file_path, 'rb') as f:
                files = {'file': f}
                data = {
                    'path': Path(file_path).name,
                    'checksum': self.calculate_file_checksum_from_path(file_path)
                }
                headers = {
                    'Authorization': f'MigrationToken {auth_token}'
                }
                
                # POST a endpoint de recepción
                response = requests.post(
                    f"{target_url}/api/v1/migration/receive-file/",
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=300
                )
                
                if response.status_code == 200:
                    return {
                        'success': True,
                        'file': file_path,
                        'response': response.json()
                    }
                else:
                    return {
                        'success': False,
                        'file': file_path,
                        'error': f"HTTP {response.status_code}: {response.text}"
                    }
                    
        except Exception as e:
            return {
                'success': False,
                'file': file_path,
                'error': str(e)
            }
    
    def calculate_file_checksum_from_path(self, file_path, algorithm='md5'):
        """
        Calcula checksum de un archivo por su path.
        
        Args:
            file_path: ruta del archivo
            algorithm: 'md5' o 'sha256'
            
        Returns:
            str: checksum en hexadecimal
        """
        if algorithm == 'md5':
            hasher = hashlib.md5()
        elif algorithm == 'sha256':
            hasher = hashlib.sha256()
        else:
            raise ValueError(f"Algoritmo no soportado: {algorithm}")
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    
    def download_file_from_url(self, url, destination, auth_token=None, max_retries=3):
        """
        Descarga un archivo desde una URL con retry.
        
        Args:
            url: URL del archivo
            destination: ruta destino
            auth_token: token de autenticación (opcional)
            max_retries: número máximo de reintentos
            
        Returns:
            dict con resultado
        """
        headers = {}
        if auth_token:
            headers['Authorization'] = f'MigrationToken {auth_token}'
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, stream=True, timeout=300)
                
                if response.status_code == 200:
                    # Crear directorio si no existe
                    Path(destination).parent.mkdir(parents=True, exist_ok=True)
                    
                    # Descargar en chunks
                    with open(destination, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=self.chunk_size_bytes):
                            if chunk:
                                f.write(chunk)
                    
                    return {
                        'success': True,
                        'file': destination,
                        'size': Path(destination).stat().st_size
                    }
                else:
                    logger.warning(f"Intento {attempt + 1}/{max_retries} falló: HTTP {response.status_code}")
                    
            except Exception as e:
                logger.warning(f"Intento {attempt + 1}/{max_retries} falló: {e}")
                if attempt == max_retries - 1:
                    return {
                        'success': False,
                        'file': destination,
                        'error': str(e)
                    }
        
        return {
            'success': False,
            'file': destination,
            'error': f"Failed after {max_retries} attempts"
        }
