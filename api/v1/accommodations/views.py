"""Vistas públicas de alojamientos (formato que espera el frontend)."""

import uuid
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q

from apps.accommodations.models import Accommodation
from apps.accommodations.services.pricing import (
    calculate_accommodation_pricing,
    AccommodationPricingError,
)
from apps.accommodations.serializers import (
    PublicAccommodationListSerializer,
    PublicAccommodationDetailSerializer,
    resolve_room_public_payload,
    _other_rooms_for_hotel,
    _other_units_for_hub,
)


class PublicAccommodationListView(APIView):
    """
    GET /api/v1/accommodations/public/
    Lista alojamientos publicados. Formato compatible con el tipo Accommodation del frontend.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        qs = Accommodation.objects.filter(
            status="published",
            deleted_at__isnull=True,
        )
        country = request.query_params.get("country", "").strip()
        city = request.query_params.get("city", "").strip()
        search = request.query_params.get("search", "").strip()
        if country:
            qs = qs.filter(country__icontains=country)
        if city:
            qs = qs.filter(city__icontains=city)
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(location_name__icontains=search)
                | Q(city__icontains=search)
            )
        qs = qs.order_by("-rating_avg", "-created_at")
        serializer = PublicAccommodationListSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


class PublicAccommodationDetailView(APIView):
    """
    GET /api/v1/accommodations/public/<slug_or_id>/
    Detalle por slug o UUID. Incluye reviews (reviewsList).
    Los alojamientos en borrador (draft) no aparecen en el listado público pero
    son accesibles por enlace directo (comportamiento "no listado").
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug_or_id):
        # Listado: solo published. Detalle: published o draft (unlisted = accesible por link).
        qs = Accommodation.objects.filter(
            status__in=("published", "draft"),
            deleted_at__isnull=True,
        )
        acc = None
        try:
            acc = qs.get(slug=slug_or_id)
        except Accommodation.DoesNotExist:
            try:
                uid = uuid.UUID(str(slug_or_id))
                acc = qs.get(id=uid)
            except (ValueError, TypeError, Accommodation.DoesNotExist):
                pass
        if not acc:
            return Response(
                {"error": "Alojamiento no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )
        # When room belongs to a hotel, apply inheritance (location, amenities) in public payload
        if acc.hotel_id:
            data = resolve_room_public_payload(acc, request, include_photo_tour=True)
            reviews_qs = acc.reviews.all()[:50]
            data["reviewsList"] = [
                {
                    "id": r.id,
                    "author_name": r.author_name,
                    "author_location": r.author_location or "",
                    "rating": r.rating,
                    "text": r.text,
                    "review_date": r.review_date.isoformat() if r.review_date else None,
                    "stay_type": r.stay_type or "",
                    "host_reply": r.host_reply or "",
                }
                for r in reviews_qs
            ]
            data["short_description"] = acc.short_description or ""
            data["not_amenities"] = list(acc.not_amenities or [])
            data["hotel"] = {
                "slug": acc.hotel.slug,
                "name": acc.hotel.name,
            }
            data["other_rooms"] = _other_rooms_for_hotel(
                acc.hotel_id, acc.id, request, limit=12
            )
            if acc.rental_hub_id:
                data["rental_hub"] = {
                    "slug": acc.rental_hub.slug,
                    "name": acc.rental_hub.name,
                }
                data["other_units"] = _other_units_for_hub(
                    acc.rental_hub_id, acc.id, request, limit=12
                )
            return Response(data)
        # Default path: use serializer, then add rental_hub when applicable
        serializer = PublicAccommodationDetailSerializer(acc, context={"request": request})
        data = serializer.data
        if acc.rental_hub_id:
            data["rental_hub"] = {
                "slug": acc.rental_hub.slug,
                "name": acc.rental_hub.name,
            }
            data["other_units"] = _other_units_for_hub(
                acc.rental_hub_id, acc.id, request, limit=12
            )
        return Response(data)


def _parse_extras_query(extras_param):
    """
    Parse query param extras into selected_options.
    Convention: extras=code1:qty1,code2:qty2 (e.g. extras=linens:2,towels:1).
    Returns list of {"code": str, "quantity": int}. Invalid pairs are skipped only if
    we want to be lenient; per plan we validate strictly in the service, so we just
    parse here and let the service raise 400 for invalid codes/quantities.
    """
    if not extras_param or not extras_param.strip():
        return []
    selected = []
    for part in extras_param.strip().split(","):
        part = part.strip()
        if ":" in part:
            code, _, qty_str = part.partition(":")
            code = code.strip()
            qty_str = qty_str.strip()
            if code:
                try:
                    qty = int(qty_str) if qty_str else 1
                    if qty >= 1:
                        selected.append({"code": code, "quantity": qty})
                except ValueError:
                    pass  # service will not receive this malformed entry if we skip; or we could raise
        elif part:
            selected.append({"code": part, "quantity": 1})
    return selected


class PublicAccommodationPricingPreviewView(APIView):
    """
    GET /api/v1/accommodations/public/<slug_or_id>/pricing-preview/
    Query params: check_in (YYYY-MM-DD), check_out (YYYY-MM-DD), guests (int), extras (code:qty,code:qty).
    Returns pricing_snapshot shape (base, extras, total). Stateless; no quote persisted.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug_or_id):
        qs = Accommodation.objects.filter(
            status__in=("published", "draft"),
            deleted_at__isnull=True,
        )
        acc = None
        try:
            acc = qs.get(slug=slug_or_id)
        except Accommodation.DoesNotExist:
            try:
                uid = uuid.UUID(str(slug_or_id))
                acc = qs.get(id=uid)
            except (ValueError, TypeError, Accommodation.DoesNotExist):
                pass
        if not acc:
            return Response(
                {"error": "Alojamiento no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )

        check_in = request.query_params.get("check_in", "").strip()
        check_out = request.query_params.get("check_out", "").strip()
        guests_param = request.query_params.get("guests", "").strip()
        extras_param = request.query_params.get("extras", "").strip()

        if not check_in or not check_out:
            return Response(
                {"error": "check_in and check_out are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            guests = int(guests_param) if guests_param else 1
        except ValueError:
            guests = 1
        if guests < 1:
            guests = 1

        selected_options = _parse_extras_query(extras_param)

        try:
            snapshot = calculate_accommodation_pricing(
                accommodation_id=acc.id,
                check_in=check_in,
                check_out=check_out,
                guests=guests,
                selected_options=selected_options,
            )
        except AccommodationPricingError as e:
            return Response(
                {"error": getattr(e, "message", str(e))},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(snapshot)
