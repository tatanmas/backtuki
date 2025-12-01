"""
🚀 ENTERPRISE: Celery signal handlers for automatic task logging

This module connects to Celery's built-in signals to automatically log
ALL task executions to the database, providing complete visibility into
async operations without requiring manual instrumentation of every task.

Signals handled:
- task_prerun: Log when task starts
- task_postrun: Log when task succeeds
- task_failure: Log when task fails
- task_retry: Log when task retries

The handlers automatically extract business context (flow_id, order_id, user_id)
from task arguments to enable cross-referencing with business entities.

Setup:
    Import this module in config/celery.py to register the signals:
    
    from core import celery_signals  # noqa
"""

from celery.signals import task_prerun, task_postrun, task_failure, task_retry
from django.utils import timezone
import logging
import time

logger = logging.getLogger(__name__)

# Store task start times for duration calculation
_task_start_times = {}


def _resolve_context(task_name, args, kwargs):
    """
    Extract business context (flow, order, user) from task arguments.
    
    This function attempts to intelligently extract references to business
    entities from task arguments to enable automatic linking of task logs
    to flows and orders.
    
    Args:
        task_name: Full task name (e.g., 'apps.events.tasks.send_order_confirmation_email')
        args: Positional arguments tuple
        kwargs: Keyword arguments dict
    
    Returns:
        Tuple of (flow, order, user)
    """
    # Import models here to avoid AppRegistryNotReady error
    from core.models import PlatformFlow
    from apps.events.models import Order
    
    flow = None
    order = None
    user = None
    
    # 1. Try to get flow_id from kwargs (explicitly passed)
    flow_id = kwargs.get('flow_id')
    if flow_id:
        try:
            flow = PlatformFlow.objects.get(id=flow_id)
            logger.debug(f"📊 [CELERY] Resolved flow from kwargs: {flow_id}")
        except PlatformFlow.DoesNotExist:
            logger.warning(f"⚠️ [CELERY] Flow {flow_id} not found in kwargs")
        except Exception as e:
            logger.error(f"❌ [CELERY] Error resolving flow from kwargs: {e}")
    
    # 2. Try to get order_id from kwargs or first positional arg
    order_id = kwargs.get('order_id')
    if not order_id and args and len(args) > 0:
        # For email tasks, first arg is usually order_id
        if 'email' in task_name.lower() or 'order' in task_name.lower():
            order_id = args[0]
    
    if order_id:
        try:
            order = Order.objects.select_related('user', 'flow').get(id=order_id)
            user = order.user
            
            # If we don't have a flow yet, try to get it from the order
            if not flow and hasattr(order, 'flow') and order.flow:
                flow = order.flow
                logger.debug(f"📊 [CELERY] Resolved flow from order: {flow.id}")
            
            logger.debug(f"📊 [CELERY] Resolved order: {order.order_number}")
        except Order.DoesNotExist:
            logger.warning(f"⚠️ [CELERY] Order {order_id} not found")
        except Exception as e:
            logger.error(f"❌ [CELERY] Error resolving order: {e}")
    
    # 3. Try to get user_id from kwargs
    user_id = kwargs.get('user_id')
    if user_id and not user:
        try:
            from apps.users.models import User
            user = User.objects.get(id=user_id)
            logger.debug(f"📊 [CELERY] Resolved user from kwargs: {user.email}")
        except Exception as e:
            logger.error(f"❌ [CELERY] Error resolving user from kwargs: {e}")
    
    return flow, order, user


