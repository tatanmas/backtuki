"""
Configuración del sincronizador
Maneja credenciales y configuraciones de conexión de forma segura
"""

import os
from dataclasses import dataclass
from typing import Optional
import logging
import logging.handlers

@dataclass
class SSHConfig:
    """Configuración SSH para conexión al servidor"""
    host: str = "ssh.tuki.cl"
    port: int = 18765
    username: str = "u2623-ptnhn7j8zwzr"
    private_key_path: Optional[str] = None
    private_key_content: Optional[str] = None
    private_key_passphrase: Optional[str] = None  # Para claves encriptadas
    password: Optional[str] = None  # Contraseña SSH alternativa
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 5

@dataclass
class MySQLConfig:
    """Configuración MySQL para la base de datos WordPress"""
    host: str = "127.0.0.1"  # Localhost a través del túnel SSH
    port: int = 3307  # Puerto local del túnel
    database: str = "dbuogb7tu1drph"
    username: str = "uzrc1b3rpwtoa"
    password: str = "*3h(2f1)%1@^"
    charset: str = "utf8mb4"
    autocommit: bool = True
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600

@dataclass
class SyncConfig:
    """Configuración general del sincronizador"""
    log_level: str = "INFO"
    log_file: str = "sync.log"
    max_log_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    batch_size: int = 100
    connection_timeout: int = 60
    query_timeout: int = 300  # 5 minutos
    
    # Configuraciones específicas de WooCommerce
    order_statuses: list = None
    
    def __post_init__(self):
        if self.order_statuses is None:
            self.order_statuses = [
                'wc-completed', 
                'wc-processing', 
                'wc-on-hold', 
                'wc-pending'
            ]

class Config:
    """Configuración principal del sincronizador"""
    
    def __init__(self):
        self.ssh = SSHConfig()
        self.mysql = MySQLConfig()
        self.sync = SyncConfig()
        self._load_local_credentials()
        self._setup_logging()
    
    def _load_local_credentials(self):
        """Carga credenciales locales si están disponibles"""
        try:
            from .ssh_config_local import SSH_PASSWORD, SSH_PRIVATE_KEY_PASSPHRASE
            if SSH_PASSWORD:
                self.ssh.password = SSH_PASSWORD
            if SSH_PRIVATE_KEY_PASSPHRASE:
                self.ssh.private_key_passphrase = SSH_PRIVATE_KEY_PASSPHRASE
            logging.getLogger(__name__).info("Credenciales SSH locales cargadas")
        except ImportError:
            logging.getLogger(__name__).debug("No se encontraron credenciales SSH locales")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Error cargando credenciales locales: {e}")
    
    def _setup_logging(self):
        """Configura el sistema de logging"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # Configurar logging básico
        logging.basicConfig(
            level=getattr(logging, self.sync.log_level),
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.handlers.RotatingFileHandler(
                    self.sync.log_file,
                    maxBytes=self.sync.max_log_size,
                    backupCount=self.sync.backup_count
                )
            ]
        )
    
    def get_ssh_private_key(self) -> str:
        """
        Obtiene la clave privada SSH
        Prioriza archivo sobre contenido directo por seguridad
        """
        if self.ssh.private_key_path and os.path.exists(self.ssh.private_key_path):
            with open(self.ssh.private_key_path, 'r') as f:
                return f.read()
        
        # Fallback a clave hardcodeada (solo para desarrollo)
        return """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAACmFlczI1Ni1jdHIAAAAGYmNyeXB0AAAAGAAAABA/pd9e6g
ydaQPXUhp/T/7EAAAAGAAAAAEAAAAzAAAAC3NzaC1lZDI1NTE5AAAAICVljvnE9t5x086q
GcmnXdP1fGYAxfmB0rhyeqUQRRAzAAAAkATmZsqgXTj5mP/njjdaQgEj5KMqc6o7M9Ld/w
GRq2zNVWr15dG8PY6+vtvR+XlY7nRi+pan7P7ln03h6CfY11MdiYPTdBGbMDXbxoSQV9Jm
Nd81u7VXdyDUODHC2a7xOG0uZXYpVqsRIBpHCC0k+U+annkE2hq5/x4OQjhPF6pZi6rQE8
vr4Of13MZ+ndg00g==
-----END OPENSSH PRIVATE KEY-----"""
    
    def validate(self) -> bool:
        """Valida la configuración"""
        try:
            # Validar configuración SSH
            if not self.ssh.host:
                raise ValueError("SSH host no configurado")
            
            # Validar configuración MySQL
            if not all([self.mysql.database, self.mysql.username, self.mysql.password]):
                raise ValueError("Credenciales MySQL incompletas")
            
            # Validar clave SSH
            private_key = self.get_ssh_private_key()
            if not private_key or len(private_key.strip()) == 0:
                raise ValueError("Clave privada SSH no disponible")
            
            return True
            
        except Exception as e:
            logging.error(f"Error de validación de configuración: {e}")
            return False

# Instancia global de configuración
config = Config()
