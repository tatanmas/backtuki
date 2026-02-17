"""Superadmin views for Erasmus: leads, tracking links, extra fields (dynamic form questions)."""

import csv
import json
from django.db import models
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.superadmin.permissions import IsSuperUser
from apps.erasmus.models import ErasmusLead, ErasmusTrackingLink, ErasmusExtraField, ErasmusDestinationGuide


class ErasmusLeadsView(APIView):
    """GET /api/v1/superadmin/erasmus/leads/ – list with filters. Export via ?format=csv."""
    permission_classes = [IsSuperUser]

    def get(self, request):
        qs = ErasmusLead.objects.all().order_by("-created_at")
        # Filters
        source = request.query_params.get("source_slug")
        if source is not None:
            qs = qs.filter(source_slug=source)
        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                models.Q(first_name__icontains=search)
                | models.Q(last_name__icontains=search)
                | models.Q(email__icontains=search)
                | models.Q(instagram__icontains=search)
                | models.Q(university__icontains=search)
                | models.Q(stay_reason_detail__icontains=search)
                | models.Q(country__icontains=search)
            )

        if request.query_params.get("format") == "csv":
            return self._export_csv(qs)

        # Pagination-friendly list
        page = int(request.query_params.get("page", 1))
        page_size = min(int(request.query_params.get("page_size", 50)), 200)
        start = (page - 1) * page_size
        end = start + page_size
        leads = qs[start:end]
        data = []
        for lead in leads:
            data.append({
                "id": str(lead.id),
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "nickname": lead.nickname or "",
                "birth_date": str(lead.birth_date),
                "country": lead.country or "",
                "email": lead.email or "",
                "phone_country_code": lead.phone_country_code,
                "phone_number": lead.phone_number,
                "instagram": lead.instagram or "",
                "stay_reason": lead.stay_reason,
                "stay_reason_detail": lead.stay_reason_detail or "",
                "university": lead.university or "",
                "degree": lead.degree or "",
                "arrival_date": str(lead.arrival_date),
                "departure_date": str(lead.departure_date),
                "destinations": lead.destinations,
                "interests": lead.interests,
                "source_slug": lead.source_slug or "",
                "utm_source": lead.utm_source or "",
                "utm_medium": lead.utm_medium or "",
                "utm_campaign": lead.utm_campaign or "",
                "extra_data": lead.extra_data,
                "created_at": lead.created_at.isoformat() if lead.created_at else "",
            })
        return Response({"results": data, "count": qs.count()})


    def _export_csv(self, qs):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="erasmus-leads.csv"'
        writer = csv.writer(response)
        # Header
        writer.writerow([
            "id", "first_name", "last_name", "nickname", "birth_date", "country", "email",
            "phone_country_code", "phone_number", "instagram",
            "stay_reason", "stay_reason_detail", "university", "degree",
            "arrival_date", "departure_date", "destinations", "interests",
            "source_slug", "utm_source", "utm_medium", "utm_campaign", "extra_data", "created_at"
        ])
        for lead in qs:
            writer.writerow([
                lead.id, lead.first_name, lead.last_name, lead.nickname or "", lead.birth_date,
                lead.country or "", lead.email or "", lead.phone_country_code, lead.phone_number,
                lead.instagram or "",
                lead.stay_reason, lead.stay_reason_detail or "", lead.university or "", lead.degree or "",
                lead.arrival_date, lead.departure_date,
                json.dumps(lead.destinations, ensure_ascii=False),
                json.dumps(lead.interests, ensure_ascii=False),
                lead.source_slug or "", lead.utm_source or "", lead.utm_medium or "", lead.utm_campaign or "",
                json.dumps(lead.extra_data, ensure_ascii=False),
                lead.created_at.isoformat() if lead.created_at else "",
            ])
        return response