@task_prerun.connect
def log_task_started(sender=None, task_id=None, args=None, kwargs=None, **extras):
    """
    Log when a Celery task starts execution.
    
    Connected to celery.signals.task_prerun.
    
    Args:
        sender: Task class
        task_id: Unique task execution ID (UUID)
        args: Positional arguments
        kwargs: Keyword arguments
        **extras: Additional signal data
    """
    try:
        # Import models here to avoid AppRegistryNotReady error
        from core.models import CeleryTaskLog
        
        # Store start time for duration calculation
        _task_start_times[task_id] = time.time()
        
        # Resolve business context
        flow, order, user = _resolve_context(sender.name, args or [], kwargs or {})
        
        # Create task log
        task_log = CeleryTaskLog.objects.create(
            task_id=task_id,
            task_name=sender.name,
            status='started',
            queue=getattr(sender, 'queue', ''),
            routing_key=getattr(sender, 'routing_key', ''),
            args=list(args or []),
            kwargs=dict(kwargs or {}),
            flow=flow,
            order=order,
            user=user,
        )
        
        logger.info(
            f"🚀 [CELERY] Task started: {sender.name} "
            f"(task_id: {task_id[:8]}, order: {order.order_number if order else 'N/A'})"
        )
        
        # Also log to flow if available (only for email tasks)
        if flow and 'email' in sender.name.lower():
            from core.flow_logger import FlowLogger
            flow_logger = FlowLogger(flow)
            
            flow_logger.log_event(
                'EMAIL_TASK_STARTED',
                source='celery',
                status='info',
                message=f"Task {sender.name.split('.')[-1]} started",
                order=order,
                celery_task_log=task_log,
                metadata={'task_id': task_id, 'task_name': sender.name}
            )
    
    except Exception as e:
        # Never let logging errors break task execution
        logger.error(f"❌ [CELERY] Error in task_prerun signal: {e}", exc_info=True)


@task_postrun.connect
def log_task_success(sender=None, task_id=None, retval=None, **extras):
    """
    Log when a Celery task completes successfully.
    
    Connected to celery.signals.task_postrun.
    
    Args:
        sender: Task class
        task_id: Unique task execution ID (UUID)
        retval: Task return value
        **extras: Additional signal data
    """
    try:
        # Import models here to avoid AppRegistryNotReady error
        from core.models import CeleryTaskLog
        
        # Calculate duration
        duration_ms = None
        if task_id in _task_start_times:
            duration_ms = int((time.time() - _task_start_times[task_id]) * 1000)
            del _task_start_times[task_id]
        
        # Update existing task log
        task_log = CeleryTaskLog.objects.filter(task_id=task_id, status='started').first()
        if task_log:
            task_log.status = 'success'
            task_log.duration_ms = duration_ms
            
            # Store result if it's serializable
            if retval is not None:
                if isinstance(retval, dict):
                    task_log.result = retval
                else:
                    task_log.result = {'result': str(retval)}
            
            task_log.save()
            
            logger.info(
                f"✅ [CELERY] Task succeeded: {sender.name} "
                f"(task_id: {task_id[:8]}, duration: {duration_ms}ms)"
            )
            
            # Log to flow if available
            if task_log.flow:
                from core.flow_logger import FlowLogger
                flow_logger = FlowLogger(task_log.flow)
                
                # For email tasks, log specific event
                if 'email' in sender.name.lower():
                    flow_logger.log_event(
                        'EMAIL_SENT',
                        source='celery',
                        status='success',
                        message=f"Email sent successfully",
                        order=task_log.order,
                        celery_task_log=task_log,
                        metadata={
                            'task_id': task_id,
                            'duration_ms': duration_ms,
                            'task_name': sender.name
                        }
                    )
        else:
            logger.warning(f"⚠️ [CELERY] No started log found for task {task_id[:8]}")
    
    except Exception as e:
        logger.error(f"❌ [CELERY] Error in task_postrun signal: {e}", exc_info=True)


