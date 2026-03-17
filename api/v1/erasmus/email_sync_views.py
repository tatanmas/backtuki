"""
🚀 ENTERPRISE: Sync send of Erasmus activity confirmation email.
Same contract as events/experiences: register in flow, send synchronously, fallback to Celery.
"""
import time
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.events.models import Order, EmailLog
from apps.erasmus.email_sender import send_erasmus_activity_confirmation_email_optimized
from core.models import PlatformFlow
from core.flow_logger import FlowLogger

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([AllowAny])
def send_erasmus_activity_email_sync(request, order_number):
    """
    🚀 ENTERPRISE: Send Erasmus activity confirmation email synchronously.
    Called from the same orders/<order_number>/send-email/ endpoint when order_kind is erasmus_activity.
    Flow: get order by token → flow → idempotency → EMAIL_SYNC_ATTEMPT → send → EMAIL_SENT or EMAIL_FAILED + Celery.
    """
    start_time = time.time()

    access_token = request.query_params.get("access_token")
    if not access_token:
        logger.warning(f"📧 [EMAIL_SYNC_ERASMUS] Missing access_token for order {order_number}")
        return Response({"success": False, "message": "Missing access_token"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        order = Order.objects.select_related(
            "erasmus_activity_payment_link",
            "erasmus_activity_payment_link__lead",
            "erasmus_activity_payment_link__instance",
        ).get(order_number=order_number, access_token=access_token, order_kind="erasmus_activity")
    except Order.DoesNotExist:
        logger.warning(f"📧 [EMAIL_SYNC_ERASMUS] Order not found or invalid token: {order_number}")
        return Response({"success": False, "message": "Order not found or invalid token"}, status=status.HTTP_404_NOT_FOUND)

    flow_obj = None
    flow_logger = None
    try:
        flow_obj = order.flow
        if not flow_obj:
            flow_obj = PlatformFlow.objects.filter(
                primary_order=order,
                flow_type="erasmus_activity_inscription",
            ).first()
        if not flow_obj and hasattr(order, "flow_events"):
            flow_event = order.flow_events.first()
            if flow_event:
                flow_obj = flow_event.flow
        if flow_obj:
            flow_logger = FlowLogger(flow_obj)
    except Exception as e:
        logger.warning(f"📧 [EMAIL_SYNC_ERASMUS] Could not find flow for order {order_number}: {e}")

    if flow_obj:
        if flow_obj.events.filter(step="EMAIL_SENT").exists():
            logger.info(f"📧 [EMAIL_SYNC_ERASMUS] ✅ Email already sent for order {order_number} (idempotency)")
            return Response(
                {"success": True, "message": "Email already sent", "already_sent": True, "emails_sent": 1},
                status=status.HTTP_200_OK,
            )

    if flow_logger:
        flow_logger.log_event(
            "EMAIL_SYNC_ATTEMPT",
            order=order,
            source="api",
            status="info",
            message=f"Attempting synchronous email send for Erasmus activity order {order_number}",
            metadata={"strategy": "frontend_sync", "triggered_by": "confirmation_page"},
        )

    logger.info(f"📧 [EMAIL_SYNC_ERASMUS] Starting synchronous email send for order {order_number}")
    to_email = request.data.get("to_email")

    result = send_erasmus_activity_confirmation_email_optimized(
        order_id=str(order.id),
        to_email=to_email,
        flow_id=str(flow_obj.id) if flow_obj else None,
    )
    total_time_ms = int((time.time() - start_time) * 1000)

    if result.get("status") == "success" and result.get("emails_sent", 0) > 0:
        logger.info(f"📧 [EMAIL_SYNC_ERASMUS] ✅ Email sent successfully for order {order_number} in {total_time_ms}ms")
        if flow_logger:
            flow_logger.log_event(
                "EMAIL_SENT",
                order=order,
                source="api",
                status="success",
                message=f"Email sent successfully in {total_time_ms}ms",
                metadata={
                    "strategy": "frontend_sync",
                    "emails_sent": result.get("emails_sent", 0),
                    "metrics": result.get("metrics", {}),
                    "total_time_ms": total_time_ms,
                },
            )
        return Response(
            {
                "success": True,
                "message": "Email sent successfully",
                "emails_sent": result.get("emails_sent", 0),
                "metrics": result.get("metrics", {}),
                "fallback_to_celery": False,
            },
            status=status.HTTP_200_OK,
        )

    logger.warning(f"📧 [EMAIL_SYNC_ERASMUS] ⚠️ Synchronous send failed for order {order_number}, falling back to Celery")
    if flow_logger:
        flow_logger.log_event(
            "EMAIL_FAILED",
            order=order,
            source="api",
            status="warning",
            message="Synchronous email send failed, falling back to Celery",
            metadata={"strategy": "frontend_sync", "error": result.get("error", "Unknown error"), "metrics": result.get("metrics", {})},
        )

    try:
        from apps.erasmus.tasks import send_erasmus_activity_confirmation_email
        task = send_erasmus_activity_confirmation_email.apply_async(
            args=[str(order.id)],
            kwargs={"flow_id": str(flow_obj.id) if flow_obj else None},
            queue="emails",
        )
        if flow_logger:
            flow_logger.log_event(
                "EMAIL_TASK_ENQUEUED",
                order=order,
                source="api",
                status="info",
                message="Email enqueued in Celery for retry",
                metadata={"task_id": task.id, "reason": "sync_send_failed"},
            )
        logger.info(f"📧 [EMAIL_SYNC_ERASMUS] Enqueued in Celery with task_id: {task.id}")
        return Response(
            {
                "success": False,
                "message": "Email failed but enqueued in Celery for retry",
                "fallback_to_celery": True,
                "task_id": task.id,
                "error": result.get("error", "Unknown error"),
            },
            status=status.HTTP_202_ACCEPTED,
        )
    except Exception as celery_error:
        logger.error(f"📧 [EMAIL_SYNC_ERASMUS] Failed to enqueue in Celery: {celery_error}")
        if flow_logger:
            flow_logger.log_event(
                "EMAIL_FAILED",
                order=order,
                source="api",
                status="failure",
                message=f"Sync failed and Celery enqueue failed: {celery_error}",
            )
        return Response(
            {"success": False, "message": "Email send failed", "error": result.get("error", str(celery_error))},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
