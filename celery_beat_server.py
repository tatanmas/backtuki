#!/usr/bin/env python3
"""
🚀 ENTERPRISE CELERY BEAT HEALTH SERVER
HTTP health check server for Celery beat in Google Cloud Run
"""

import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import subprocess
import signal
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variable to track Celery beat process
celery_process = None

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health' or self.path == '/':
            try:
                # Check if Celery beat process is running
                global celery_process
                if celery_process and celery_process.poll() is None:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"status": "healthy", "service": "celery-beat"}')
                else:
                    raise Exception("Celery beat process not running")
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

def signal_handler(sig, frame):
    global celery_process
    logger.info("Received shutdown signal, terminating Celery beat...")
    if celery_process:
        celery_process.terminate()
        celery_process.wait()
    sys.exit(0)

if __name__ == '__main__':
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start health server in background thread
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Start Celery beat
    logger.info("Starting Celery beat scheduler...")
    celery_process = subprocess.Popen([
        'celery', '-A', 'config', 'beat', '-l', 'info', '--pidfile='
    ])
    
    # Wait for Celery beat process
    try:
        celery_process.wait()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