@task_failure.connect
def log_task_failure(sender=None, task_id=None, exception=None, traceback=None, 
                     einfo=None, args=None, kwargs=None, **extras):
    """
    Log when a Celery task fails.
    
    Connected to celery.signals.task_failure.
    
    Args:
        sender: Task class
        task_id: Unique task execution ID (UUID)
        exception: Exception that caused the failure
        traceback: Traceback object
        einfo: ExceptionInfo object
        args: Positional arguments
        kwargs: Keyword arguments
        **extras: Additional signal data
    """
    try:
        # Import models here to avoid AppRegistryNotReady error
        from core.models import CeleryTaskLog
        
        # Calculate duration
        duration_ms = None
        if task_id in _task_start_times:
            duration_ms = int((time.time() - _task_start_times[task_id]) * 1000)
            del _task_start_times[task_id]
        
        # Resolve business context
        flow, order, user = _resolve_context(sender.name, args or [], kwargs or {})
        
        # Get traceback string
        traceback_str = str(traceback or getattr(einfo, 'traceback', ''))
        
        # Create or update task log
        task_log = CeleryTaskLog.objects.filter(task_id=task_id, status='started').first()
        if task_log:
            task_log.status = 'failure'
            task_log.error = str(exception)
            task_log.traceback = traceback_str
            task_log.duration_ms = duration_ms
            task_log.save()
        else:
            # Create new log if prerun didn't fire
            task_log = CeleryTaskLog.objects.create(
                task_id=task_id,
                task_name=sender.name,
                status='failure',
                error=str(exception),
                traceback=traceback_str,
                duration_ms=duration_ms,
                flow=flow,
                order=order,
                user=user,
            )
        
        logger.error(
            f"❌ [CELERY] Task failed: {sender.name} "
            f"(task_id: {task_id[:8]}, error: {str(exception)[:100]})"
        )
        
        # Log to flow if available
        if flow:
            from core.flow_logger import FlowLogger
            flow_logger = FlowLogger(flow)
            
            # For email tasks, log specific event
            if 'email' in sender.name.lower():
                flow_logger.log_event(
                    'EMAIL_FAILED',
                    source='celery',
                    status='failure',
                    message=f"Email task failed: {str(exception)[:200]}",
                    order=order,
                    celery_task_log=task_log,
                    metadata={
                        'task_id': task_id,
                        'error': str(exception),
                        'error_type': type(exception).__name__,
                        'duration_ms': duration_ms
                    }
                )
    
    except Exception as e:
        logger.error(f"❌ [CELERY] Error in task_failure signal: {e}", exc_info=True)


@task_retry.connect
def log_task_retry(sender=None, task_id=None, reason=None, einfo=None, **extras):
    """
    Log when a Celery task is retried.
    
    Connected to celery.signals.task_retry.
    
    Args:
        sender: Task class (if available)
        task_id: Unique task execution ID (UUID)
        reason: Reason for retry (usually an exception)
        einfo: ExceptionInfo object
        **extras: Additional signal data
    """
    try:
        # Import models here to avoid AppRegistryNotReady error
        from core.models import CeleryTaskLog
        
        # Get task name from sender or from request
        task_name = sender.name if sender else extras.get('request', {}).get('task', 'unknown')
        
        # Get traceback string
        traceback_str = str(getattr(einfo, 'traceback', ''))
        
        # Create retry log
        CeleryTaskLog.objects.create(
            task_id=task_id,
            task_name=task_name,
            status='retry',
            error=str(reason or ''),
            traceback=traceback_str,
        )
        
        logger.warning(
            f"⚠️ [CELERY] Task retry: {task_name} "
            f"(task_id: {task_id[:8]}, reason: {str(reason)[:100]})"
        )
    
    except Exception as e:
        logger.error(f"❌ [CELERY] Error in task_retry signal: {e}", exc_info=True)


# Cleanup function to prevent memory leaks
def cleanup_task_start_times():
    """
    Clean up old task start times to prevent memory leaks.
    
    Call this periodically (e.g., from a scheduled task) to remove
    start times for tasks that never completed (crashed workers, etc.)
    """
    current_time = time.time()
    old_task_ids = [
        task_id for task_id, start_time in _task_start_times.items()
        if current_time - start_time > 3600  # 1 hour
    ]
    
    for task_id in old_task_ids:
        del _task_start_times[task_id]
    
    if old_task_ids:
        logger.info(f"🧹 [CELERY] Cleaned up {len(old_task_ids)} old task start times")

