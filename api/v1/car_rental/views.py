"""Public API for car rental (list and detail with availability)."""

import uuid
from datetime import datetime
from decimal import Decimal

from django.db.models import Exists, OuterRef, Q
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.car_rental.models import Car, CarBlockedDate, CarReservation
from apps.car_rental.serializers import PublicCarListSerializer, PublicCarDetailSerializer
from apps.landing_destinations.models import LandingDestination
from apps.whatsapp.services.reservation_code_generator import ReservationCodeGenerator
from apps.whatsapp.services.reservation_handler import ReservationHandler


def _parse_date(s):
    """Parse YYYY-MM-DD or return None."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


class PublicCarListView(APIView):
    """
    GET /api/v1/car-rental/public/
    List published cars. Query params: destination (slug), pickup_date, return_date (for availability).
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        qs = Car.objects.filter(
            status="published",
            deleted_at__isnull=True,
        ).select_related("company")

        destination_slug = request.query_params.get("destination", "").strip()
        if destination_slug:
            dest = LandingDestination.objects.filter(
                slug=destination_slug, is_active=True
            ).first()
            if dest:
                car_ids = getattr(dest, "car_rental_ids", None) or []
                if car_ids:
                    qs = qs.filter(id__in=[str(cid) for cid in car_ids])
            else:
                qs = qs.none()

        pickup_date = _parse_date(request.query_params.get("pickup_date"))
        return_date = _parse_date(request.query_params.get("return_date"))

        if pickup_date and return_date and return_date >= pickup_date:
            blocked_subq = CarBlockedDate.objects.filter(
                car_id=OuterRef("id"),
                date__gte=pickup_date,
                date__lte=return_date,
            )
            qs = qs.exclude(Exists(blocked_subq))
            overlapping = CarReservation.objects.filter(
                car_id=OuterRef("id"),
                status__in=("pending", "paid"),
            ).filter(
                pickup_date__lte=return_date,
                return_date__gte=pickup_date,
            )
            qs = qs.exclude(Exists(overlapping))

        qs = qs.order_by("company__name", "title")
        serializer = PublicCarListSerializer(
            qs, many=True, context={"request": request}
        )
        data = serializer.data
        for i, car in enumerate(qs):
            if i < len(data):
                data[i]["image"] = data[i]["images"][0] if data[i].get("images") else ""
        return Response(data)


class PublicCarDetailView(APIView):
    """
    GET /api/v1/car-rental/public/<slug_or_id>/
    Detail by slug or UUID.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug_or_id):
        qs = Car.objects.filter(
            status="published",
            deleted_at__isnull=True,
        ).select_related("company")

        car = None
        try:
            car = qs.get(slug=slug_or_id)
        except Car.DoesNotExist:
            try:
                uid = uuid.UUID(str(slug_or_id))
                car = qs.get(id=uid)
            except (ValueError, TypeError, Car.DoesNotExist):
                pass

        if not car:
            return Response(
                {"error": "Auto no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PublicCarDetailSerializer(car, context={"request": request})
        data = serializer.data
        data["image"] = data["images"][0] if data.get("images") else ""
        return Response(data)


class GenerateWhatsAppCodeView(APIView):
    """
    POST /api/v1/car-rental/public/<slug_or_id>/generate-whatsapp-code/
    Body: { pickup_date, return_date, pickup_time?, return_time?, customer: { name, email?, phone? } }
    Returns: { code, expires_at, message_for_whatsapp }
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, slug_or_id):
        qs = Car.objects.filter(
            status="published",
            deleted_at__isnull=True,
        ).select_related("company")

        car = None
        try:
            car = qs.get(slug=slug_or_id)
        except Car.DoesNotExist:
            try:
                uid = uuid.UUID(str(slug_or_id))
                car = qs.get(id=uid)
            except (ValueError, TypeError, Car.DoesNotExist):
                pass

        if not car:
            return Response(
                {"error": "Auto no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )

        pickup_date = request.data.get("pickup_date")
        return_date = request.data.get("return_date")
        pickup_time = (request.data.get("pickup_time") or car.pickup_time_default or "")[:5]
        return_time = (request.data.get("return_time") or car.return_time_default or "")[:5]
        customer = request.data.get("customer") or {}
        if not pickup_date or not return_date:
            return Response(
                {"error": "pickup_date y return_date son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            pdate = _parse_date(pickup_date)
            rdate = _parse_date(return_date)
        except Exception:
            pdate = rdate = None
        if not pdate or not rdate or rdate < pdate:
            return Response(
                {"error": "Fechas inválidas o return_date debe ser >= pickup_date."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        days = (rdate - pdate).days or 1
        price_per_day = car.price_per_day or Decimal("0")
        total = float(price_per_day * days)
        currency = getattr(car, "currency", "CLP")

        checkout_data = {
            "pickup_date": pickup_date if isinstance(pickup_date, str) else pdate.isoformat(),
            "return_date": return_date if isinstance(return_date, str) else rdate.isoformat(),
            "pickup_time": pickup_time,
            "return_time": return_time,
            "pricing": {"total": total, "currency": currency},
            "customer": {
                "name": customer.get("name", ""),
                "email": customer.get("email", ""),
                "phone": customer.get("phone", ""),
            },
        }

        try:
            code_obj = ReservationCodeGenerator.generate_code_for_car(str(car.id), checkout_data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Error generating car reservation code: %s", e)
            return Response({"error": "Error al generar el código."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        ReservationHandler.start_flow_for_code(code_obj)

        message_for_whatsapp = f"Hola, quiero reservar el auto {car.title}. Mi código de reserva: {code_obj.code}"
        return Response(
            {
                "code": code_obj.code,
                "expires_at": code_obj.expires_at.isoformat(),
                "code_id": str(code_obj.id),
                "message_for_whatsapp": message_for_whatsapp,
            },
            status=status.HTTP_201_CREATED,
        )
