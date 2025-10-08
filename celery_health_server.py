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
    logger.info("Starting Celery worker...")
    
    # Use subprocess to start Celery worker
    celery_cmd = [
        'celery', '-A', 'config', 'worker', 
        '-l', 'info', 
        '-Q', 'default,emails,critical,maintenance,documents',
        '--concurrency=4'
    ]
    
    try:
        subprocess.run(celery_cmd)
    except KeyboardInterrupt:
        logger.info("Celery worker stopped")
        sys.exit(0)
