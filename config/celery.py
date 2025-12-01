"""
🚀 ENTERPRISE CELERY CONFIGURATION for Tuki Platform

This configuration handles async tasks and periodic jobs for the ticketing system,
including automatic cleanup of expired ticket holds to prevent overselling.
"""

from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('tuki')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# 🚀 ENTERPRISE PERIODIC TASKS SCHEDULE
app.conf.beat_schedule = {
    # Critical: Clean expired ticket holds every 5 minutes
    'cleanup-expired-holds': {
        'task': 'apps.events.tasks.cleanup_expired_ticket_holds',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
        'options': {
            'queue': 'critical',  # High priority queue
            'routing_key': 'critical.cleanup_holds',
        }
    },
    
    # Send event reminders 24 hours before events
    'send-event-reminders': {
        'task': 'apps.events.tasks.schedule_event_reminders',
        'schedule': crontab(hour=10, minute=0),  # Daily at 10 AM
        'options': {
            'queue': 'emails',
            'routing_key': 'emails.reminders',
        }
    },
    
    # Clean up old completed orders (weekly)
    'weekly-order-cleanup': {
        'task': 'apps.events.tasks.cleanup_old_orders',
        'schedule': crontab(hour=2, minute=0, day_of_week=1),  # Monday at 2 AM
        'options': {
            'queue': 'maintenance',
            'routing_key': 'maintenance.cleanup_orders',
        }
    },
    
    # 🚀 ENTERPRISE: WooCommerce Sync Tasks
    'run-scheduled-woocommerce-syncs': {
        'task': 'apps.sync_woocommerce.tasks.run_scheduled_syncs',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {
            'queue': 'default',
            'routing_key': 'sync.scheduled',
        }
    },
    
    # Clean up old sync executions (weekly)
    'cleanup-sync-executions': {
        'task': 'apps.sync_woocommerce.tasks.cleanup_old_executions',
        'schedule': crontab(hour=3, minute=0, day_of_week=1),  # Monday at 3 AM
        'options': {
            'queue': 'maintenance',
            'routing_key': 'maintenance.cleanup_syncs',
        }
    },
}

# 🚀 ENTERPRISE TASK ROUTING
app.conf.task_routes = {
    'apps.events.tasks.cleanup_expired_ticket_holds': {'queue': 'critical'},
    'apps.events.tasks.send_ticket_confirmation_email': {'queue': 'emails'},
    'apps.events.tasks.send_event_reminder_email': {'queue': 'emails'},
    'apps.events.tasks.send_welcome_organizer_email': {'queue': 'emails'},
    'apps.events.tasks.schedule_event_reminders': {'queue': 'emails'},
    'apps.events.tasks.generate_ticket_pdf': {'queue': 'documents'},
    
    # 🚀 ENTERPRISE: WooCommerce Sync Task Routing
    # sync_woocommerce_event va a cola dedicada 'sync-heavy' con concurrencia=1
    'apps.sync_woocommerce.tasks.sync_woocommerce_event': {'queue': 'sync-heavy'},
    'apps.sync_woocommerce.tasks.run_scheduled_syncs': {'queue': 'default'},
    'apps.sync_woocommerce.tasks.cleanup_old_executions': {'queue': 'maintenance'},
    'apps.sync_woocommerce.tasks.test_woocommerce_connection': {'queue': 'default'},
}

# 🚀 ENTERPRISE CELERY CONFIGURATION
app.conf.update(
    timezone='America/Santiago',
    enable_utc=True,
    
    # Task execution settings
    task_soft_time_limit=1700,  # 28 minutes soft limit (para WooCommerce sync)
    task_time_limit=1800,       # 30 minutes hard limit (para WooCommerce sync)
    task_acks_late=True,       # Acknowledge after task completion
    worker_prefetch_multiplier=1,  # Process one task at a time for reliability
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    
    # Worker settings for high availability
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_disable_rate_limits=False,
    
    # Queue priorities (enterprise-grade)
    task_default_queue='default',
    task_default_exchange='default',
    task_default_exchange_type='direct',
    task_default_routing_key='default',
)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Task to debug Celery worker."""
    print(f'🔍 DEBUG: Celery task executed - Request: {self.request!r}')


# 🚀 ENTERPRISE: Import Celery signals for automatic task logging
# This registers signal handlers that log ALL task executions to the database
from core import celery_signals  # noqa 