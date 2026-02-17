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
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug_or_id):
        qs = Accommodation.objects.filter(status="published", deleted_at__isnull=True)
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
        serializer = PublicAccommodationDetailSerializer(acc, context={"request": request})
        return Response(serializer.data)
