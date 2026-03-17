"""
SuperAdmin Orders & Payments API.
Lista unificada de órdenes (eventos, experiencias, alojamientos, Erasmus, etc.)
con estado de pago, intentos y últimos errores. Enterprise, escalable.
Incluye: is_sandbox (excluidas del revenue), soft delete (papelera) y eliminación permanente.
"""
import logging
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.events.models import Order
from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)


def _order_product_label(order) -> str:
    """Human-readable product label by order_kind."""
    kind = getattr(order, "order_kind", "event") or "event"
    if kind == "event" and order.event_id:
        return order.event.title if order.event else "Evento"
    if kind == "experience" and getattr(order, "experience_reservation", None):
        try:
            exp = order.experience_reservation.experience
            return exp.title if exp else "Experiencia"
        except Exception:
            return "Experiencia"
    if kind == "accommodation":
        return "Alojamiento"
    if kind == "car_rental":
        return "Arriendo auto"
    if kind == "erasmus_activity" and getattr(order, "erasmus_activity_payment_link", None):
        link = order.erasmus_activity_payment_link
        if link and link.instance_id:
            try:
                act = link.instance.activity
                return act.title_es or act.title_en or "Actividad Erasmus"
            except Exception:
                pass
        return "Actividad Erasmus"
    return kind.replace("_", " ").title()


def _serialize_order_list_item(order, last_payment=None, last_error=None, payments_count=0):
    """One order row for list API."""
    return {
        "id": str(order.id),
        "order_number": order.order_number or "",
        "order_kind": getattr(order, "order_kind", "event") or "event",
        "status": order.status,
        "total": float(order.total),
        "subtotal": float(order.subtotal),
        "service_fee": float(order.service_fee or 0),
        "email": order.email or "",
        "first_name": order.first_name or "",
        "last_name": order.last_name or "",
        "phone": order.phone or "",
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "product_label": _order_product_label(order),
        "is_sandbox": getattr(order, "is_sandbox", False),
        "deleted_at": order.deleted_at.isoformat() if getattr(order, "deleted_at", None) else None,
        "exclude_from_revenue": getattr(order, "exclude_from_revenue", False),
        "payment_summary": {
            "payments_count": payments_count,
            "last_payment_status": last_payment.status if last_payment else None,
            "last_payment_id": str(last_payment.id) if last_payment else None,
            "last_payment_at": last_payment.created_at.isoformat() if last_payment and last_payment.created_at else None,
            "last_error": last_error,
        },
    }


