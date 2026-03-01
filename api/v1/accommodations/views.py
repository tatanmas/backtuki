"""Vistas públicas de alojamientos (formato que espera el frontend)."""

import uuid
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q

from apps.accommodations.models import Accommodation
from apps.accommodations.serializers import (
    PublicAccommodationListSerializer,
    PublicAccommodationDetailSerializer,
    resolve_room_public_payload,
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
            return Response(data)
        serializer = PublicAccommodationDetailSerializer(acc, context={"request": request})
        return Response(serializer.data)
