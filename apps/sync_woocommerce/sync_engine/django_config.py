"""
Configuración Django para el sincronizador WooCommerce

Este archivo adapta la configuración existente para trabajar con Django
usando las mismas credenciales que ya funcionaron en las pruebas.
"""

import os
from dataclasses import dataclass
from typing import Optional
from django.conf import settings


@dataclass
class SSHConfig:
    """Configuración SSH para conexión al servidor"""
    host: str
    port: int = 22
    username: str = ""
    password: Optional[str] = None
    private_key_content: Optional[str] = None
    private_key_passphrase: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 5


@dataclass
class MySQLConfig:
    """Configuración MySQL para la base de datos WordPress"""
    host: str = "localhost"
    port: int = 3306
    database: str = ""
    username: str = ""
    password: str = ""
    charset: str = "utf8mb4"


@dataclass
class DjangoSyncConfig:
    """Configuración del sincronizador para Django"""
    ssh: SSHConfig
    mysql: MySQLConfig
    
    # Configuraciones adicionales
    debug: bool = False
    max_retries: int = 3
    retry_delay: int = 5
    
    @classmethod
    def from_django_settings(cls) -> 'DjangoSyncConfig':
        """
        Crear configuración desde Django settings y variables de entorno
        """
        
        # Configuración SSH
        ssh_config = SSHConfig(
            host=os.getenv('WOOCOMMERCE_SSH_HOST', 'ssh.tuki.cl'),
            port=int(os.getenv('WOOCOMMERCE_SSH_PORT', '18765')),
            username=os.getenv('WOOCOMMERCE_SSH_USERNAME', 'u2623-ptnhn7j8zwzr'),
            password=os.getenv('WOOCOMMERCE_SSH_PASSWORD', ''),
            private_key_content=cls._load_private_key_from_file(),
            private_key_passphrase=os.getenv('WOOCOMMERCE_SSH_PRIVATE_KEY_PASSPHRASE', ''),
            timeout=int(os.getenv('WOOCOMMERCE_SSH_TIMEOUT', '30')),
            max_retries=int(os.getenv('WOOCOMMERCE_SSH_MAX_RETRIES', '3')),
            retry_delay=int(os.getenv('WOOCOMMERCE_SSH_RETRY_DELAY', '5'))
        )
        
        # Configuración MySQL
        mysql_config = MySQLConfig(
            host=os.getenv('WOOCOMMERCE_MYSQL_HOST', '127.0.0.1'),
            port=int(os.getenv('WOOCOMMERCE_MYSQL_PORT', '3307')),
            database=os.getenv('WOOCOMMERCE_MYSQL_DATABASE', 'dbuogb7tu1drph'),
            username=os.getenv('WOOCOMMERCE_MYSQL_USERNAME', 'uzrc1b3rpwtoa'),
            password=os.getenv('WOOCOMMERCE_MYSQL_PASSWORD', ''),
            charset=os.getenv('WOOCOMMERCE_MYSQL_CHARSET', 'utf8mb4')
        )
        
        return cls(
            ssh=ssh_config,
            mysql=mysql_config,
            debug=getattr(settings, 'DEBUG', False),
            max_retries=int(os.getenv('WOOCOMMERCE_SYNC_MAX_RETRIES', '3')),
            retry_delay=int(os.getenv('WOOCOMMERCE_SYNC_RETRY_DELAY', '5'))
        )
    
    def validate(self) -> bool:
        """Valida la configuración"""
        try:
            # Validar configuración SSH
            if not self.ssh.host:
                raise ValueError("SSH host no configurado")
            
            if not self.ssh.username:
                raise ValueError("SSH username no configurado")
            
            if not self.ssh.password and not self.ssh.private_key_content:
                raise ValueError("SSH password o private key requerido")
            
            # Validar configuración MySQL
            if not all([self.mysql.database, self.mysql.username, self.mysql.password]):
                raise ValueError("Credenciales MySQL incompletas")
            
            return True
            
        except Exception as e:
            print(f"Error de validación de configuración: {e}")
            return False
    
    @classmethod
    def _load_private_key_from_file(cls) -> Optional[str]:
        """
        Carga la clave SSH privada desde archivo
        """
        key_path = os.getenv('WOOCOMMERCE_SSH_PRIVATE_KEY_PATH', '/app/WOOCOMMERCE_SSH_KEY.txt')
        
        try:
            if os.path.exists(key_path):
                with open(key_path, 'r') as f:
                    return f.read().strip()
        except Exception as e:
            print(f"Error cargando clave SSH desde {key_path}: {e}")
        
        # Fallback a variable de entorno si existe
        return os.getenv('WOOCOMMERCE_SSH_PRIVATE_KEY', '')


def get_sync_config() -> DjangoSyncConfig:
    """
    Obtiene la configuración de sincronización para Django
    """
    return DjangoSyncConfig.from_django_settings()
