"""
SuperAdmin: CRUD contests (sorteos), slides, extra-fields, participants list and CSV export.
"""
import csv
import logging
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.erasmus.models import (
    Contest,
    ContestSlideConfig,
    ContestExtraField,
    ContestRegistration,
)
from apps.media.models import MediaAsset, MediaUsage
from apps.experiences.models import Experience

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)


def _sync_media_usage_contest_slide(config: ContestSlideConfig, new_asset: MediaAsset | None):
    """Update MediaUsage for contest slide so library shows usage."""
    config_ct = ContentType.objects.get_for_model(ContestSlideConfig)
    MediaUsage.objects.filter(
        content_type=config_ct,
        object_id=config.id,
        deleted_at__isnull=True,
    ).update(deleted_at=timezone.now())
    if new_asset:
        MediaUsage.objects.create(
            asset=new_asset,
            content_type=config_ct,
            object_id=config.id,
            field_name="contest_slide",
        )


class ContestListView(APIView):
    """GET /api/v1/superadmin/contests/ – list all contests."""
    permission_classes = [IsSuperUser]

    def get(self, request):
        qs = Contest.objects.all().order_by("order", "slug")
        items = []
        for c in qs:
            items.append({
                "id": str(c.id),
                "slug": c.slug,
                "title": c.title,
                "subtitle": c.subtitle,
                "headline": (c.headline or "")[:200],
                "experience_id": str(c.experience_id) if c.experience_id else None,
                "is_active": c.is_active,
                "starts_at": c.starts_at.isoformat() if c.starts_at else None,
                "ends_at": c.ends_at.isoformat() if c.ends_at else None,
                "order": c.order,
                "registrations_count": c.registrations.count(),
            })
        return Response(items)