class ErasmusTrackingLinkViewSet(viewsets.ModelViewSet):
    """CRUD for tracking links: /api/v1/superadmin/erasmus/tracking-links/"""
    permission_classes = [IsSuperUser]
    queryset = ErasmusTrackingLink.objects.all()
    serializer_class = None  # use simple dict

    def list(self, request, *args, **kwargs):
        items = list(self.get_queryset().values("id", "name", "slug"))
        return Response(items)

    def create(self, request, *args, **kwargs):
        name = request.data.get("name", "").strip()
        slug = request.data.get("slug", "").strip().lower().replace(" ", "_")
        if not name or not slug:
            return Response({"detail": "name and slug required"}, status=status.HTTP_400_BAD_REQUEST)
        if ErasmusTrackingLink.objects.filter(slug=slug).exists():
            return Response({"detail": "slug already exists"}, status=status.HTTP_400_BAD_REQUEST)
        obj = ErasmusTrackingLink.objects.create(name=name, slug=slug)
        return Response({"id": obj.id, "name": obj.name, "slug": obj.slug}, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        return Response({"id": obj.id, "name": obj.name, "slug": obj.slug})

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        if "name" in request.data:
            obj.name = request.data["name"].strip()
        if "slug" in request.data:
            obj.slug = request.data["slug"].strip().lower().replace(" ", "_")
        obj.save()
        return Response({"id": obj.id, "name": obj.name, "slug": obj.slug})

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class ErasmusDestinationGuideViewSet(viewsets.ModelViewSet):
    """CRUD for destination guides: /api/v1/superadmin/erasmus/destination-guides/"""
    permission_classes = [IsSuperUser]
    queryset = ErasmusDestinationGuide.objects.all().order_by("destination_slug", "order", "id")

    def list(self, request, *args, **kwargs):
        items = list(
            self.get_queryset().values(
                "id", "destination_slug", "title", "description", "file_url", "order", "is_active"
            )
        )
        return Response(items)

    def create(self, request, *args, **kwargs):
        data = request.data
        destination_slug = (data.get("destination_slug") or "").strip().lower().replace(" ", "-")
        if not destination_slug:
            return Response({"detail": "destination_slug required"}, status=status.HTTP_400_BAD_REQUEST)
        obj = ErasmusDestinationGuide.objects.create(
            destination_slug=destination_slug,
            title=(data.get("title") or "").strip() or destination_slug,
            description=(data.get("description") or "").strip(),
            file_url=(data.get("file_url") or "").strip(),
            order=int(data.get("order", 0)),
            is_active=bool(data.get("is_active", True)),
        )
        return Response(
            {"id": obj.id, "destination_slug": obj.destination_slug, "title": obj.title,
             "description": obj.description, "file_url": obj.file_url, "order": obj.order, "is_active": obj.is_active},
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        return Response({
            "id": obj.id, "destination_slug": obj.destination_slug, "title": obj.title,
            "description": obj.description, "file_url": obj.file_url, "order": obj.order, "is_active": obj.is_active,
        })

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        for key in ("destination_slug", "title", "description", "file_url", "order", "is_active"):
            if key in request.data:
                if key == "destination_slug":
                    obj.destination_slug = (request.data[key] or "").strip().lower().replace(" ", "-")
                elif key == "order":
                    obj.order = int(request.data[key])
                elif key == "is_active":
                    obj.is_active = bool(request.data[key])
                else:
                    setattr(obj, key, (request.data[key] or "").strip() if key in ("title", "description", "file_url") else request.data[key])
        obj.save()
        return Response({
            "id": obj.id, "destination_slug": obj.destination_slug, "title": obj.title,
            "description": obj.description, "file_url": obj.file_url, "order": obj.order, "is_active": obj.is_active,
        })

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class ErasmusExtraFieldViewSet(viewsets.ModelViewSet):
    """CRUD for dynamic form questions: /api/v1/superadmin/erasmus/extra-fields/"""
    permission_classes = [IsSuperUser]
    queryset = ErasmusExtraField.objects.all().order_by("order", "id")

    def list(self, request, *args, **kwargs):
        items = list(
            self.get_queryset().values(
                "id", "field_key", "label", "type", "required", "placeholder", "help_text", "order", "is_active", "options"
            )
        )
        return Response(items)

    def create(self, request, *args, **kwargs):
        data = request.data
        field_key = (data.get("field_key") or "").strip().lower().replace(" ", "_")
        if not field_key:
            return Response({"detail": "field_key required"}, status=status.HTTP_400_BAD_REQUEST)
        if ErasmusExtraField.objects.filter(field_key=field_key).exists():
            return Response({"detail": "field_key already exists"}, status=status.HTTP_400_BAD_REQUEST)
        obj = ErasmusExtraField.objects.create(
            label=data.get("label", field_key),
            field_key=field_key,
            type=data.get("type", "text"),
            required=bool(data.get("required", False)),
            placeholder=(data.get("placeholder") or "")[:255],
            help_text=data.get("help_text") or "",
            order=int(data.get("order", 0)),
            is_active=bool(data.get("is_active", True)),
            options=data.get("options") or [],
        )
        return Response(
            {"id": obj.id, "field_key": obj.field_key, "label": obj.label, "type": obj.type,
             "required": obj.required, "placeholder": obj.placeholder, "help_text": obj.help_text,
             "order": obj.order, "is_active": obj.is_active, "options": obj.options},
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        return Response({
            "id": obj.id, "field_key": obj.field_key, "label": obj.label, "type": obj.type,
            "required": obj.required, "placeholder": obj.placeholder, "help_text": obj.help_text,
            "order": obj.order, "is_active": obj.is_active, "options": obj.options,
        })

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        for key in ("label", "type", "required", "placeholder", "help_text", "order", "is_active", "options"):
            if key in request.data:
                setattr(obj, key, request.data[key] if key != "order" else int(request.data[key]))
        if "field_key" in request.data and request.data["field_key"]:
            obj.field_key = request.data["field_key"].strip().lower().replace(" ", "_")
        obj.save()
        return Response({
            "id": obj.id, "field_key": obj.field_key, "label": obj.label, "type": obj.type,
            "required": obj.required, "placeholder": obj.placeholder, "help_text": obj.help_text,
            "order": obj.order, "is_active": obj.is_active, "options": obj.options,
        })

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
