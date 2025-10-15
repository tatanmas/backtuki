"""
Módulo de conexión SSH robusto
Maneja conexiones SSH con reconexión automática y túneles MySQL
"""

import paramiko
import logging
import time
import socket
from typing import Optional, Tuple
from contextlib import contextmanager
import threading
from .django_config import get_sync_config

logger = logging.getLogger(__name__)

class SSHConnectionError(Exception):
    """Excepción personalizada para errores de conexión SSH"""
    pass

class SSHTunnel:
    """
    Maneja conexiones SSH y túneles para MySQL
    Implementa reconexión automática y manejo robusto de errores
    """
    
    def __init__(self, ssh_config=None):
        self.ssh_client: Optional[paramiko.SSHClient] = None
        self.tunnel_thread: Optional[threading.Thread] = None
        self.is_connected = False
        
        # Obtener configuración de Django si no se proporciona
        if ssh_config is None:
            sync_config = get_sync_config()
            self.ssh_config = sync_config.ssh
            self.mysql_config = sync_config.mysql
        else:
            self.ssh_config = ssh_config
            # Para compatibilidad, usar puerto por defecto si no se proporciona mysql_config
            from .django_config import MySQLConfig
            self.mysql_config = MySQLConfig(port=3307)
        self.tunnel_active = False
        self._lock = threading.Lock()
    
    def connect(self) -> bool:
        """
        Establece conexión SSH con reintentos automáticos
        
        Returns:
            bool: True si la conexión fue exitosa
        """
        with self._lock:
            for attempt in range(self.ssh_config.max_retries):
                try:
                    logger.info(f"Intento de conexión SSH #{attempt + 1}")
                    
                    # Crear cliente SSH
                    self.ssh_client = paramiko.SSHClient()
                    self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    # Intentar conexión con clave privada primero, luego con contraseña
                    connected = False
                    
                    # Método 1: Intentar con clave privada si está disponible
                    try:
                        private_key_str = self.ssh_config.private_key_content
                        if private_key_str and private_key_str.strip():
                            logger.info("Intentando conexión con clave privada...")
                            
                            # Intentar diferentes tipos de clave
                            private_key = None
                            passphrase = self.ssh_config.private_key_passphrase
                            
                            for key_class in [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey]:
                                try:
                                    from io import StringIO
                                    if passphrase:
                                        private_key = key_class.from_private_key(StringIO(private_key_str), password=passphrase)
                                    else:
                                        private_key = key_class.from_private_key(StringIO(private_key_str))
                                    logger.info(f"Clave privada cargada como {key_class.__name__}")
                                    break
                                except paramiko.ssh_exception.PasswordRequiredException:
                                    logger.debug(f"Clave {key_class.__name__} requiere passphrase")
                                    continue
                                except Exception as e:
                                    logger.debug(f"No se pudo cargar como {key_class.__name__}: {e}")
                                    continue
                            
                            if private_key:
                                # Conectar con clave privada
                                self.ssh_client.connect(
                                    hostname=self.ssh_config.host,
                                    port=self.ssh_config.port,
                                    username=self.ssh_config.username,
                                    pkey=private_key,
                                    timeout=self.ssh_config.timeout,
                                    look_for_keys=False,
                                    allow_agent=False
                                )
                                connected = True
                                logger.info("Conexión exitosa con clave privada")
                    except Exception as e:
                        logger.warning(f"Falló conexión con clave privada: {e}")
                    
                    # Método 2: Intentar con contraseña si la clave privada falló
                    if not connected and self.ssh_config.password:
                        logger.info("Intentando conexión con contraseña...")
                        try:
                            self.ssh_client.connect(
                                hostname=self.ssh_config.host,
                                port=self.ssh_config.port,
                                username=self.ssh_config.username,
                                password=self.ssh_config.password,
                                timeout=self.ssh_config.timeout,
                                look_for_keys=False,
                                allow_agent=False
                            )
                            connected = True
                            logger.info("Conexión exitosa con contraseña")
                        except Exception as e:
                            logger.error(f"Falló conexión con contraseña: {e}")
                    
                    # Método 3: Intentar sin autenticación (para algunos servidores)
                    if not connected:
                        logger.info("Intentando conexión sin autenticación...")
                        try:
                            self.ssh_client.connect(
                                hostname=self.ssh_config.host,
                                port=self.ssh_config.port,
                                username=self.ssh_config.username,
                                timeout=self.ssh_config.timeout,
                                look_for_keys=True,
                                allow_agent=True
                            )
                            connected = True
                            logger.info("Conexión exitosa sin autenticación explícita")
                        except Exception as e:
                            logger.error(f"Falló conexión sin autenticación: {e}")
                    
                    if not connected:
                        raise SSHConnectionError("No se pudo establecer conexión SSH con ningún método de autenticación")
                    
                    self.is_connected = True
                    logger.info("Conexión SSH establecida exitosamente")
                    return True
                    
                except Exception as e:
                    logger.error(f"Error en intento #{attempt + 1}: {e}")
                    if self.ssh_client:
                        try:
                            self.ssh_client.close()
                        except:
                            pass
                        self.ssh_client = None
                    
                    if attempt < self.ssh_config.max_retries - 1:
                        logger.info(f"Reintentando en {self.ssh_config.retry_delay} segundos...")
                        time.sleep(self.ssh_config.retry_delay)
            
            logger.error("No se pudo establecer conexión SSH después de todos los intentos")
            return False
    
    def create_tunnel(self) -> bool:
        """
        Crea túnel SSH para MySQL
        
        Returns:
            bool: True si el túnel fue creado exitosamente
        """
        if not self.is_connected or not self.ssh_client:
            logger.error("No hay conexión SSH activa para crear túnel")
            return False
        
        try:
            # Verificar que el puerto local esté disponible
            if self._is_port_in_use(self.mysql_config.port):
                logger.warning(f"Puerto {self.mysql_config.port} ya está en uso")
                return True  # Asumir que el túnel ya existe
            
            # Intentar crear túnel con diferentes métodos
            transport = self.ssh_client.get_transport()
            
            # Método 1: Túnel directo a localhost:3306
            try:
                logger.info("Intentando túnel directo a localhost:3306...")
                local_port = transport.request_port_forward('', self.mysql_config.port, 'localhost', 3306)
                if local_port:
                    self.tunnel_active = True
                    logger.info(f"Túnel SSH creado: localhost:{self.mysql_config.port} -> localhost:3306")
                    return True
            except Exception as e:
                logger.warning(f"Falló túnel directo: {e}")
            
            # Método 2: Túnel a 127.0.0.1:3306
            try:
                logger.info("Intentando túnel a 127.0.0.1:3306...")
                local_port = transport.request_port_forward('', self.mysql_config.port, '127.0.0.1', 3306)
                if local_port:
                    self.tunnel_active = True
                    logger.info(f"Túnel SSH creado: localhost:{self.mysql_config.port} -> 127.0.0.1:3306")
                    return True
            except Exception as e:
                logger.warning(f"Falló túnel a 127.0.0.1: {e}")
            
            # Método 3: Intentar con puerto alternativo
            try:
                logger.info("Intentando túnel con puerto alternativo 3307...")
                local_port = transport.request_port_forward('', 3308, 'localhost', 3306)
                if local_port:
                    # Actualizar configuración para usar el puerto alternativo
                    self.mysql_config.port = 3308
                    self.tunnel_active = True
                    logger.info(f"Túnel SSH creado: localhost:3308 -> localhost:3306")
                    return True
            except Exception as e:
                logger.warning(f"Falló túnel alternativo: {e}")
            
            logger.error("No se pudo crear túnel SSH con ningún método")
            return False
            
        except Exception as e:
            logger.error(f"Error general creando túnel SSH: {e}")
            return False
    
    def _is_port_in_use(self, port: int) -> bool:
        """Verifica si un puerto está en uso"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return False
            except socket.error:
                return True
    
    def is_connection_alive(self) -> bool:
        """
        Verifica si la conexión SSH está realmente activa
        
        Returns:
            bool: True si la conexión está activa y funcional
        """
        if not self.is_connected or not self.ssh_client:
            return False
        
        try:
            # Verificar que el transport esté activo
            transport = self.ssh_client.get_transport()
            if not transport or not transport.is_active():
                return False
            
            # Ejecutar comando simple para verificar conectividad
            stdin, stdout, stderr = self.ssh_client.exec_command("echo 'alive'", timeout=5)
            result = stdout.read().decode('utf-8').strip()
            exit_code = stdout.channel.recv_exit_status()
            
            return exit_code == 0 and result == 'alive'
            
        except Exception as e:
            logger.debug(f"Verificación de conexión falló: {e}")
            return False
    
    def execute_command(self, command: str) -> Tuple[str, str, int]:
        """
        Ejecuta un comando en el servidor remoto
        
        Args:
            command: Comando a ejecutar
            
        Returns:
            Tuple[stdout, stderr, exit_code]
        """
        if not self.is_connected or not self.ssh_client:
            raise SSHConnectionError("No hay conexión SSH activa")
        
        # Verificar que la conexión esté realmente activa
        if not self.is_connection_alive():
            logger.warning("Conexión SSH no está activa, marcando como desconectada")
            self.is_connected = False
            raise SSHConnectionError("Conexión SSH perdida")
        
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command, timeout=30)
            
            stdout_data = stdout.read().decode('utf-8')
            stderr_data = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()
            
            return stdout_data, stderr_data, exit_code
            
        except Exception as e:
            logger.error(f"Error ejecutando comando '{command}': {e}")
            # Marcar conexión como inactiva si hay error
            self.is_connected = False
            raise SSHConnectionError(f"Error ejecutando comando: {e}")
    
    def test_mysql_connection(self) -> bool:
        """
        Prueba la conectividad MySQL a través del túnel
        
        Returns:
            bool: True si MySQL es accesible
        """
        try:
            # Intentar conectar al puerto MySQL local
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                result = s.connect_ex(('localhost', self.mysql_config.port))
                return result == 0
                
        except Exception as e:
            logger.error(f"Error probando conexión MySQL: {e}")
            return False
    
    def disconnect(self):
        """Cierra la conexión SSH y limpia recursos"""
        with self._lock:
            if self.ssh_client:
                try:
                    self.ssh_client.close()
                    logger.info("Conexión SSH cerrada")
                except Exception as e:
                    logger.error(f"Error cerrando conexión SSH: {e}")
                finally:
                    self.ssh_client = None
                    self.is_connected = False
                    self.tunnel_active = False
    
    def __enter__(self):
        """Context manager entry"""
        if not self.connect():
            raise SSHConnectionError("No se pudo establecer conexión SSH")
        
        if not self.create_tunnel():
            raise SSHConnectionError("No se pudo crear túnel MySQL")
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()

@contextmanager
def ssh_tunnel():
    """
    Context manager para manejo automático de túnel SSH
    
    Usage:
        with ssh_tunnel() as tunnel:
            # Usar conexión MySQL aquí
            pass
    """
    tunnel = SSHTunnel()
    try:
        yield tunnel.__enter__()
    finally:
        tunnel.__exit__(None, None, None)