class ContestDetailView(APIView):
    """GET /api/v1/superadmin/contests/<id>/ – retrieve. PUT/PATCH – update. DELETE – delete."""
    permission_classes = [IsSuperUser]

    def get(self, request, pk):
        try:
            c = Contest.objects.select_related("experience").get(pk=pk)
        except Contest.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "id": str(c.id),
            "slug": c.slug,
            "title": c.title,
            "subtitle": c.subtitle,
            "headline": c.headline,
            "experience_id": str(c.experience_id) if c.experience_id else None,
            "terms_and_conditions_html": c.terms_and_conditions_html,
            "requirements_html": c.requirements_html,
            "whatsapp_confirmation_message": c.whatsapp_confirmation_message,
            "is_active": c.is_active,
            "starts_at": c.starts_at.isoformat() if c.starts_at else None,
            "ends_at": c.ends_at.isoformat() if c.ends_at else None,
            "order": c.order,
        })

    def put(self, request, pk):
        return self._update(request, pk, partial=False)

    def patch(self, request, pk):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, partial):
        try:
            c = Contest.objects.get(pk=pk)
        except Contest.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data
        if "slug" in data:
            c.slug = (data["slug"] or "").strip() or c.slug
        if "title" in data:
            c.title = (data["title"] or "").strip() or c.title
        if "subtitle" in data:
            c.subtitle = (data["subtitle"] or "").strip()
        if "headline" in data:
            c.headline = (data["headline"] or "").strip()
        if "experience_id" in data:
            if data["experience_id"]:
                try:
                    c.experience = Experience.objects.get(pk=data["experience_id"])
                except Experience.DoesNotExist:
                    pass
            else:
                c.experience = None
        if "terms_and_conditions_html" in data:
            c.terms_and_conditions_html = data["terms_and_conditions_html"] or ""
        if "requirements_html" in data:
            c.requirements_html = data["requirements_html"] or ""
        if "whatsapp_confirmation_message" in data:
            c.whatsapp_confirmation_message = data["whatsapp_confirmation_message"] or ""
        if "is_active" in data:
            c.is_active = bool(data["is_active"])
        if "starts_at" in data:
            from django.utils.dateparse import parse_datetime
            c.starts_at = parse_datetime(data["starts_at"]) if data["starts_at"] else None
        if "ends_at" in data:
            from django.utils.dateparse import parse_datetime
            c.ends_at = parse_datetime(data["ends_at"]) if data["ends_at"] else None
        if "order" in data:
            c.order = int(data["order"]) if data["order"] is not None else 0
        c.save()
        return Response({"id": str(c.id), "slug": c.slug})

    def delete(self, request, pk):
        try:
            c = Contest.objects.get(pk=pk)
        except Contest.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        c.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContestCreateView(APIView):
    """POST /api/v1/superadmin/contests/ – create contest."""
    permission_classes = [IsSuperUser]

    def post(self, request):
        data = request.data
        slug = (data.get("slug") or "").strip()
        title = (data.get("title") or "").strip()
        if not title:
            return Response({"detail": "title is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not slug:
            slug = title.lower().replace(" ", "-")[:80]
        if Contest.objects.filter(slug=slug).exists():
            return Response({"detail": "A contest with this slug already exists."}, status=status.HTTP_400_BAD_REQUEST)
        c = Contest.objects.create(
            slug=slug,
            title=title,
            subtitle=(data.get("subtitle") or "").strip(),
            headline=(data.get("headline") or "").strip(),
            terms_and_conditions_html=data.get("terms_and_conditions_html") or "",
            requirements_html=data.get("requirements_html") or "",
            whatsapp_confirmation_message=data.get("whatsapp_confirmation_message") or "",
            is_active=bool(data.get("is_active", True)),
            order=int(data.get("order", 0)),
        )
        if data.get("experience_id"):
            try:
                c.experience = Experience.objects.get(pk=data["experience_id"])
                c.save()
            except Experience.DoesNotExist:
                pass
        return Response({"id": str(c.id), "slug": c.slug}, status=status.HTTP_201_CREATED)


# Contest slides
class ContestSlidesView(APIView):
    """GET /api/v1/superadmin/contests/<contest_id>/slides/ – list. POST – create slot."""
    permission_classes = [IsSuperUser]

    def get(self, request, contest_id):
        try:
            contest = Contest.objects.get(pk=contest_id)
        except Contest.DoesNotExist:
            return Response({"detail": "Contest not found."}, status=status.HTTP_404_NOT_FOUND)
        configs = ContestSlideConfig.objects.filter(contest=contest).select_related("asset").order_by("order", "id")
        result = []
        for cfg in configs:
            asset_url = getattr(cfg.asset, "url", None) if cfg.asset and not getattr(cfg.asset, "deleted_at", None) else None
            result.append({
                "id": str(cfg.id),
                "asset_id": str(cfg.asset_id) if cfg.asset_id else None,
                "asset_url": asset_url,
                "asset_filename": getattr(cfg.asset, "original_filename", None) if cfg.asset else None,
                "caption": cfg.caption or "",
                "order": cfg.order,
            })
        return Response(result)

    def post(self, request, contest_id):
        try:
            contest = Contest.objects.get(pk=contest_id)
        except Contest.DoesNotExist:
            return Response({"detail": "Contest not found."}, status=status.HTTP_404_NOT_FOUND)
        max_order = ContestSlideConfig.objects.filter(contest=contest).aggregate(m=models.Max("order"))
        next_order = (max_order.get("m") or -1) + 1
        cfg = ContestSlideConfig.objects.create(contest=contest, order=next_order)
        return Response({
            "id": str(cfg.id),
            "asset_id": None,
            "asset_url": None,
            "asset_filename": None,
            "caption": "",
            "order": cfg.order,
        }, status=status.HTTP_201_CREATED)


class ContestSlideAssignView(APIView):
    """PUT /api/v1/superadmin/contests/<contest_id>/slides/assign/ – body: { slide_id, asset_id, caption? }."""
    permission_classes = [IsSuperUser]

    def put(self, request, contest_id):
        try:
            contest = Contest.objects.get(pk=contest_id)
        except Contest.DoesNotExist:
            return Response({"detail": "Contest not found."}, status=status.HTTP_404_NOT_FOUND)
        slide_id = request.data.get("slide_id")
        asset_id = request.data.get("asset_id")
        caption = (request.data.get("caption") or "").strip()
        if not slide_id:
            return Response({"detail": "slide_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            cfg = ContestSlideConfig.objects.get(id=slide_id, contest=contest)
        except ContestSlideConfig.DoesNotExist:
            return Response({"detail": "Slide not found."}, status=status.HTTP_404_NOT_FOUND)
        new_asset = None
        if asset_id:
            try:
                new_asset = MediaAsset.objects.get(pk=asset_id)
            except MediaAsset.DoesNotExist:
                return Response({"detail": "Asset not found."}, status=status.HTTP_404_NOT_FOUND)
        cfg.asset = new_asset
        cfg.caption = caption[:255] if caption else ""
        cfg.save()
        _sync_media_usage_contest_slide(cfg, new_asset)
        return Response({"slide_id": str(cfg.id), "asset_id": str(cfg.asset_id) if cfg.asset_id else None})


class ContestSlideDeleteView(APIView):
    """DELETE /api/v1/superadmin/contests/<contest_id>/slides/<slide_id>/."""
    permission_classes = [IsSuperUser]

    def delete(self, request, contest_id, slide_id):
        try:
            contest = Contest.objects.get(pk=contest_id)
        except Contest.DoesNotExist:
            return Response({"detail": "Contest not found."}, status=status.HTTP_404_NOT_FOUND)
        deleted, _ = ContestSlideConfig.objects.filter(id=slide_id, contest=contest).delete()
        if not deleted:
            return Response({"detail": "Slide not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContestSlidesReorderView(APIView):
    """POST /api/v1/superadmin/contests/<contest_id>/slides/reorder/ – body: { order: [slide_id, ...] }."""
    permission_classes = [IsSuperUser]

    def post(self, request, contest_id):
        try:
            contest = Contest.objects.get(pk=contest_id)
        except Contest.DoesNotExist:
            return Response({"detail": "Contest not found."}, status=status.HTTP_404_NOT_FOUND)
        order_ids = request.data.get("order") or []
        for i, sid in enumerate(order_ids):
            ContestSlideConfig.objects.filter(id=sid, contest=contest).update(order=i)
        configs = ContestSlideConfig.objects.filter(contest=contest).order_by("order", "id")
        result = [{"id": str(c.id), "order": c.order} for c in configs]
        return Response(result)


# Contest extra fields
class ContestExtraFieldViewSet(ModelViewSet):
    """CRUD contest extra fields: /api/v1/superadmin/contests/<contest_id>/extra-fields/."""
    permission_classes = [IsSuperUser]
    queryset = ContestExtraField.objects.all()

    def get_queryset(self):
        return ContestExtraField.objects.filter(contest_id=self.kwargs["contest_id"]).order_by("order", "id")

    def list(self, request, contest_id=None):
        qs = self.get_queryset()
        items = list(qs.values("id", "field_key", "label", "type", "required", "placeholder", "help_text", "order", "is_active", "options"))
        return Response(items)

    def create(self, request, contest_id=None):
        try:
            contest = Contest.objects.get(pk=contest_id)
        except Contest.DoesNotExist:
            return Response({"detail": "Contest not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data
        field_key = (data.get("field_key") or "").strip().lower().replace(" ", "_")
        if not field_key:
            return Response({"detail": "field_key is required."}, status=status.HTTP_400_BAD_REQUEST)
        if ContestExtraField.objects.filter(contest=contest, field_key=field_key).exists():
            return Response({"detail": "field_key already exists for this contest."}, status=status.HTTP_400_BAD_REQUEST)
        obj = ContestExtraField.objects.create(
            contest=contest,
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
            {"id": obj.id, "field_key": obj.field_key, "label": obj.label, "type": obj.type, "required": obj.required,
             "placeholder": obj.placeholder, "help_text": obj.help_text, "order": obj.order, "is_active": obj.is_active, "options": obj.options},
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, contest_id=None, pk=None):
        obj = self.get_queryset().filter(pk=pk).first()
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"id": obj.id, "field_key": obj.field_key, "label": obj.label, "type": obj.type, "required": obj.required,
                        "placeholder": obj.placeholder, "help_text": obj.help_text, "order": obj.order, "is_active": obj.is_active, "options": obj.options})

    def update(self, request, contest_id=None, pk=None):
        return self._update(request, contest_id, pk, partial=False)

    def partial_update(self, request, contest_id=None, pk=None):
        return self._update(request, contest_id, pk, partial=True)

    def _update(self, request, contest_id, pk, partial):
        obj = self.get_queryset().filter(pk=pk).first()
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data
        if "label" in data:
            obj.label = (data["label"] or "").strip() or obj.label
        if "field_key" in data:
            fk = (data["field_key"] or "").strip().lower().replace(" ", "_")
            if fk and not ContestExtraField.objects.filter(contest_id=contest_id, field_key=fk).exclude(pk=pk).exists():
                obj.field_key = fk
        if "type" in data:
            obj.type = data["type"]
        if "required" in data:
            obj.required = bool(data["required"])
        if "placeholder" in data:
            obj.placeholder = (data["placeholder"] or "")[:255]
        if "help_text" in data:
            obj.help_text = data["help_text"] or ""
        if "order" in data:
            obj.order = int(data["order"]) if data["order"] is not None else 0
        if "is_active" in data:
            obj.is_active = bool(data["is_active"])
        if "options" in data:
            obj.options = data["options"] if isinstance(data["options"], list) else []
        obj.save()
        return Response({"id": obj.id, "field_key": obj.field_key, "label": obj.label, "type": obj.type, "required": obj.required,
                        "placeholder": obj.placeholder, "help_text": obj.help_text, "order": obj.order, "is_active": obj.is_active, "options": obj.options})

    def destroy(self, request, contest_id=None, pk=None):
        obj = self.get_queryset().filter(pk=pk).first()
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Contest participants
class ContestParticipantsView(APIView):
    """GET /api/v1/superadmin/contests/<contest_id>/participants/ – list registrations."""
    permission_classes = [IsSuperUser]

    def get(self, request, contest_id):
        try:
            contest = Contest.objects.get(pk=contest_id)
        except Contest.DoesNotExist:
            return Response({"detail": "Contest not found."}, status=status.HTTP_404_NOT_FOUND)
        qs = ContestRegistration.objects.filter(contest=contest).order_by("-created_at")
        extra_keys = list(
            ContestExtraField.objects.filter(contest=contest, is_active=True).order_by("order", "id").values_list("field_key", flat=True)
        )
        items = []
        for r in qs:
            row = {
                "id": r.id,
                "first_name": r.first_name,
                "last_name": r.last_name,
                "email": r.email or "",
                "phone_country_code": r.phone_country_code or "",
                "phone_number": r.phone_number or "",
                "extra_data": r.extra_data or {},
                "accept_terms": r.accept_terms,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for k in extra_keys:
                if k not in row["extra_data"]:
                    row["extra_data"][k] = None
            items.append(row)
        return Response({"count": len(items), "results": items})


def _export_contest_participants_csv(contest, qs):
    """Build CSV for contest participants (fixed fields + extra_data columns)."""
    extra_fields = list(
        ContestExtraField.objects.filter(contest=contest, is_active=True).order_by("order", "id")
    )
    extra_headers = [f.label for f in extra_fields]
    extra_keys = [f.field_key for f in extra_fields]
    options_by_key = {}
    for f in extra_fields:
        if f.options and f.type in ("select", "multiselect", "radio"):
            options_by_key[f.field_key] = {str(o.get("value")): o.get("label", o.get("value")) for o in f.options if isinstance(o, dict) and "value" in o}

    headers = ["id", "first_name", "last_name", "email", "phone_country_code", "phone_number", "created_at"] + extra_headers
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="concurso-{contest.slug}-participantes.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for r in qs:
        ed = r.extra_data or {}
        extra_row = []
        for k in extra_keys:
            val = ed.get(k)
            if k in options_by_key and val is not None:
                if isinstance(val, list):
                    extra_row.append("; ".join(options_by_key[k].get(str(v), v) for v in val))
                else:
                    extra_row.append(options_by_key[k].get(str(val), val))
            else:
                extra_row.append(val if val is not None else "")
        base = [r.id, r.first_name, r.last_name, r.email or "", r.phone_country_code or "", r.phone_number or "", r.created_at.isoformat() if r.created_at else ""]
        writer.writerow(base + extra_row)
    return response


class ContestParticipantsExportView(APIView):
    """GET /api/v1/superadmin/contests/<contest_id>/participants/export/ – CSV download."""
    permission_classes = [IsSuperUser]

    def get(self, request, contest_id):
        try:
            contest = Contest.objects.get(pk=contest_id)
        except Contest.DoesNotExist:
            return Response({"detail": "Contest not found."}, status=status.HTTP_404_NOT_FOUND)
        qs = ContestRegistration.objects.filter(contest=contest).order_by("-created_at")
        return _export_contest_participants_csv(contest, qs)
