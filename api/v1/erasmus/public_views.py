"""
Public API for Erasmus activity: view inscritos and full edit by token (no auth).
Same response shape as superadmin so the frontend can reuse the same UI.
"""

from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.erasmus.models import (
    ErasmusActivity,
    ErasmusActivityInstance,
    ErasmusActivityPublicLink,
    ErasmusActivityReview,
    ErasmusLead,
    ErasmusActivityInscriptionPayment,
    ErasmusActivityPaymentLink,
)
from rest_framework.exceptions import ValidationError as DRFValidationError
from api.v1.superadmin.serializers import (
    JsonErasmusActivityInstanceSerializer,
    validate_itinerary_items,
)


def _format_time(t):
    if t is None:
        return None
    return t.strftime("%H:%M")


def _parse_time(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _inscription_payment_dict(payment):
    """Return a small dict for an ErasmusActivityInscriptionPayment or None."""
    if not payment:
        return None
    return {
        "amount": str(payment.amount),
        "payment_method": payment.payment_method,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
    }


def _activity_to_dict(act, include_instances=False):
    """Same shape as superadmin _activity_to_dict for edit UI."""
    images = act.images or []
    main = images[0] if images else None
    if isinstance(main, dict):
        main = main.get("url") or main.get("image") or main.get("src") or ""
    data = {
        "id": str(act.id),
        "slug": act.slug,
        "title_es": act.title_es,
        "title_en": act.title_en or "",
        "description_es": act.description_es or "",
        "description_en": act.description_en or "",
        "short_description_es": act.short_description_es or "",
        "short_description_en": act.short_description_en or "",
        "location": act.location or "",
        "location_name": getattr(act, "location_name", "") or "",
        "location_address": getattr(act, "location_address", "") or "",
        "duration_minutes": getattr(act, "duration_minutes", None),
        "included": getattr(act, "included", None) or [],
        "not_included": getattr(act, "not_included", None) or [],
        "itinerary": getattr(act, "itinerary", None) or [],
        "images": images,
        "image": main or "",
        "display_order": act.display_order,
        "is_active": act.is_active,
        "detail_layout": getattr(act, "detail_layout", "default") or "default",
        "experience_id": str(act.experience_id) if act.experience_id else None,
        "created_at": act.created_at.isoformat() if act.created_at else None,
        "updated_at": act.updated_at.isoformat() if act.updated_at else None,
        "is_paid": getattr(act, "is_paid", False),
        "price": str(act.price) if getattr(act, "price", None) is not None else None,
    }
    if include_instances:
        data["instances"] = []
        for inst in act.instances.order_by("display_order", "scheduled_date", "scheduled_year", "scheduled_month"):
            inscribed_count = ErasmusLead.objects.filter(
                interested_experiences__contains=[str(inst.id)]
            ).count()
            data["instances"].append({
                "id": str(inst.id),
                "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                "scheduled_month": inst.scheduled_month,
                "scheduled_year": inst.scheduled_year,
                "scheduled_label_es": inst.scheduled_label_es or "",
                "scheduled_label_en": inst.scheduled_label_en or "",
                "start_time": _format_time(getattr(inst, "start_time", None)),
                "end_time": _format_time(getattr(inst, "end_time", None)),
                "display_order": inst.display_order,
                "is_active": inst.is_active,
                "capacity": getattr(inst, "capacity", None),
                "is_agotado": getattr(inst, "is_agotado", False),
                "interested_count_boost": getattr(inst, "interested_count_boost", 0) or 0,
                "instructions_es": getattr(inst, "instructions_es", "") or "",
                "instructions_en": getattr(inst, "instructions_en", "") or "",
                "whatsapp_message_es": getattr(inst, "whatsapp_message_es", "") or "",
                "whatsapp_message_en": getattr(inst, "whatsapp_message_en", "") or "",
                "inscribed_count": inscribed_count,
            })
    return data


def _normalize_images(raw_images):
    if not raw_images:
        return []
    out = []
    for item in raw_images:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            out.append(item.get("url") or item.get("image") or item.get("src") or "")
    return out


def _get_activity_by_view_token(view_token):
    try:
        link = ErasmusActivityPublicLink.objects.select_related("activity").get(view_token=view_token)
    except ErasmusActivityPublicLink.DoesNotExist:
        return None, None
    if not link.links_enabled:
        return None, "disabled"
    return link.activity, None


def _get_activity_by_edit_token(edit_token):
    try:
        link = ErasmusActivityPublicLink.objects.select_related("activity").get(edit_token=edit_token)
    except ErasmusActivityPublicLink.DoesNotExist:
        return None, None
    if not link.links_enabled:
        return None, "disabled"
    return link.activity, None


def _get_activity_by_review_token(review_token):
    """Return (activity, None) or (None, 'disabled'/'not_found'). Requires links_enabled and review_link_enabled."""
    if not review_token or not isinstance(review_token, str) or not review_token.strip():
        return None, None
    try:
        link = ErasmusActivityPublicLink.objects.select_related("activity").get(review_token=review_token.strip())
    except ErasmusActivityPublicLink.DoesNotExist:
        return None, None
    if not link.links_enabled:
        return None, "disabled"
    if not getattr(link, "review_link_enabled", True):
        return None, "disabled"
    return link.activity, None


def _instance_label_for_review(inst):
    """Short label for instance (date or month/year or label_es)."""
    if inst.scheduled_date:
        return inst.scheduled_date.strftime("%d/%m/%Y")
    if inst.scheduled_label_es:
        return inst.scheduled_label_es
    if inst.scheduled_month and inst.scheduled_year:
        return f"{inst.scheduled_month:02d}/{inst.scheduled_year}"
    return str(inst.id)


class ErasmusPublicViewInscritosView(APIView):
    """
    GET /api/v1/erasmus/public/view/<view_token>/
    Public (no auth). Returns activity title + instances with full list of inscritos per instance.
    When links_enabled is False returns 404.
    """
    permission_classes = [AllowAny]

    def get(self, request, view_token):
        act, err = _get_activity_by_view_token(view_token)
        if err == "disabled":
            return Response({"detail": "Link desactivado."}, status=status.HTTP_404_NOT_FOUND)
        if act is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        instances = []
        for inst in act.instances.order_by("display_order", "scheduled_date", "scheduled_year", "scheduled_month"):
            leads = list(
                ErasmusLead.objects.filter(
                    interested_experiences__contains=[str(inst.id)]
                ).order_by("-updated_at").values(
                    "id", "first_name", "last_name", "email",
                    "phone_country_code", "phone_number", "instagram", "updated_at"
                )
            )
            # Payment status per inscription (lead+instance)
            lead_ids = [l["id"] for l in leads]
            payments = {
                (str(p.lead_id), str(p.instance_id)): p
                for p in ErasmusActivityInscriptionPayment.objects.filter(
                    lead_id__in=lead_ids,
                    instance=inst,
                ).select_related("lead", "instance")
            }
            label = inst.scheduled_label_es or (inst.scheduled_date.isoformat() if inst.scheduled_date else str(inst.id))
            instances.append({
                "id": str(inst.id),
                "label": label,
                "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                "inscriptions": [
                    {
                        "id": str(l["id"]),
                        "first_name": l["first_name"] or "",
                        "last_name": l["last_name"] or "",
                        "email": l["email"] or "",
                        "phone_country_code": l["phone_country_code"] or "",
                        "phone_number": l["phone_number"] or "",
                        "instagram": l["instagram"] or "",
                        "updated_at": l["updated_at"].isoformat() if l.get("updated_at") else None,
                        "payment": _inscription_payment_dict(payments.get((str(l["id"]), str(inst.id)))),
                    }
                    for l in leads
                ],
                "count": len(leads),
            })
        return Response({
            "activity": {
                "id": str(act.id),
                "title_es": act.title_es,
                "title_en": act.title_en or act.title_es,
                "slug": act.slug,
                "is_paid": getattr(act, "is_paid", False),
                "price": str(act.price) if getattr(act, "price", None) is not None else None,
            },
            "instances": instances,
            "links_enabled": True,
        })


