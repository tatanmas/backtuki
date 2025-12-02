#!/usr/bin/env python3
"""
🚀 ENTERPRISE Unified Celery Health Server - Tuki Platform

Runs multiple Celery workers in a single Cloud Run service:
- EMAILS worker: Dedicated to instant email delivery
- CRITICAL worker: High-priority tasks
- GENERAL worker: Default tasks
- SYNC worker: Heavy sync operations

Benefits:
- Single deployment (vs 4 separate services)
- Simplified management
- Dedicated queues for isolation
- Health check endpoint for Cloud Run

Performance:
- EMAILS: 4 workers, <10s latency
- CRITICAL: 2 workers, high priority
- GENERAL: 2 workers, standard tasks
- SYNC: 1 worker, heavy operations

Usage:
    python celery_health_server_unified.py

Health Check:
    curl http://localhost:8080/health
"""

import os
import sys
import time
import signal
import subprocess
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global list to track worker processes
worker_processes = []


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks."""
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/health':
            # Check if all workers are running
            all_alive = all(p.poll() is None for p in worker_processes)
            
            if all_alive:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'healthy',
                    'workers': len(worker_processes),
                    'timestamp': time.time()
                }
                self.wfile.write(str(response).encode())
            else:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'unhealthy',
                    'workers_alive': sum(1 for p in worker_processes if p.poll() is None),
                    'workers_total': len(worker_processes),
                    'timestamp': time.time()
                }
                self.wfile.write(str(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def start_health_server(port=8080):
    """Start HTTP health check server."""
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"✅ Health check server started on port {port}")
    server.serve_forever()


def start_celery_worker(name, queues, concurrency, max_memory_mb=1500):
    """
    Start a Celery worker process.
    
    Args:
        name: Worker name (e.g., 'emails', 'critical')
        queues: Comma-separated queue names
        concurrency: Number of concurrent workers
        max_memory_mb: Max memory per child in MB
        
    Returns:
        subprocess.Popen object
    """
    cmd = [
        'celery', '-A', 'config', 'worker',
        '-l', 'info',
        '-Q', queues,
        f'--concurrency={concurrency}',
        '--prefetch-multiplier=1',
        f'--max-tasks-per-child=100',
        f'--max-memory-per-child={max_memory_mb * 1000}',  # Convert to KB
        '--pool=prefork',
        f'--hostname={name}@%h',
    ]
    
    logger.info(f"🚀 Starting {name.upper()} worker: {' '.join(cmd)}")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    # Log output in background thread
    def log_output():
        for line in process.stdout:
            logger.info(f"[{name.upper()}] {line.rstrip()}")
    
    Thread(target=log_output, daemon=True).start()
    
    return process


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"📡 Received signal {signum}, shutting down workers...")
    
    for process in worker_processes:
        if process.poll() is None:
            logger.info(f"Terminating worker PID {process.pid}")
            process.terminate()
    
    # Wait for graceful shutdown
    time.sleep(5)
    
    # Force kill if still running
    for process in worker_processes:
        if process.poll() is None:
            logger.warning(f"Force killing worker PID {process.pid}")
            process.kill()
    
    sys.exit(0)


def main():
    """Main entry point."""
    logger.info("=" * 80)
    logger.info("🚀 ENTERPRISE UNIFIED CELERY WORKER - TUKI PLATFORM")
    logger.info("=" * 80)
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start health check server in background
    health_thread = Thread(target=start_health_server, args=(8080,), daemon=True)
    health_thread.start()
    
    # 🚀 ENTERPRISE: Start dedicated workers
    logger.info("\n📋 Starting workers with dedicated queues:")
    logger.info("  • EMAILS: 4 workers (instant delivery)")
    logger.info("  • CRITICAL: 2 workers (high priority)")
    logger.info("  • GENERAL: 2 workers (default tasks)")
    logger.info("  • SYNC: 1 worker (heavy operations)")
    logger.info("")
    
    try:
        # Worker 1: EMAILS (highest priority, instant delivery)
        worker_processes.append(
            start_celery_worker(
                name='emails',
                queues='emails',
                concurrency=4,
                max_memory_mb=1500
            )
        )
        time.sleep(2)  # Stagger startup
        
        # Worker 2: CRITICAL (high priority)
        worker_processes.append(
            start_celery_worker(
                name='critical',
                queues='critical',
                concurrency=2,
                max_memory_mb=1500
            )
        )
        time.sleep(2)
        
        # Worker 3: GENERAL (default tasks)
        worker_processes.append(
            start_celery_worker(
                name='general',
                queues='default,maintenance,documents',
                concurrency=2,
                max_memory_mb=1500
            )
        )
        time.sleep(2)
        
        # Worker 4: SYNC (heavy operations)
        worker_processes.append(
            start_celery_worker(
                name='sync',
                queues='sync-heavy',
                concurrency=1,
                max_memory_mb=2000  # More memory for heavy sync
            )
        )
        
        logger.info("\n✅ All workers started successfully!")
        logger.info("📊 Monitoring workers... (Ctrl+C to stop)\n")
        
        # Monitor workers
        while True:
            time.sleep(30)
            
            # Check if any worker died
            for i, process in enumerate(worker_processes):
                if process.poll() is not None:
                    logger.error(f"❌ Worker {i+1} died with exit code {process.returncode}")
                    logger.error("🔄 Restarting all workers...")
                    signal_handler(signal.SIGTERM, None)
            
            # Log status
            alive_count = sum(1 for p in worker_processes if p.poll() is None)
            logger.info(f"💚 Workers alive: {alive_count}/{len(worker_processes)}")
    
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        signal_handler(signal.SIGTERM, None)


if __name__ == '__main__':
    main()

