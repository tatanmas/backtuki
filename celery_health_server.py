#!/usr/bin/env python3
"""
🚀 ENTERPRISE CELERY WORKER HEALTH SERVER
HTTP health check server for Celery worker in Google Cloud Run
"""

import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import subprocess
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health' or self.path == '/':
            try:
                # Simple health check - verify Celery app can be imported
                from config.celery import app as celery_app
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "healthy", "service": "celery-worker"}')
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(f'{{"status": "unhealthy", "error": "{str(e)}"}}'.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default HTTP server logs
        pass

def start_health_server():
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    logger.info(f"Health server starting on port {port}")
    server.serve_forever()

if __name__ == '__main__':
    # Start health server in background thread
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Start Celery worker
    logger.info("=" * 80)
    logger.info("🚀 CELERY WORKER INICIANDO 🚀")
    logger.info("=" * 80)
    
    # Log environment info
    import os
    logger.info(f"📋 CONFIGURACIÓN:")
    logger.info(f"   - Django Settings: {os.environ.get('DJANGO_SETTINGS_MODULE', 'N/A')}")
    logger.info(f"   - Redis URL: {os.environ.get('REDIS_URL', 'N/A')}")
    logger.info(f"   - Workers: 4 (concurrency=4)")
    logger.info(f"   - Memoria: 8Gi total (~2Gi por worker)")
    logger.info(f"   - Colas: sync-heavy,default,emails,critical,maintenance,documents")
    logger.info(f"   - Prefetch: 1 (una tarea por worker)")
    logger.info(f"   - Rate limit sync: 1/minuto (solo 1 sync pesada a la vez)")
    logger.info("=" * 80)
    
    # Use subprocess to start Celery worker
    # 🚀 ENTERPRISE: Cola dedicada para syncs pesadas con concurrencia limitada
    # Todas las colas escuchadas, control de concurrency se hace con rate_limit en la tarea
    celery_cmd = [
        'celery', '-A', 'config', 'worker', 
        '-l', 'info', 
        '-Q', 'sync-heavy,default,emails,critical,maintenance,documents',
        '--concurrency=4',                  # 4 workers totales
        '--prefetch-multiplier=1',          # Solo 1 tarea por worker a la vez
        '--max-tasks-per-child=500',        # Recicla workers cada 500 tareas
        '--max-memory-per-child=2000000',   # 2GB límite por worker
    ]
    
    logger.info(f"🎯 Comando Celery: {' '.join(celery_cmd)}")
    logger.info("⏳ Esperando tareas...")
    logger.info("=" * 80)
    
    try:
        # Usar Popen para que los logs de Celery fluyan a stdout
        process = subprocess.Popen(
            celery_cmd,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        process.wait()
    except KeyboardInterrupt:
        logger.info("Celery worker stopped")
        process.terminate()
        process.wait()
        sys.exit(0)
