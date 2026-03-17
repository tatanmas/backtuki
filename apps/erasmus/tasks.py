"""
🚀 ENTERPRISE Celery tasks for Erasmus activity (e.g. confirmation email fallback).
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_erasmus_activity_confirmation_email(self, order_id: str, to_email: str = None, flow_id: str = None):
    """
    🚀 ENTERPRISE: Send Erasmus activity confirmation email (Celery fallback).
    Same pattern as experiences/events: retry on failure, log to flow.
    """
    try:
        from apps.erasmus.email_sender import send_erasmus_activity_confirmation_email_optimized
        from core.flow_logger import FlowLogger

        logger.info(f"📧 [CELERY_ERASMUS] Starting email task for order {order_id} (attempt {self.request.retries + 1}/{self.max_retries + 1})")

        if flow_id:
            fl = FlowLogger.from_flow_id(flow_id)
            if fl and fl.flow:
                fl.log_event(
                    "EMAIL_TASK_STARTED",
                    status="info",
                    message=f"Celery task started for Erasmus order {order_id}",
                    metadata={"attempt": self.request.retries + 1, "max_retries": self.max_retries + 1, "task_id": self.request.id},
                )

        result = send_erasmus_activity_confirmation_email_optimized(
            order_id=order_id,
            to_email=to_email,
            flow_id=flow_id,
        )

        if result.get("status") == "success":
            logger.info(f"✅ [CELERY_ERASMUS] Email sent for order {order_id}")
            return result
        if result.get("status") == "skipped":
            logger.warning(f"⚠️ [CELERY_ERASMUS] Email skipped for order {order_id}: {result.get('reason')}")
            return result
        raise Exception(result.get("error", "Unknown error"))

    except Exception as exc:
        logger.error(f"❌ [CELERY_ERASMUS] Error for order {order_id}: {exc}", exc_info=True)
        if flow_id:
            try:
                from core.flow_logger import FlowLogger
                fl = FlowLogger.from_flow_id(flow_id)
                if fl and fl.flow:
                    fl.log_event(
                        "EMAIL_FAILED",
                        status="failure",
                        message=f"Celery task failed: {exc}",
                        metadata={"error": str(exc), "attempt": self.request.retries + 1},
                    )
            except Exception:
                pass
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        return {"status": "error", "error": str(exc)}