class ErasmusPublicViewMarkPaidView(APIView):
    """
    POST /api/v1/erasmus/public/view/<view_token>/mark-paid/
    Body: { "lead_id": "uuid", "instance_id": "uuid", "amount": "1234.56", "payment_method": "efectivo" }
    Marks an inscription (lead + instance) as paid. Activity must have is_paid=True.
    """
    permission_classes = [AllowAny]

    def post(self, request, view_token):
        act, err = _get_activity_by_view_token(view_token)
        if err == "disabled":
            return Response({"detail": "Link desactivado."}, status=status.HTTP_404_NOT_FOUND)
        if act is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not getattr(act, "is_paid", False):
            return Response(
                {"detail": "Esta actividad no está configurada como actividad de pago."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = request.data or {}
        lead_id = data.get("lead_id")
        instance_id = data.get("instance_id")
        amount = data.get("amount")
        payment_method = (data.get("payment_method") or "efectivo").strip() or "efectivo"
        if not lead_id or not instance_id:
            return Response(
                {"detail": "lead_id e instance_id son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            inst = ErasmusActivityInstance.objects.get(id=instance_id, activity_id=act.id)
        except (ErasmusActivityInstance.DoesNotExist, ValueError, TypeError):
            return Response(
                {"detail": "Instancia no válida o no pertenece a esta actividad."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            lead = ErasmusLead.objects.get(id=lead_id)
        except (ErasmusLead.DoesNotExist, ValueError, TypeError):
            return Response(
                {"detail": "Lead no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if str(inst.id) not in (lead.interested_experiences or []):
            return Response(
                {"detail": "Esta persona no está inscrita en esta fecha/instancia."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount is None or amount == "":
            amount = act.price
        if amount is None:
            return Response(
                {"detail": "Indica el monto o configura un precio en la actividad."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            amount_decimal = Decimal(str(amount))
        except (ValueError, TypeError):
            return Response(
                {"detail": "Monto no válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount_decimal <= 0:
            return Response(
                {"detail": "El monto debe ser mayor que cero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        valid_methods = [c[0] for c in ErasmusActivityInscriptionPayment._meta.get_field("payment_method").choices]
        if payment_method not in valid_methods:
            payment_method = "other"
        payment, created = ErasmusActivityInscriptionPayment.objects.update_or_create(
            lead=lead,
            instance=inst,
            defaults={
                "amount": amount_decimal,
                "payment_method": payment_method,
                "paid_at": timezone.now(),
            },
        )
        return Response(
            {
                "id": payment.id,
                "lead_id": str(lead.id),
                "instance_id": str(inst.id),
                "amount": str(payment.amount),
                "payment_method": payment.payment_method,
                "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


def _get_activity_by_payment_token(token):
    """Resolve ErasmusActivityPaymentLink by token; return (link, error) or (None, None) if not found."""
    if not token or not isinstance(token, str) or not token.strip():
        return None, "missing"
    try:
        link = ErasmusActivityPaymentLink.objects.select_related(
            "lead", "instance", "instance__activity"
        ).get(token=token.strip())
    except ErasmusActivityPaymentLink.DoesNotExist:
        return None, "not_found"
    if link.expires_at and timezone.now() > link.expires_at:
        return None, "expired"
    if ErasmusActivityInscriptionPayment.objects.filter(lead=link.lead, instance=link.instance).exists():
        return None, "already_paid"
    return link, None


class ErasmusPublicViewGeneratePaymentLinkView(APIView):
    """POST /api/v1/erasmus/public/view/<view_token>/generate-payment-link/"""
    permission_classes = [AllowAny]

    def post(self, request, view_token):
        import secrets
        from apps.events.models import Order
        from django.conf import settings

        act, err = _get_activity_by_view_token(view_token)
        if err == "disabled":
            return Response({"detail": "Link desactivado."}, status=status.HTTP_404_NOT_FOUND)
        if act is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not getattr(act, "is_paid", False):
            return Response(
                {"detail": "Esta actividad no está configurada como actividad de pago."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = request.data or {}
        lead_id = data.get("lead_id")
        instance_id = data.get("instance_id")
        if not lead_id or not instance_id:
            return Response(
                {"detail": "lead_id e instance_id son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            inst = ErasmusActivityInstance.objects.get(id=instance_id, activity_id=act.id)
        except (ErasmusActivityInstance.DoesNotExist, ValueError, TypeError):
            return Response(
                {"detail": "Instancia no válida o no pertenece a esta actividad."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            lead = ErasmusLead.objects.get(id=lead_id)
        except (ErasmusLead.DoesNotExist, ValueError, TypeError):
            return Response(
                {"detail": "Lead no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if str(inst.id) not in (lead.interested_experiences or []):
            return Response(
                {"detail": "Esta persona no está inscrita en esta fecha/instancia."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if ErasmusActivityInscriptionPayment.objects.filter(lead=lead, instance=inst).exists():
            return Response(
                {"detail": "Esta inscripción ya está marcada como pagada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        amount = act.price
        if amount is None or amount <= 0:
            return Response(
                {"detail": "Configura un precio en la actividad para generar el link de pago."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = (lead.email or "").strip()
        if not email:
            return Response(
                {"detail": "Este inscrito no tiene email; añade uno para poder enviarle el link de pago."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        existing = ErasmusActivityPaymentLink.objects.filter(lead=lead, instance=inst).first()
        if existing:
            if existing.expires_at and timezone.now() > existing.expires_at:
                existing.delete()
                existing = None
            elif getattr(existing, "order", None) and existing.order.status == "paid":
                return Response(
                    {"detail": "Ya existe un pago para esta inscripción."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            elif getattr(existing, "order", None) and existing.order.status == "pending":
                order = existing.order
                frontend_url = (getattr(settings, "FRONTEND_URL", "http://localhost:8080") or "http://localhost:8080").rstrip("/")
                return Response({
                    "payment_link_url": f"{frontend_url}/checkout/erasmus-activity?token={existing.token}",
                    "order_id": str(order.id),
                    "amount": str(existing.amount),
                    "currency": existing.currency,
                    "expires_at": existing.expires_at.isoformat() if existing.expires_at else None,
                }, status=status.HTTP_200_OK)
        token_str = secrets.token_urlsafe(32)[:48]
        link = ErasmusActivityPaymentLink(
            lead=lead, instance=inst, amount=amount, currency="CLP", token=token_str,
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        link.save()
        phone = (lead.phone_country_code or "") + (lead.phone_number or "")
        order = Order.objects.create(
            user=None,
            email=email,
            first_name=(lead.first_name or "")[:100],
            last_name=(lead.last_name or "")[:100],
            phone=phone[:20] if phone else "",
            total=amount,
            subtotal=amount,
            service_fee=Decimal("0"),
            discount=Decimal("0"),
            taxes=Decimal("0"),
            order_kind="erasmus_activity",
            erasmus_activity_payment_link=link,
            status="pending",
        )
        frontend_url = (getattr(settings, "FRONTEND_URL", "http://localhost:8080") or "http://localhost:8080").rstrip("/")
        return Response({
            "payment_link_url": f"{frontend_url}/checkout/erasmus-activity?token={token_str}",
            "order_id": str(order.id),
            "amount": str(amount),
            "currency": link.currency,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        }, status=status.HTTP_201_CREATED)


class ErasmusPublicPaymentLinkByTokenView(APIView):
    """GET /api/v1/erasmus/public/payment-link/<token>/"""
    permission_classes = [AllowAny]

    def get(self, request, token):
        link, err = _get_activity_by_payment_token(token)
        if err:
            if err == "already_paid":
                return Response({"detail": "Esta inscripción ya fue pagada."}, status=status.HTTP_400_BAD_REQUEST)
            if err == "expired":
                return Response({"detail": "El link de pago ha expirado."}, status=status.HTTP_410_GONE)
            return Response({"detail": "Link no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        order = getattr(link, "order", None)
        if not order or order.status != "pending":
            return Response({"detail": "Orden no disponible o ya pagada."}, status=status.HTTP_404_NOT_FOUND)
        act = link.instance.activity
        instance_label = link.instance.scheduled_label_es or (
            link.instance.scheduled_date.isoformat() if link.instance.scheduled_date else str(link.instance.id)
        )
        return Response({
            "activity_title": act.title_es,
            "instance_label": instance_label,
            "amount": str(link.amount),
            "currency": link.currency,
            "order_id": str(order.id),
            "lead_name": f"{(link.lead.first_name or '').strip()} {(link.lead.last_name or '').strip()}".strip() or "Participante",
        })


class ErasmusPublicEditActivityView(APIView):
    """
    GET/PATCH /api/v1/erasmus/public/edit/<edit_token>/
    Same payload shape as superadmin activity detail/update. No auth.
    """
    permission_classes = [AllowAny]

    def get(self, request, edit_token):
        act, err = _get_activity_by_edit_token(edit_token)
        if err == "disabled":
            return Response({"detail": "Link desactivado."}, status=status.HTTP_404_NOT_FOUND)
        if act is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_activity_to_dict(act, include_instances=True))

    def patch(self, request, edit_token):
        act, err = _get_activity_by_edit_token(edit_token)
        if err == "disabled":
            return Response({"detail": "Link desactivado."}, status=status.HTTP_404_NOT_FOUND)
        if act is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data or {}
        if "title_es" in data:
            act.title_es = (data["title_es"] or "").strip()[:255]
        if "title_en" in data:
            act.title_en = (data["title_en"] or "").strip()[:255]
        if "slug" in data and data["slug"]:
            new_slug = (data["slug"] or "").strip()[:255]
            if new_slug != act.slug and ErasmusActivity.objects.filter(slug=new_slug).exists():
                return Response({"detail": "Slug already exists."}, status=status.HTTP_400_BAD_REQUEST)
            act.slug = new_slug
        if "description_es" in data:
            act.description_es = (data["description_es"] or "")[:10000]
        if "description_en" in data:
            act.description_en = (data["description_en"] or "")[:10000]
        if "short_description_es" in data:
            act.short_description_es = (data["short_description_es"] or "").strip()[:500]
        if "short_description_en" in data:
            act.short_description_en = (data["short_description_en"] or "").strip()[:500]
        if "location" in data:
            act.location = (data["location"] or "").strip()[:255]
        if "location_name" in data:
            act.location_name = (data["location_name"] or "").strip()[:255]
        if "location_address" in data:
            act.location_address = (data["location_address"] or "")[:5000]
        if "duration_minutes" in data:
            v = data["duration_minutes"]
            act.duration_minutes = int(v) if v is not None and v != "" else None
        if "included" in data:
            act.included = data["included"] if isinstance(data["included"], list) else []
        if "not_included" in data:
            act.not_included = data["not_included"] if isinstance(data["not_included"], list) else []
        if "itinerary" in data:
            raw = data["itinerary"] if isinstance(data["itinerary"], list) else []
            try:
                validate_itinerary_items(raw)
            except DRFValidationError as e:
                return Response({"detail": str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)
            act.itinerary = raw
        if "images" in data:
            act.images = _normalize_images(data["images"] if isinstance(data["images"], list) else [])
        if "display_order" in data:
            act.display_order = int(data["display_order"]) if data["display_order"] is not None else 0
        if "is_active" in data:
            act.is_active = bool(data["is_active"])
        if "detail_layout" in data:
            val = (data["detail_layout"] or "").strip()
            if val in ("default", "two_column"):
                act.detail_layout = val
        if "is_paid" in data:
            act.is_paid = bool(data["is_paid"])
        if "price" in data:
            v = data["price"]
            act.price = Decimal(str(v)) if v is not None and str(v).strip() != "" else None
        act.save()
        # Optional: sync instances (same as superadmin). If "instances" is present, create/update/delete to match.
        if "instances" in data and isinstance(data["instances"], list):
            from api.v1.superadmin.views.erasmus import _sync_activity_instances
            _sync_activity_instances(act, data["instances"])
        return Response(_activity_to_dict(act, include_instances=True))


class ErasmusPublicEditInstancesView(APIView):
    """GET/POST /api/v1/erasmus/public/edit/<edit_token>/instances/"""
    permission_classes = [AllowAny]

    def get(self, request, edit_token):
        act, err = _get_activity_by_edit_token(edit_token)
        if err == "disabled":
            return Response({"detail": "Link desactivado."}, status=status.HTTP_404_NOT_FOUND)
        if act is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        instances = []
        for inst in act.instances.order_by("display_order", "scheduled_date", "scheduled_year", "scheduled_month"):
            inscribed_count = ErasmusLead.objects.filter(
                interested_experiences__contains=[str(inst.id)]
            ).count()
            instances.append({
                "id": str(inst.id),
                "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                "scheduled_month": inst.scheduled_month,
                "scheduled_year": inst.scheduled_year,
                "scheduled_label_es": inst.scheduled_label_es or "",
                "scheduled_label_en": inst.scheduled_label_en or "",
                "start_time": _format_time(getattr(inst, "start_time", None)),
                "end_time": _format_time(getattr(inst, "end_time", None)),
                "display_order": inst.display_order,
                "is_active": inst.is_active,
                "capacity": getattr(inst, "capacity", None),
                "is_agotado": getattr(inst, "is_agotado", False),
                "interested_count_boost": getattr(inst, "interested_count_boost", 0) or 0,
                "inscribed_count": inscribed_count,
            })
        return Response({"results": instances})

    def post(self, request, edit_token):
        act, err = _get_activity_by_edit_token(edit_token)
        if err == "disabled":
            return Response({"detail": "Link desactivado."}, status=status.HTTP_404_NOT_FOUND)
        if act is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = JsonErasmusActivityInstanceSerializer(data=request.data or {})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        iv = serializer.validated_data
        inst = ErasmusActivityInstance(
            activity=act,
            scheduled_date=iv.get("scheduled_date"),
            scheduled_month=iv.get("scheduled_month"),
            scheduled_year=iv.get("scheduled_year"),
            scheduled_label_es=iv.get("scheduled_label_es", ""),
            scheduled_label_en=iv.get("scheduled_label_en", ""),
            start_time=_parse_time(iv.get("start_time")),
            end_time=_parse_time(iv.get("end_time")),
            display_order=iv.get("display_order", 0),
            is_active=iv.get("is_active", True),
            instructions_es=(iv.get("instructions_es") or "").strip(),
            instructions_en=(iv.get("instructions_en") or "").strip(),
            whatsapp_message_es=(iv.get("whatsapp_message_es") or "").strip(),
            whatsapp_message_en=(iv.get("whatsapp_message_en") or "").strip(),
            interested_count_boost=iv.get("interested_count_boost", 0) or 0,
        )
        try:
            inst.full_clean()
            inst.save()
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"id": str(inst.id), "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None},
            status=status.HTTP_201_CREATED,
        )


class ErasmusPublicEditInstanceDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/erasmus/public/edit/<edit_token>/instances/<instance_id>/"""
    permission_classes = [AllowAny]

    def _get_instance(self, edit_token, instance_id):
        act, err = _get_activity_by_edit_token(edit_token)
        if err == "disabled" or act is None:
            return None, None, Response(
                {"detail": "Link desactivado." if err == "disabled" else "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            inst = ErasmusActivityInstance.objects.get(id=instance_id, activity_id=act.id)
        except ErasmusActivityInstance.DoesNotExist:
            return None, None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return act, inst, None

    def get(self, request, edit_token, instance_id):
        act, inst, err_resp = self._get_instance(edit_token, instance_id)
        if err_resp is not None:
            return err_resp
        inscribed_count = ErasmusLead.objects.filter(
            interested_experiences__contains=[str(inst.id)]
        ).count()
        return Response({
            "id": str(inst.id),
            "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
            "scheduled_month": inst.scheduled_month,
            "scheduled_year": inst.scheduled_year,
            "scheduled_label_es": inst.scheduled_label_es or "",
            "scheduled_label_en": inst.scheduled_label_en or "",
            "start_time": _format_time(getattr(inst, "start_time", None)),
            "end_time": _format_time(getattr(inst, "end_time", None)),
            "display_order": inst.display_order,
            "is_active": inst.is_active,
            "capacity": getattr(inst, "capacity", None),
            "is_agotado": getattr(inst, "is_agotado", False),
            "interested_count_boost": getattr(inst, "interested_count_boost", 0) or 0,
            "inscribed_count": inscribed_count,
        })

    def patch(self, request, edit_token, instance_id):
        act, inst, err_resp = self._get_instance(edit_token, instance_id)
        if err_resp is not None:
            return err_resp
        data = request.data or {}
        if "scheduled_date" in data:
            val = data["scheduled_date"]
            if not val:
                inst.scheduled_date = None
            elif isinstance(val, str):
                try:
                    inst.scheduled_date = datetime.strptime(val[:10], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    inst.scheduled_date = None
            else:
                inst.scheduled_date = None
        if "scheduled_month" in data:
            inst.scheduled_month = data["scheduled_month"] if data["scheduled_month"] is not None else None
        if "scheduled_year" in data:
            inst.scheduled_year = data["scheduled_year"] if data["scheduled_year"] is not None else None
        if "scheduled_label_es" in data:
            inst.scheduled_label_es = (data["scheduled_label_es"] or "").strip()[:100]
        if "scheduled_label_en" in data:
            inst.scheduled_label_en = (data["scheduled_label_en"] or "").strip()[:100]
        if "start_time" in data:
            inst.start_time = _parse_time(data.get("start_time"))
        if "end_time" in data:
            inst.end_time = _parse_time(data.get("end_time"))
        if "display_order" in data:
            inst.display_order = int(data["display_order"]) if data["display_order"] is not None else 0
        if "is_active" in data:
            inst.is_active = bool(data["is_active"])
        if "capacity" in data:
            r = data["capacity"]
            inst.capacity = int(r) if r is not None and str(r).strip() != "" else None
        if "is_agotado" in data:
            inst.is_agotado = bool(data["is_agotado"])
        if "interested_count_boost" in data:
            raw = data["interested_count_boost"]
            inst.interested_count_boost = max(0, int(raw)) if raw is not None and str(raw).strip() != "" else 0
        try:
            inst.full_clean()
            inst.save()
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        inscribed_count = ErasmusLead.objects.filter(
            interested_experiences__contains=[str(inst.id)]
        ).count()
        return Response({
            "id": str(inst.id),
            "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
            "scheduled_month": inst.scheduled_month,
            "scheduled_year": inst.scheduled_year,
            "scheduled_label_es": inst.scheduled_label_es or "",
            "scheduled_label_en": inst.scheduled_label_en or "",
            "start_time": _format_time(getattr(inst, "start_time", None)),
            "end_time": _format_time(getattr(inst, "end_time", None)),
            "display_order": inst.display_order,
            "is_active": inst.is_active,
            "capacity": getattr(inst, "capacity", None),
            "is_agotado": getattr(inst, "is_agotado", False),
            "interested_count_boost": getattr(inst, "interested_count_boost", 0) or 0,
            "inscribed_count": inscribed_count,
        })

    def delete(self, request, edit_token, instance_id):
        act, inst, err_resp = self._get_instance(edit_token, instance_id)
        if err_resp is not None:
            return err_resp
        inst.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ErasmusPublicEditInstanceInscriptionsView(APIView):
    """GET /api/v1/erasmus/public/edit/<edit_token>/instances/<instance_id>/inscriptions/"""
    permission_classes = [AllowAny]

    def get(self, request, edit_token, instance_id):
        act, err = _get_activity_by_edit_token(edit_token)
        if err == "disabled":
            return Response({"detail": "Link desactivado."}, status=status.HTTP_404_NOT_FOUND)
        if act is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            inst = ErasmusActivityInstance.objects.get(id=instance_id, activity_id=act.id)
        except ErasmusActivityInstance.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        leads = ErasmusLead.objects.filter(
            interested_experiences__contains=[str(inst.id)]
        ).order_by("-updated_at")
        result = [
            {
                "id": str(lead.id),
                "first_name": lead.first_name or "",
                "last_name": lead.last_name or "",
                "email": lead.email or "",
                "phone_country_code": lead.phone_country_code or "",
                "phone_number": lead.phone_number or "",
                "instagram": lead.instagram or "",
                "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
            }
            for lead in leads
        ]
        return Response({"inscriptions": result, "count": len(result)})


class ErasmusPublicReviewFormView(APIView):
    """
    GET/POST /api/v1/erasmus/public/review/<review_token>/
    Public (no auth). Link is open for anyone you send it to.
    GET: returns activity title + list of instances (id, label) for the review form (instance selector).
    POST: create a review. Body: instance_id (required), author_name (required), author_origin (optional), rating (1-5), body (required).
    """
    permission_classes = [AllowAny]

    def get(self, request, review_token):
        act, err = _get_activity_by_review_token(review_token)
        if err == "disabled":
            return Response({"detail": "Link desactivado."}, status=status.HTTP_404_NOT_FOUND)
        if act is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        instances = []
        for inst in act.instances.filter(is_active=True).order_by(
            "display_order", "scheduled_date", "scheduled_year", "scheduled_month"
        ):
            instances.append({
                "id": str(inst.id),
                "label": _instance_label_for_review(inst),
                "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
            })
        return Response({
            "activity": {
                "id": str(act.id),
                "title_es": act.title_es,
                "title_en": act.title_en or act.title_es,
                "slug": act.slug,
            },
            "instances": instances,
        })

    def post(self, request, review_token):
        act, err = _get_activity_by_review_token(review_token)
        if err == "disabled":
            return Response({"detail": "Link desactivado."}, status=status.HTTP_404_NOT_FOUND)
        if act is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        instance_id = data.get("instance_id")
        if not instance_id:
            return Response(
                {"detail": "instance_id es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            inst = ErasmusActivityInstance.objects.get(id=instance_id, activity_id=act.id, is_active=True)
        except (ErasmusActivityInstance.DoesNotExist, ValueError, TypeError):
            return Response(
                {"detail": "Instancia no válida o no pertenece a esta actividad."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        author_name = (data.get("author_name") or "").strip()
        if not author_name:
            return Response(
                {"detail": "Tu nombre es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        author_name = author_name[:255]

        author_origin = (data.get("author_origin") or "").strip()[:255]

        try:
            rating = int(data.get("rating", 0))
        except (TypeError, ValueError):
            rating = 0
        if rating < 1 or rating > 5:
            return Response(
                {"detail": "La valoración debe ser entre 1 y 5."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body = (data.get("body") or "").strip()
        if not body:
            return Response(
                {"detail": "El comentario es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        body = body[:5000]

        review = ErasmusActivityReview(
            instance=inst,
            author_name=author_name,
            author_origin=author_origin,
            rating=rating,
            body=body,
        )
        try:
            review.full_clean()
            review.save()
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "id": review.id,
                "instance_id": str(inst.id),
                "created_at": review.created_at.isoformat() if review.created_at else None,
            },
            status=status.HTTP_201_CREATED,
        )