@api_view(["GET"])
@permission_classes([IsSuperUser])
def orders_list(request):
    """
    GET /api/v1/superadmin/orders/
    Lista paginada de órdenes con resumen de pago (estado, intentos, último error).
    Query params: status, order_kind, page, page_size (default 20), search (email/order_number),
    show_deleted (1|true) to list only soft-deleted orders (trash), omit to list only active.
    """
    from payment_processor.models import Payment, PaymentTransaction

    try:
        status_filter = request.query_params.get("status", "").strip().lower()
        kind_filter = request.query_params.get("order_kind", "").strip().lower()
        search = request.query_params.get("search", "").strip()
        show_deleted = request.query_params.get("show_deleted", "").strip().lower() in ("1", "true", "yes")
        revenue_filter = request.query_params.get("revenue", "").strip().lower()
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))

        qs = (
            Order.objects.select_related(
                "event",
                "experience_reservation",
                "accommodation_reservation",
                "erasmus_activity_payment_link",
                "erasmus_activity_payment_link__instance",
                "erasmus_activity_payment_link__instance__activity",
            )
            .prefetch_related(
                Prefetch(
                    "payments",
                    queryset=Payment.objects.order_by("-created_at"),
                    to_attr="payments_list",
                )
            )
            .order_by("-created_at")
        )

        if show_deleted:
            qs = qs.filter(deleted_at__isnull=False)
        else:
            qs = qs.filter(deleted_at__isnull=True)

        if status_filter:
            qs = qs.filter(status=status_filter)
        if kind_filter:
            qs = qs.filter(order_kind=kind_filter)
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(order_number__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        if revenue_filter == "included":
            qs = qs.filter(exclude_from_revenue=False)
        elif revenue_filter == "excluded":
            qs = qs.filter(exclude_from_revenue=True)

        total_count = qs.count()
        start = (page - 1) * page_size
        orders_page = list(qs[start : start + page_size])

        # Use prefetched payments_list (already ordered by -created_at); collect payment ids for errors
        payment_ids = []
        for o in orders_page:
            pay_list = getattr(o, "payments_list", None) or []
            payment_ids.extend(p.id for p in pay_list)

        # Last failed transaction error per payment (most recent failed tx per payment)
        failed_tx = (
            PaymentTransaction.objects.filter(
                payment_id__in=payment_ids, is_successful=False
            )
            .order_by("-created_at")
            .values("payment_id", "error_message")
        )
        error_by_payment = {}
        for tx in failed_tx:
            if tx["payment_id"] not in error_by_payment:
                error_by_payment[tx["payment_id"]] = tx["error_message"] or ""

        results = []
        for order in orders_page:
            payments_list = getattr(order, "payments_list", None) or []
            last_payment = payments_list[0] if payments_list else None
            last_error = None
            if last_payment and last_payment.status == "failed":
                last_error = error_by_payment.get(last_payment.id)
            results.append(
                _serialize_order_list_item(
                    order,
                    last_payment=last_payment,
                    last_error=last_error,
                    payments_count=len(payments_list),
                )
            )

        return Response(
            {
                "success": True,
                "count": total_count,
                "page": page,
                "page_size": page_size,
                "results": results,
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        logger.exception("SuperAdmin orders_list error: %s", e)
        return Response(
            {"success": False, "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsSuperUser])
def order_detail(request, order_id):
    """
    GET /api/v1/superadmin/orders/<order_id>/
    Detalle de una orden: datos de la orden + todos los intentos de pago (Payment)
    y por cada uno los registros de transacción (PaymentTransaction) con request/response y error.
    """
    from payment_processor.models import Payment, PaymentTransaction

    try:
        order = (
            Order.objects.select_related(
                "event",
                "experience_reservation",
                "accommodation_reservation",
                "erasmus_activity_payment_link",
                "erasmus_activity_payment_link__instance",
                "erasmus_activity_payment_link__instance__activity",
                "erasmus_activity_payment_link__lead",
            )
            .prefetch_related(
                Prefetch(
                    "payments",
                    queryset=Payment.objects.select_related("payment_method").order_by("-created_at"),
                )
            )
            .get(id=order_id)
        )
    except Order.DoesNotExist:
        return Response(
            {"success": False, "detail": "Orden no encontrada."},
            status=status.HTTP_404_NOT_FOUND,
        )

    payments_data = []
    for pay in order.payments.all():
        transactions = list(
            PaymentTransaction.objects.filter(payment=pay).order_by("-created_at")
        )
        payments_data.append({
            "id": str(pay.id),
            "buy_order": pay.buy_order,
            "status": pay.status,
            "amount": float(pay.amount),
            "currency": pay.currency,
            "created_at": pay.created_at.isoformat() if pay.created_at else None,
            "completed_at": pay.completed_at.isoformat() if pay.completed_at else None,
            "payment_method": pay.payment_method.display_name if pay.payment_method_id else None,
            "transactions": [
                {
                    "id": str(tx.id),
                    "transaction_type": tx.transaction_type,
                    "is_successful": tx.is_successful,
                    "error_message": tx.error_message or None,
                    "request_data": tx.request_data,
                    "response_data": tx.response_data,
                    "duration_ms": tx.duration_ms,
                    "created_at": tx.created_at.isoformat() if tx.created_at else None,
                }
                for tx in transactions
            ],
        })

    return Response(
        {
            "success": True,
            "order": {
                "id": str(order.id),
                "order_number": order.order_number,
                "order_kind": getattr(order, "order_kind", "event") or "event",
                "status": order.status,
                "total": float(order.total),
                "subtotal": float(order.subtotal),
                "service_fee": float(order.service_fee or 0),
                "discount": float(order.discount or 0),
                "email": order.email,
                "first_name": order.first_name,
                "last_name": order.last_name,
                "phone": order.phone,
                "payment_method": getattr(order, "payment_method", "") or "",
                "notes": getattr(order, "notes", "") or "",
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "updated_at": order.updated_at.isoformat() if order.updated_at else None,
                "product_label": _order_product_label(order),
                "is_sandbox": getattr(order, "is_sandbox", False),
                "deleted_at": order.deleted_at.isoformat() if getattr(order, "deleted_at", None) else None,
                "exclude_from_revenue": getattr(order, "exclude_from_revenue", False),
            },
            "payments": payments_data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsSuperUser])
def order_exclude_from_revenue(request, order_id):
    """
    POST /api/v1/superadmin/orders/<order_id>/exclude_from_revenue/
    Body: { "exclude": true } or { "exclude": false }
    Marks the order as excluded from revenue (test, sandbox, cortesía) or includes it again.
    When excluding, voids the organizer PayableLine if present.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return Response(
            {"success": False, "detail": "Orden no encontrada."},
            status=status.HTTP_404_NOT_FOUND,
        )
    data = request.data or {}
    exclude = data.get("exclude")
    if exclude is None:
        return Response(
            {"success": False, "detail": "Indica 'exclude': true o false en el body."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    exclude = bool(exclude)
    if order.exclude_from_revenue == exclude:
        return Response(
            {
                "success": True,
                "message": "La orden ya tiene ese estado.",
                "exclude_from_revenue": order.exclude_from_revenue,
            },
            status=status.HTTP_200_OK,
        )
    order.exclude_from_revenue = exclude
    order.save(update_fields=["exclude_from_revenue", "updated_at"])
    if exclude:
        try:
            from apps.finance.services import void_organizer_payable_for_order
            void_organizer_payable_for_order(order)
        except Exception as e:
            logger.warning("SuperAdmin order %s: void PayableLine failed: %s", order.order_number, e)
    else:
        try:
            from apps.finance.services import ensure_organizer_payable_for_order
            ensure_organizer_payable_for_order(order)
        except Exception as e:
            logger.warning("SuperAdmin order %s: ensure PayableLine failed: %s", order.order_number, e)
    logger.info(
        "SuperAdmin order %s exclude_from_revenue=%s",
        order.order_number,
        order.exclude_from_revenue,
    )
    return Response(
        {
            "success": True,
            "message": "Excluida del revenue." if exclude else "Incluida en revenue.",
            "exclude_from_revenue": order.exclude_from_revenue,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsSuperUser])
def order_soft_delete(request, order_id):
    """
    POST /api/v1/superadmin/orders/<order_id>/soft_delete/
    Mueve la orden a la papelera (soft delete). No se cuenta en revenue ni en listado por defecto.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return Response(
            {"success": False, "detail": "Orden no encontrada."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if order.deleted_at:
        return Response(
            {"success": True, "message": "La orden ya está en la papelera.", "deleted_at": order.deleted_at.isoformat()},
            status=status.HTTP_200_OK,
        )
    order.deleted_at = timezone.now()
    order.save(update_fields=["deleted_at", "updated_at"])
    logger.info("SuperAdmin order %s soft-deleted (moved to trash)", order.order_number)
    return Response(
        {"success": True, "message": "Orden movida a la papelera.", "deleted_at": order.deleted_at.isoformat()},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsSuperUser])
def order_restore(request, order_id):
    """
    POST /api/v1/superadmin/orders/<order_id>/restore/
    Restaura una orden desde la papelera (quita deleted_at).
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return Response(
            {"success": False, "detail": "Orden no encontrada."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if not order.deleted_at:
        return Response(
            {"success": True, "message": "La orden no estaba en la papelera."},
            status=status.HTTP_200_OK,
        )
    order.deleted_at = None
    order.save(update_fields=["deleted_at", "updated_at"])
    logger.info("SuperAdmin order %s restored from trash", order.order_number)
    return Response(
        {"success": True, "message": "Orden restaurada."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST", "DELETE"])
@permission_classes([IsSuperUser])
def order_permanent_delete(request, order_id):
    """
    POST or DELETE /api/v1/superadmin/orders/<order_id>/permanent_delete/
    Elimina la orden de forma permanente. Solo recomendado para órdenes en papelera.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return Response(
            {"success": False, "detail": "Orden no encontrada."},
            status=status.HTTP_404_NOT_FOUND,
        )
    order_number = order.order_number
    order.delete()
    logger.info("SuperAdmin order %s permanently deleted", order_number)
    return Response(
        {"success": True, "message": "Orden eliminada permanentemente."},
        status=status.HTTP_200_OK,
    )
