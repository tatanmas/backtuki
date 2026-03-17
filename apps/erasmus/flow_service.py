"""
Erasmus activity inscription flow tracking.

Single responsibility: start flow when payment link/order are created, and log
payment steps (initiated, failed). All functions are defensive: errors are
logged and never raised so business logic is never broken.
"""
import logging
from typing import Optional, Any, Dict

from core.flow_logger import FlowLogger

logger = logging.getLogger(__name__)


def start_flow_for_payment_link(link, order, is_free=False) -> Optional[FlowLogger]:
    """
    Start a platform flow for this payment link and order, link order to flow,
    and log ORDER_CREATED + PAYMENT_REQUIRED (or INSCRIPTION_CONFIRMED for free).

    Call after creating ErasmusActivityPaymentLink and Order in the same transaction.
    Does not raise; returns None on any error.
    """
    try:
        if not link or not order:
            return None
        instance = getattr(link, "instance", None)
        activity = getattr(instance, "activity", None) if instance else None
        lead = getattr(link, "lead", None)
        metadata = {}
        if lead:
            metadata["lead_id"] = getattr(lead, "id", None)
        if instance:
            metadata["instance_id"] = getattr(instance, "id", None)
        if activity:
            metadata["activity_id"] = getattr(activity, "id", None)

        flow = FlowLogger.start_flow(
            "erasmus_activity_inscription",
            user=None,
            organizer=None,
            event=None,
            experience=None,
            accommodation=None,
            erasmus_activity=activity,
            metadata=metadata or None,
        )
        if not flow or not getattr(flow, "flow", None):
            return None

        flow.update_order(order)
        order.flow = flow.flow
        order.save(update_fields=["flow"])

        order_number = getattr(order, "order_number", "") or str(order.id)
        flow.log_event(
            "ORDER_CREATED",
            order=order,
            message=f"Order {order_number} created for Erasmus activity inscription",
            metadata={"order_id": getattr(order, "id", None)},
        )
        if is_free or (getattr(order, "total", None) is not None and order.total == 0):
            flow.log_event(
                "INSCRIPTION_CONFIRMED",
                order=order,
                message=f"Free inscription confirmed for order {order_number}",
            )
        else:
            flow.log_event(
                "PAYMENT_REQUIRED",
                order=order,
                message=f"Payment required for order {order_number}",
            )
        return flow
    except Exception as e:
        logger.warning(
            "Erasmus flow_service.start_flow_for_payment_link failed: %s",
            e,
            exc_info=True,
        )
        return None


def log_payment_initiated(order) -> None:
    """
    Log PAYMENT_INITIATED for this order if it has a flow.
    Does not raise.
    """
    try:
        if not order or not getattr(order, "flow_id", None):
            return
        flow = FlowLogger.from_flow_id(order.flow_id)
        if not flow:
            return
        order_number = getattr(order, "order_number", "") or str(getattr(order, "id", ""))
        flow.log_event(
            "PAYMENT_INITIATED",
            order=order,
            source="api",
            status="info",
            message=f"Payment initiated for order {order_number}",
        )
    except Exception as e:
        logger.warning(
            "Erasmus flow_service.log_payment_initiated failed: %s",
            e,
            exc_info=True,
        )


def log_payment_failed(
    order,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log PAYMENT_FAILED and mark flow as failed for this order if it has a flow.
    Does not raise.
    """
    try:
        if not order or not getattr(order, "flow_id", None):
            return
        flow = FlowLogger.from_flow_id(order.flow_id)
        if not flow:
            return
        flow.log_event(
            "PAYMENT_FAILED",
            order=order,
            source="payment_gateway",
            status="failure",
            message=message or "Payment failed",
            metadata=metadata,
        )
        flow.fail(message=message or "Payment failed")
    except Exception as e:
        logger.warning(
            "Erasmus flow_service.log_payment_failed failed: %s",
            e,
            exc_info=True,
        )
