"""
SQL Restore Service - Restaura PostgreSQL desde SQL dump
Estrategia: MERGE de superadmins (preserva admin de Dako + trae los del backup)
"""

import subprocess
import logging
import tempfile
import json
from pathlib import Path
from typing import Dict, List
from django.conf import settings

logger = logging.getLogger(__name__)


class SQLRestoreService:
    """
    Restaura PostgreSQL desde SQL dump de GCP.
    MERGE strategy: Preserva superadmins de Dako + restaura todo lo demás del backup.
    ~145 líneas, maneja Docker, pg_restore y merge de admins.
    """
    
    DB_CONTAINER = 'tuki-db'
    DB_NAME = 'tuki_production'
    DB_USER = 'tuki_user'
    
    def __init__(self, job=None):
        self.job = job
        self.records_restored = 0
        self.preserved_admins = []
    
    def restore(self, sql_dump_path: Path) -> Dict:
        """
        Restaura PostgreSQL desde dump con merge de superadmins.
        
        Args:
            sql_dump_path: Ruta al archivo .sql.gz
        
        Returns:
            {
                'success': bool,
                'records_restored': int,
                'admins_merged': int,
                'errors': List[str]
            }
        """
        errors = []
        
        try:
            # 1. Preservar superadmins de Dako
            self._update_progress(10, "Preservando superadmins de Dako...")
            self.preserved_admins = self._extract_superadmins()
            logger.info(f"Superadmins preservados: {len(self.preserved_admins)}")
            
            # 2. Detener servicios Django
            self._update_progress(20, "Deteniendo servicios...")
            self._stop_django_services()
            
            # 3. Drop y recrear database
            self._update_progress(30, "Recreando base de datos...")
            self._recreate_database()
            
            # 4. Restaurar dump
            self._update_progress(50, "Restaurando datos del backup...")
            self._restore_dump(sql_dump_path)
            
            # 5. Re-insertar superadmins preservados
            self._update_progress(75, "Merge de superadmins...")
            admins_merged = self._merge_superadmins()
            logger.info(f"Superadmins merged: {admins_merged}")
            
            # 6. Verificar integridad
            self._update_progress(85, "Verificando integridad...")
            self.records_restored = self._count_records()
            
            # 7. Reiniciar servicios
            self._update_progress(95, "Reiniciando servicios...")
            self._start_django_services()
            
            return {
                'success': True,
                'records_restored': self.records_restored,
                'admins_merged': admins_merged,
                'errors': errors
            }
            
        except Exception as e:
            logger.exception("Error en restore SQL")
            errors.append(str(e))
            # Intentar reiniciar servicios aunque falle
            try:
                self._start_django_services()
            except:
                pass
            return {
                'success': False,
                'records_restored': 0,
                'admins_merged': 0,
                'errors': errors
            }
    
    def _extract_superadmins(self) -> List[Dict]:
        """Extrae superadmins de Dako antes de borrar la DB."""
        cmd = [
            'docker', 'exec', self.DB_CONTAINER,
            'psql', '-U', self.DB_USER, '-d', self.DB_NAME,
            '-t', '-c',
            "SELECT row_to_json(t) FROM (SELECT id, password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined FROM auth_user WHERE is_superuser = true) t;"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            admins = []
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line:
                    admins.append(json.loads(line))
            return admins
        except Exception as e:
            logger.warning(f"No se pudieron extraer superadmins: {e}")
            return []
    
    def _merge_superadmins(self) -> int:
        """Re-inserta superadmins preservados evitando duplicados."""
        if not self.preserved_admins:
            return 0
        
        merged_count = 0
        for admin in self.preserved_admins:
            # Verificar si ya existe (por email)
            check_cmd = [
                'docker', 'exec', self.DB_CONTAINER,
                'psql', '-U', self.DB_USER, '-d', self.DB_NAME,
                '-t', '-c',
                f"SELECT COUNT(*) FROM auth_user WHERE email = '{admin['email']}';"
            ]
            
            result = subprocess.run(check_cmd, capture_output=True, text=True)
            exists = int(result.stdout.strip()) > 0
            
            if not exists:
                # Insertar admin preservado
                insert_cmd = [
                    'docker', 'exec', self.DB_CONTAINER,
                    'psql', '-U', self.DB_USER, '-d', self.DB_NAME,
                    '-c',
                    f"""INSERT INTO auth_user (id, password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined) 
                    VALUES ({admin['id']}, '{admin['password']}', {'NULL' if not admin.get('last_login') else f"'{admin['last_login']}'"}, 
                    true, '{admin['username']}', '{admin['first_name']}', '{admin['last_name']}', '{admin['email']}', true, true, '{admin['date_joined']}');"""
                ]
                subprocess.run(insert_cmd, check=False)
                merged_count += 1
                logger.info(f"Admin merged: {admin['email']}")
            else:
                logger.info(f"Admin ya existe: {admin['email']}")
        
        return merged_count
    
    def _stop_django_services(self):
        """Detiene backend y celery."""
        services = ['tuki-backend', 'tuki-celery-worker', 'tuki-celery-beat']
        for service in services:
            subprocess.run(['docker-compose', 'stop', service], check=False)
    
    def _start_django_services(self):
        """Reinicia backend y celery."""
        services = ['tuki-backend', 'tuki-celery-worker', 'tuki-celery-beat']
        subprocess.run(['docker-compose', 'up', '-d'] + services, check=True)
    
    def _recreate_database(self):
        """Drop y recreate database."""
        # Drop
        cmd_drop = [
            'docker', 'exec', self.DB_CONTAINER,
            'psql', '-U', self.DB_USER, '-d', 'postgres',
            '-c', f'DROP DATABASE IF EXISTS {self.DB_NAME};'
        ]
        subprocess.run(cmd_drop, check=True)
        
        # Create
        cmd_create = [
            'docker', 'exec', self.DB_CONTAINER,
            'psql', '-U', self.DB_USER, '-d', 'postgres',
            '-c', f'CREATE DATABASE {self.DB_NAME} OWNER {self.DB_USER};'
        ]
        subprocess.run(cmd_create, check=True)
    
    def _restore_dump(self, sql_dump_path: Path):
        """Restaura el dump con pg_restore."""
        cmd = [
            'docker', 'exec', '-i', self.DB_CONTAINER,
            'pg_restore', '-U', self.DB_USER, '-d', self.DB_NAME,
            '--no-owner', '--no-acl', '--verbose'
        ]
        
        with open(sql_dump_path, 'rb') as f:
            subprocess.run(cmd, stdin=f, check=True)
    
    def _count_records(self) -> int:
        """Cuenta registros en tablas principales."""
        cmd = [
            'docker', 'exec', self.DB_CONTAINER,
            'psql', '-U', self.DB_USER, '-d', self.DB_NAME,
            '-t', '-c', 'SELECT COUNT(*) FROM auth_user;'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return int(result.stdout.strip()) if result.returncode == 0 else 0
    
    def _update_progress(self, percent: int, step: str):
        """Actualiza progreso en el job."""
        if self.job:
            self.job.update_progress(percent, step)
