"""Public API views for Erasmus registration and options."""

import logging

from django.db.utils import ProgrammingError
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from core.flow_logger import FlowLogger
from datetime import date
from django.utils import timezone
import secrets
from django.utils import timezone as tz

from apps.erasmus.models import (
    ErasmusLead,
    ErasmusDestinationGuide,
    ErasmusExtraField,
    ErasmusRegistroBackgroundSlide,
    ErasmusSlideConfig,
    ErasmusTimelineItem,
    ErasmusActivity,
    ErasmusActivityInstance,
    ErasmusLocalPartner,
    ErasmusMagicLink,
    ErasmusWhatsAppGroup,
)
from apps.erasmus.options_data import get_erasmus_options
from apps.erasmus.services import get_guides_for_destinations
from apps.landing_destinations.models import LandingDestination
from .serializers import ErasmusRegisterSerializer

logger = logging.getLogger(__name__)


def _timeline_sort_key(entry):
    """Sort key: (year, month, day) for chronological order, then display_order. No date -> end."""
    from datetime import date
    scheduled_date = entry.get("scheduledDate")
    if scheduled_date:
        try:
            d = date.fromisoformat(scheduled_date) if isinstance(scheduled_date, str) else scheduled_date
            return (d.year, d.month, d.day, entry.get("display_order", 0))
        except (TypeError, ValueError):
            pass
    year = entry.get("scheduledYear") or 9999
    month = entry.get("scheduledMonth") or 12
    return (year, month, 0, entry.get("display_order", 0))


class ErasmusTimelineView(APIView):
    """GET /api/v1/erasmus/timeline/ – unified timeline: legacy ErasmusTimelineItem + ErasmusActivityInstance."""
    permission_classes = [AllowAny]

    def get(self, request):
        result = []
        # Legacy items
        for item in ErasmusTimelineItem.objects.filter(is_active=True).order_by(
            "display_order", "scheduled_date", "created_at"
        ):
            result.append({
                "id": str(item.id),
                "itemType": "legacy",
                "experienceId": str(item.experience_id) if item.experience_id else None,
                "title": {"es": item.title_es, "en": item.title_en or item.title_es},
                "location": item.location or "",
                "image": item.image or "",
                "scheduledDate": item.scheduled_date.isoformat() if item.scheduled_date else None,
                "scheduledMonth": None,
                "scheduledYear": None,
                "scheduledLabel": None,
                "display_order": item.display_order,
            })
        # Activity instances (active activity + active instance)
        # Si la tabla no existe (migraciones sin aplicar), solo devolvemos ítems legacy
        try:
            instances = ErasmusActivityInstance.objects.filter(
                is_active=True,
                activity__is_active=True,
            ).select_related("activity").order_by(
                "display_order", "scheduled_date", "scheduled_year", "scheduled_month", "created_at"
            )
            for inst in instances:
                act = inst.activity
                images = act.images or []
                main_image = images[0] if isinstance(images[0], str) else (images[0].get("url") or images[0].get("image") or images[0].get("src") if images and isinstance(images[0], dict) else "") if images else ""
                scheduled_label = None
                if inst.scheduled_label_es or inst.scheduled_label_en:
                    scheduled_label = {"es": inst.scheduled_label_es or "", "en": inst.scheduled_label_en or inst.scheduled_label_es or ""}
                result.append({
                    "id": str(inst.id),
                    "itemType": "instance",
                    "activityId": str(act.id),
                    "experienceId": str(act.experience_id) if act.experience_id else None,
                    "title": {"es": act.title_es, "en": act.title_en or act.title_es},
                    "location": act.location or "",
                    "image": main_image or "",
                    "scheduledDate": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                    "scheduledMonth": inst.scheduled_month,
                    "scheduledYear": inst.scheduled_year,
                    "scheduledLabel": scheduled_label,
                    "display_order": inst.display_order,
                })
        except ProgrammingError as e:
            if "does not exist" in str(e).lower() or "undefined_table" in str(e).lower():
                logger.warning(
                    "Erasmus timeline: tablas de Activity/Instance no existen (ejecuta migrate). Error: %s",
                    e,
                )
            else:
                raise
        result.sort(key=_timeline_sort_key)
        return Response(result)


def _activity_main_image(images):
    """First URL from images list (same convention as Experience)."""
    if not images:
        return ""
    first = images[0]
    if isinstance(first, str):
        return first
    if isinstance(first, dict):
        return first.get("url") or first.get("image") or first.get("src") or ""
    return ""


def _format_time(t):
    """Format time to 'HH:MM' for public API."""
    if t is None:
        return None
    return t.strftime("%H:%M")


class ErasmusActivitiesListView(APIView):
    """GET /api/v1/erasmus/activities/ – public list of active activities (for cards view)."""
    permission_classes = [AllowAny]

    def get(self, request):
        activities = ErasmusActivity.objects.filter(is_active=True).order_by("display_order", "created_at")
        result = []
        for act in activities:
            images = act.images or []
            result.append({
                "id": str(act.id),
                "slug": act.slug,
                "title": {"es": act.title_es, "en": act.title_en or act.title_es},
                "short_description": {"es": act.short_description_es or "", "en": act.short_description_en or act.short_description_es or ""},
                "location": act.location or "",
                "image": _activity_main_image(images),
                "images": images,
                "display_order": act.display_order,
            })
        return Response(result)


class ErasmusActivityDetailView(APIView):
    """GET /api/v1/erasmus/activities/<uuid:activity_id>/ – activity detail with instances."""
    permission_classes = [AllowAny]

    def get(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id, is_active=True)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        instances = act.instances.filter(is_active=True).order_by(
            "scheduled_date", "scheduled_year", "scheduled_month", "display_order", "created_at"
        )
        instance_list = []
        for inst in instances:
            scheduled_label = None
            if inst.scheduled_label_es or inst.scheduled_label_en:
                scheduled_label = {"es": inst.scheduled_label_es or "", "en": inst.scheduled_label_en or inst.scheduled_label_es or ""}
            instance_list.append({
                "id": str(inst.id),
                "scheduledDate": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                "scheduledMonth": inst.scheduled_month,
                "scheduledYear": inst.scheduled_year,
                "scheduledLabel": scheduled_label,
                "startTime": _format_time(getattr(inst, "start_time", None)),
                "endTime": _format_time(getattr(inst, "end_time", None)),
                "display_order": inst.display_order,
            })
        return Response({
            "id": str(act.id),
            "slug": act.slug,
            "title": {"es": act.title_es, "en": act.title_en or act.title_es},
            "description": {"es": act.description_es or "", "en": act.description_en or act.description_es or ""},
            "short_description": {"es": act.short_description_es or "", "en": act.short_description_en or act.short_description_es or ""},
            "location": act.location or "",
            "locationName": getattr(act, "location_name", None) or "",
            "locationAddress": getattr(act, "location_address", None) or "",
            "durationMinutes": getattr(act, "duration_minutes", None),
            "included": getattr(act, "included", None) or [],
            "notIncluded": getattr(act, "not_included", None) or [],
            "itinerary": getattr(act, "itinerary", None) or [],
            "images": act.images or [],
            "image": _activity_main_image(act.images or []),
            "display_order": act.display_order,
            "instances": instance_list,
        })


class ErasmusActivityInstanceDetailView(APIView):
    """GET /api/v1/erasmus/instances/<uuid:instance_id>/ – single instance with activity data (for timeline click)."""
    permission_classes = [AllowAny]

    def get(self, request, instance_id):
        try:
            inst = ErasmusActivityInstance.objects.select_related("activity").get(
                id=instance_id,
                is_active=True,
                activity__is_active=True,
            )
        except ErasmusActivityInstance.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        act = inst.activity
        scheduled_label = None
        if inst.scheduled_label_es or inst.scheduled_label_en:
            scheduled_label = {"es": inst.scheduled_label_es or "", "en": inst.scheduled_label_en or inst.scheduled_label_es or ""}
        return Response({
            "id": str(inst.id),
            "itemType": "instance",
            "activityId": str(act.id),
            "title": {"es": act.title_es, "en": act.title_en or act.title_es},
            "description": {"es": act.description_es or "", "en": act.description_en or act.description_es or ""},
            "short_description": {"es": act.short_description_es or "", "en": act.short_description_en or act.short_description_es or ""},
            "location": act.location or "",
            "locationName": getattr(act, "location_name", None) or "",
            "locationAddress": getattr(act, "location_address", None) or "",
            "durationMinutes": getattr(act, "duration_minutes", None),
            "included": getattr(act, "included", None) or [],
            "notIncluded": getattr(act, "not_included", None) or [],
            "itinerary": getattr(act, "itinerary", None) or [],
            "images": act.images or [],
            "image": _activity_main_image(act.images or []),
            "scheduledDate": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
            "scheduledMonth": inst.scheduled_month,
            "scheduledYear": inst.scheduled_year,
            "scheduledLabel": scheduled_label,
            "startTime": _format_time(getattr(inst, "start_time", None)),
            "endTime": _format_time(getattr(inst, "end_time", None)),
            "display_order": inst.display_order,
        })


class ErasmusTimelineEntryDetailView(APIView):
    """GET /api/v1/erasmus/timeline/<uuid:entry_id>/ – detail for one timeline entry (legacy or instance) by id."""
    permission_classes = [AllowAny]

    def get(self, request, entry_id):
        payload = _get_timeline_entry_payload(entry_id)
        if payload is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)


class ErasmusSlidesView(APIView):
    """GET /api/v1/erasmus/slides/ – public hero slide configs as ordered list [{ slide_id, url }, ...].
    URLs are always absolute using the request host so images load from the same origin as the API.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        configs = ErasmusSlideConfig.objects.filter(
            asset__isnull=False
        ).select_related('asset').order_by('order', 'slide_id')
        result = []
        for cfg in configs:
            if not cfg.asset or getattr(cfg.asset, 'deleted_at', None):
                continue
            if not cfg.asset.file:
                continue
            # Build absolute URL from request host so frontend (any origin) loads media from API host
            raw_url = cfg.asset.file.url or ''
            if raw_url.startswith(('http://', 'https://')):
                url = raw_url
            else:
                # Ensure path is absolute (leading /) so build_absolute_uri works (MEDIA_URL may be "media/" without /)
                path = raw_url.lstrip('/')
                url = request.build_absolute_uri(f'/{path}' if path else '/')
            caption = getattr(cfg, 'caption', '') or ''
            result.append({'slide_id': cfg.slide_id, 'url': url, 'caption': caption})
        return Response(result)


class ErasmusOptionsView(APIView):
    """GET /api/v1/erasmus/options/ – destinations, interests, extra fields, destination_guides info."""
    permission_classes = [AllowAny]

    def get(self, request):
        data = get_erasmus_options()
        extra_fields = list(
            ErasmusExtraField.objects.filter(is_active=True).order_by("order", "id").values(
                "id", "field_key", "label", "type", "required", "placeholder", "help_text", "order", "options"
            )
        )
        data["extra_fields"] = extra_fields
        # Destinations that have at least one guide (for frontend copy: "te preparamos guías por destino")
        slugs_with_guides = list(
            ErasmusDestinationGuide.objects.filter(is_active=True)
            .values_list("destination_slug", flat=True)
            .distinct()
        )
        data["destination_slugs_with_guides"] = slugs_with_guides
        # Destinos de Tuki (panel superadmin): lista para cards en el formulario Erasmus
        destinations_list = list(
            LandingDestination.objects.filter(is_active=True)
            .order_by("country", "name")
            .values("slug", "name", "country", "hero_image")
        )
        data["destinations_list"] = [
            {
                "slug": d["slug"],
                "name": d["name"],
                "country": d["country"],
                "image": d["hero_image"] or "",
            }
            for d in destinations_list
        ]
        # Fondo del formulario de registro: imágenes que rotan detrás del formulario
        registro_slides = ErasmusRegistroBackgroundSlide.objects.filter(
            asset__isnull=False
        ).select_related("asset").order_by("order", "id")
        registro_urls = []
        for cfg in registro_slides:
            if not cfg.asset or getattr(cfg.asset, "deleted_at", None):
                continue
            # Use MediaAsset.url property (handles GCS and local BACKEND_URL)
            raw_url = getattr(cfg.asset, "url", None) if cfg.asset else None
            if not raw_url:
                continue
            if raw_url.startswith(("http://", "https://")):
                url = raw_url
            else:
                path = raw_url.lstrip("/")
                url = request.build_absolute_uri(f"/{path}" if path else "/")
            registro_urls.append({"url": url})
        data["registro_background_slides"] = registro_urls
        return Response(data)


class ErasmusWhatsAppGroupsView(APIView):
    """GET /api/v1/erasmus/whatsapp-groups/ – list of { name, link } for student profile (ASMUS)."""
    permission_classes = [AllowAny]

    def get(self, request):
        groups = list(
            ErasmusWhatsAppGroup.objects.filter(is_active=True)
            .order_by("order", "id")
            .values("name", "link")
        )
        return Response([{"name": g["name"], "link": g["link"]} for g in groups])


class ErasmusTrackVisitView(APIView):
    """POST /api/v1/erasmus/track-visit/ – start Erasmus registration flow (link visit). Returns flow_id for later steps."""
    permission_classes = [AllowAny]

    def post(self, request):
        source = (request.data.get("source") or request.query_params.get("source") or "").strip() or None
        utm_source = (request.data.get("utm_source") or "").strip() or None
        utm_medium = (request.data.get("utm_medium") or "").strip() or None
        utm_campaign = (request.data.get("utm_campaign") or "").strip() or None
        session_id = (request.data.get("session_id") or "").strip() or None
        metadata = {"source_slug": source}
        if utm_source is not None:
            metadata["utm_source"] = utm_source
        if utm_medium is not None:
            metadata["utm_medium"] = utm_medium
        if utm_campaign is not None:
            metadata["utm_campaign"] = utm_campaign
        if session_id:
            metadata["session_id"] = session_id
        try:
            flow = FlowLogger.start_flow(
                "erasmus_registration",
                metadata=metadata,
            )
            if flow and flow.flow:
                flow.log_event(
                    "ERASMUS_LINK_VISIT",
                    source="api",
                    status="info",
                    message="User landed on registration page",
                    metadata={"source_slug": source},
                )
                return Response({"flow_id": str(flow.flow.id)}, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception("Erasmus track-visit failed: %s", e)
        return Response({"flow_id": None}, status=status.HTTP_200_OK)


class ErasmusTrackStepView(APIView):
    """POST /api/v1/erasmus/track-step/ – log a step in an existing Erasmus registration flow."""
    permission_classes = [AllowAny]

    def post(self, request):
        flow_id = request.data.get("flow_id")
        step = (request.data.get("step") or "").strip()
        step_number = request.data.get("step_number")
        if not flow_id or not step:
            return Response(
                {"detail": "flow_id and step are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        allowed_steps = ("ERASMUS_FORM_STARTED", "ERASMUS_STEP_COMPLETED")
        if step not in allowed_steps:
            return Response(
                {"detail": f"step must be one of {allowed_steps}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            flow = FlowLogger.from_flow_id(flow_id)
            if not flow or not flow.flow:
                return Response({"detail": "Flow not found"}, status=status.HTTP_404_NOT_FOUND)
            if flow.flow.status != "in_progress":
                return Response({"detail": "Flow already completed or abandoned"}, status=status.HTTP_400_BAD_REQUEST)
            metadata = {}
            if step_number is not None:
                metadata["step_number"] = step_number
            flow.log_event(
                step,
                source="api",
                status="info",
                message=f"Erasmus registration: {step}",
                metadata=metadata,
            )
            return Response({"ok": True})
        except Exception as e:
            logger.exception("Erasmus track-step failed: %s", e)
            return Response(
                {"detail": "Error recording step"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ErasmusRegisterView(APIView):
    """POST /api/v1/erasmus/register/ – create Erasmus lead (and optional guest user if email provided)."""
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.data.copy()
        flow_id = payload.pop("flow_id", None)
        source = request.query_params.get("source") or payload.get("source_slug")
        if source and not payload.get("source_slug"):
            payload["source_slug"] = source
        for key in ("utm_source", "utm_medium", "utm_campaign"):
            if request.query_params.get(key) and not payload.get(key):
                payload[key] = request.query_params.get(key)

        serializer = ErasmusRegisterSerializer(
            data=payload,
            context={"flow_id": flow_id},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            lead = serializer.save()
        except Exception as e:
            logger.exception("Erasmus register failed: %s", e)
            return Response(
                {"detail": "Error al registrar. Intenta de nuevo o contacta soporte."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        response_data = {
            "success": True,
            "message": "Gracias por inscribirte. Te hemos enviado por WhatsApp las guías de los destinos que elegiste. También quedarán en tu perfil.",
            "lead_id": str(lead.id),
        }
        if lead.community_profile_token:
            response_data["community_profile_token"] = lead.community_profile_token
        return Response(response_data, status=status.HTTP_201_CREATED)


def _age_from_birth_date(birth_date):
    """Return age in years or None if no birth_date."""
    if not birth_date:
        return None
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def _arrival_month_label(arrival_date):
    """Return short label like 'Sept' or 'Ene' from arrival_date."""
    if not arrival_date:
        return None
    months_es = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sept", "Oct", "Nov", "Dic")
    m = arrival_date.month
    return months_es[m - 1] if 1 <= m <= 12 else None


class ErasmusCommunityListView(APIView):
    """GET /api/v1/erasmus/community/ – public list of leads who opted in to the community directory."""
    permission_classes = [AllowAny]

    def get(self, request):
        qs = ErasmusLead.objects.filter(
            opt_in_community=True,
            completion_status="complete",
            is_suspended=False,
        ).order_by("-arrival_date", "-created_at")

        arrival_month = request.query_params.get("arrival_month")
        if arrival_month:
            try:
                m = int(arrival_month)
                if 1 <= m <= 12:
                    from django.db.models import Q
                    qs = qs.filter(Q(arrival_date__month=m) | Q(arrival_date__isnull=True))
            except ValueError:
                pass
        university = (request.query_params.get("university") or "").strip()
        if university:
            qs = qs.filter(university__icontains=university)
        country = (request.query_params.get("country") or "").strip()
        if country:
            qs = qs.filter(country__iexact=country)

        limit = min(int(request.query_params.get("limit", 12)), 48)
        offset = max(0, int(request.query_params.get("offset", 0)))
        total = qs.count()
        page = list(qs[offset : offset + limit])

        results = []
        for lead in page:
            photo_url = None
            if lead.profile_photo:
                raw = lead.profile_photo.url
                photo_url = request.build_absolute_uri(raw) if raw and not raw.startswith(("http://", "https://")) else raw
            instagram_handle = (lead.instagram or "").strip().lstrip("@")
            show_dates = getattr(lead, "community_show_dates", True)
            show_age = getattr(lead, "community_show_age", True)
            show_whatsapp = getattr(lead, "community_show_whatsapp", False)
            entry = {
                "id": str(lead.id),
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "country": lead.country or "",
                "university": lead.university or "",
                "instagram": instagram_handle or None,
                "profile_photo_url": photo_url,
                "community_bio": (lead.community_bio or "").strip() or None,
                "languages_spoken": lead.languages_spoken or [],
            }
            if show_age:
                entry["age"] = _age_from_birth_date(lead.birth_date)
            else:
                entry["age"] = None
            if show_dates:
                entry["arrival_date"] = lead.arrival_date.isoformat() if lead.arrival_date else None
                entry["arrival_month"] = lead.arrival_date.month if lead.arrival_date else None
                entry["arrival_label"] = _arrival_month_label(lead.arrival_date)
            else:
                entry["arrival_date"] = None
                entry["arrival_month"] = None
                entry["arrival_label"] = None
            if show_whatsapp:
                entry["whatsapp"] = f"{lead.phone_country_code or ''}{lead.phone_number or ''}".strip() or None
            else:
                entry["whatsapp"] = None
            results.append(entry)
        return Response({
            "results": results,
            "total": total,
            "limit": limit,
            "offset": offset,
        })


class ErasmusCommunityProfileUpdateView(APIView):
    """POST /api/v1/erasmus/community-profile/ – update community profile (bio, photo) with lead_id + token."""
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        lead_id = (request.data.get("lead_id") or "").strip()
        token = (request.data.get("token") or "").strip()
        if not lead_id or not token:
            return Response(
                {"detail": "lead_id y token son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            lead = ErasmusLead.objects.get(pk=lead_id)
        except (ErasmusLead.DoesNotExist, ValueError):
            return Response({"detail": "Registro no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if not lead.community_profile_token or lead.community_profile_token != token:
            return Response({"detail": "Token inválido."}, status=status.HTTP_403_FORBIDDEN)

        bio = request.data.get("community_bio") or request.data.get("bio")
        if bio is not None:
            lead.community_bio = (bio if isinstance(bio, str) else str(bio))[:2000]
        photo = request.FILES.get("profile_photo")
        if photo:
            if photo.size > 5 * 1024 * 1024:  # 5 MB
                return Response({"detail": "La imagen no debe superar 5 MB."}, status=status.HTTP_400_BAD_REQUEST)
            lead.profile_photo = photo
        languages_spoken = request.data.get("languages_spoken")
        if languages_spoken is not None:
            if isinstance(languages_spoken, str):
                import json
                try:
                    languages_spoken = json.loads(languages_spoken)
                except (TypeError, ValueError):
                    languages_spoken = []
            if isinstance(languages_spoken, list):
                lead.languages_spoken = [str(x) for x in languages_spoken if x][:20]
        update_fields = ["community_bio", "profile_photo", "updated_at"]
        if languages_spoken is not None:
            update_fields.append("languages_spoken")
        lead.save(update_fields=update_fields)
        photo_url = None
        if lead.profile_photo:
            raw = lead.profile_photo.url
            photo_url = request.build_absolute_uri(raw) if raw and not raw.startswith(("http://", "https://")) else raw
        return Response({
            "success": True,
            "community_bio": lead.community_bio or "",
            "profile_photo_url": photo_url,
            "languages_spoken": lead.languages_spoken or [],
        }, status=status.HTTP_200_OK)


class ErasmusRequestWhatsAppApprovalView(APIView):
    """POST /api/v1/erasmus/leads/<lead_id>/request-whatsapp-approval/ – marca que el lead pidió aprobación en el grupo."""
    permission_classes = [AllowAny]

    def post(self, request, lead_id):
        try:
            lead = ErasmusLead.objects.get(pk=lead_id)
        except ErasmusLead.DoesNotExist:
            return Response(
                {"detail": "Registro no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if lead.requested_whatsapp_approval_at:
            return Response(
                {"success": True, "message": "Ya habías solicitado aprobación. Te agregaremos al grupo pronto."},
                status=status.HTTP_200_OK,
            )
        lead.requested_whatsapp_approval_at = timezone.now()
        lead.save(update_fields=["requested_whatsapp_approval_at", "updated_at"])
        return Response(
            {"success": True, "message": "Recibido. Te aprobaremos en el grupo en breve."},
            status=status.HTTP_200_OK,
        )


class ErasmusExpressInterestView(APIView):
    """POST /api/v1/erasmus/express-interest/ – vincular lead por teléfono e indicar interés en una actividad.
    Accepts timeline_item_id (legacy) or activity_instance_id; both stored in interested_experiences."""
    permission_classes = [AllowAny]

    def post(self, request):
        phone_country_code = (request.data.get("phone_country_code") or "").strip()
        phone_number = (request.data.get("phone_number") or "").strip()
        timeline_item_id = (request.data.get("timeline_item_id") or "").strip()
        activity_instance_id = (request.data.get("activity_instance_id") or "").strip()
        activity_id = timeline_item_id or activity_instance_id
        if not phone_country_code or not phone_number:
            return Response(
                {"detail": "Faltan código de país o número de teléfono."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not activity_id:
            return Response(
                {"detail": "Falta el id de la actividad (timeline_item_id o activity_instance_id)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lead = (
            ErasmusLead.objects.filter(
                phone_country_code=phone_country_code,
                phone_number=phone_number,
            )
            .order_by("-created_at")
            .first()
        )
        if not lead:
            return Response(
                {"detail": "No encontramos un registro Erasmus con ese número. Completa primero el formulario de registro."},
                status=status.HTTP_404_NOT_FOUND,
            )
        experiences = list(lead.interested_experiences or [])
        if activity_id not in experiences:
            experiences.append(activity_id)
            lead.interested_experiences = experiences
            lead.save(update_fields=["interested_experiences", "updated_at"])
        return Response(
            {
                "success": True,
                "message": "Gracias por registrarte. Ya formas parte de la experiencia. Puedes revisar los detalles de tu reserva en tu cuenta. ¡Nos vemos!",
            },
            status=status.HTTP_200_OK,
        )


def _get_timeline_entry_payload(entry_id):
    """Build the same payload as timeline entry detail for a given entry_id (instance or legacy). Returns dict or None."""
    try:
        inst = ErasmusActivityInstance.objects.select_related("activity").get(
            id=entry_id,
            is_active=True,
            activity__is_active=True,
        )
    except (ErasmusActivityInstance.DoesNotExist, ValueError):
        inst = None
    if inst:
        act = inst.activity
        scheduled_label = None
        if inst.scheduled_label_es or inst.scheduled_label_en:
            scheduled_label = {"es": inst.scheduled_label_es or "", "en": inst.scheduled_label_en or inst.scheduled_label_es or ""}
        return {
            "id": str(inst.id),
            "itemType": "instance",
            "activityId": str(act.id),
            "title": {"es": act.title_es, "en": act.title_en or act.title_es},
            "description": {"es": act.description_es or "", "en": act.description_en or act.description_es or ""},
            "short_description": {"es": act.short_description_es or "", "en": act.short_description_en or act.short_description_es or ""},
            "location": act.location or "",
            "locationName": getattr(act, "location_name", None) or "",
            "locationAddress": getattr(act, "location_address", None) or "",
            "durationMinutes": getattr(act, "duration_minutes", None),
            "included": getattr(act, "included", None) or [],
            "notIncluded": getattr(act, "not_included", None) or [],
            "itinerary": getattr(act, "itinerary", None) or [],
            "images": act.images or [],
            "image": _activity_main_image(act.images or []),
            "scheduledDate": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
            "scheduledMonth": inst.scheduled_month,
            "scheduledYear": inst.scheduled_year,
            "scheduledLabel": scheduled_label,
            "startTime": _format_time(getattr(inst, "start_time", None)),
            "endTime": _format_time(getattr(inst, "end_time", None)),
            "display_order": inst.display_order,
        }
    try:
        item = ErasmusTimelineItem.objects.get(id=entry_id, is_active=True)
    except (ErasmusTimelineItem.DoesNotExist, ValueError):
        return None
    return {
        "id": str(item.id),
        "itemType": "legacy",
        "activityId": None,
        "title": {"es": item.title_es, "en": item.title_en or item.title_es},
        "description": {"es": "", "en": ""},
        "short_description": {"es": "", "en": ""},
        "location": item.location or "",
        "images": [item.image] if item.image else [],
        "image": item.image or "",
        "scheduledDate": item.scheduled_date.isoformat() if item.scheduled_date else None,
        "scheduledMonth": None,
        "scheduledYear": None,
        "scheduledLabel": None,
        "display_order": item.display_order,
    }


class ErasmusMyActivitiesView(APIView):
    """GET /api/v1/erasmus/my-activities/ – actividades del timeline en las que el usuario (lead) se inscribió (evidencia en su perfil)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        lead = getattr(user, "erasmus_leads", None)
        if lead is None:
            return Response({"entries": []})
        lead = user.erasmus_leads.order_by("-created_at").first()
        if not lead:
            return Response({"entries": []})
        ids = list(lead.interested_experiences or [])
        entries = []
        seen = set()
        for eid in ids:
            try:
                eid_str = str(eid).strip()
                if not eid_str or eid_str in seen:
                    continue
                seen.add(eid_str)
                payload = _get_timeline_entry_payload(eid_str)
                if payload:
                    entries.append(payload)
            except Exception:
                continue
        return Response({"entries": entries})


class ErasmusMyGuidesView(APIView):
    """GET /api/v1/erasmus/my-guides/ – guías de viaje para los destinos del lead del usuario (perfil)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        lead = getattr(user, "erasmus_leads", None)
        if lead is None:
            return Response({"guides": []})
        # First lead linked to this user (most recent if multiple)
        lead = user.erasmus_leads.order_by("-created_at").first()
        if not lead or not lead.destinations:
            return Response({"guides": []})
        guides = get_guides_for_destinations(list(lead.destinations))
        return Response({"guides": guides})


class ErasmusLocalPartnersView(APIView):
    """GET /api/v1/erasmus/local-partners/ – active local partners for the gracias page."""
    permission_classes = [AllowAny]

    def get(self, request):
        partners = ErasmusLocalPartner.objects.filter(is_active=True).select_related("asset").order_by("order", "id")
        results = []
        for p in partners:
            photo_url = None
            if getattr(p, "asset_id", None) and p.asset and not getattr(p.asset, "deleted_at", None):
                photo_url = getattr(p.asset, "url", None)
            if not photo_url and p.photo:
                raw = p.photo.url
                photo_url = request.build_absolute_uri(raw) if raw and not raw.startswith(("http://", "https://")) else raw
            instagram_url = f"https://instagram.com/{p.instagram_username.strip().lstrip('@')}" if p.instagram_username else None
            whatsapp_url = f"https://wa.me/{p.whatsapp_number.strip().lstrip('+').replace(' ', '')}" if p.whatsapp_number else None
            results.append({
                "id": str(p.id),
                "name": p.name,
                "role": p.role,
                "photo_url": photo_url,
                "bio": p.bio,
                "instagram_username": p.instagram_username.strip().lstrip("@") if p.instagram_username else None,
                "instagram_url": instagram_url,
                "whatsapp_number": p.whatsapp_number if p.whatsapp_number else None,
                "whatsapp_url": whatsapp_url,
            })
        return Response(results)


class ErasmusGenerateAccessCodeView(APIView):
    """
    POST /api/v1/erasmus/generate-access-code/

    Phase 1 of the Erasmus magic-link flow.
    Generates an ERAS-XXXXXX verification code and returns a pre-filled WhatsApp URL
    that the student will use to message Tuki.  When Tuki's bot receives the message
    it sends back the actual magic link (Phase 2).

    Input:  { lead_id, target: 'community'|'whatsapp' }
    Output: { verification_code, whatsapp_url, expires_at }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        lead_id = (request.data.get("lead_id") or "").strip()
        target = (request.data.get("target") or "").strip()

        if not lead_id:
            return Response({"detail": "lead_id requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if target not in ("community", "whatsapp"):
            return Response(
                {"detail": "target debe ser 'community' o 'whatsapp'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            lead = ErasmusLead.objects.get(pk=lead_id)
        except ErasmusLead.DoesNotExist:
            return Response({"detail": "Registro no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        try:
            from apps.erasmus.access_code_service import generate_access_code
            result = generate_access_code(lead, target)
        except Exception as exc:
            logger.exception("[ErasmusAccess] generate_access_code failed for lead %s: %s", lead_id, exc)
            return Response(
                {"detail": "No se pudo generar el código. Intenta de nuevo."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result, status=status.HTTP_201_CREATED)


class ErasmusMagicLoginView(APIView):
    """
    POST /api/v1/erasmus/magic-login/

    Phase 3 of the Erasmus magic-link flow.
    The student opens the link {FRONTEND_URL}/erasmus/acceder?token=XXX,
    which calls this endpoint with the access_token.
    Returns JWT tokens so the frontend can store them and redirect to the profile tab.

    Input:  { access_token }
    Output: { access, refresh, target, user: { id, email, first_name, last_name } }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from rest_framework_simplejwt.tokens import RefreshToken
        import logging
        logger = logging.getLogger(__name__)

        # Aceptar token en body (access_token o token) o en query
        token_str = (
            (request.data.get("access_token") or request.data.get("token") or "")
            or (request.query_params.get("access_token") or request.query_params.get("token") or "")
        ).strip()
        if not token_str:
            logger.warning("[ErasmusMagicLogin] POST sin token: data=%s query=%s", list(request.data.keys()), list(request.query_params.keys()))
            return Response({"detail": "access_token requerido."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            magic = ErasmusMagicLink.objects.select_related("lead__user").get(access_token=token_str)
        except ErasmusMagicLink.DoesNotExist:
            logger.warning("[ErasmusMagicLogin] Token no encontrado (inválido o expirado)")
            return Response({"detail": "Enlace inválido o expirado."}, status=status.HTTP_400_BAD_REQUEST)

        now = tz.now()

        # If link was already used (double-open, refresh, second tab), issue a fresh JWT for the same user
        if magic.status == ErasmusMagicLink.STATUS_USED:
            lead = magic.lead
            if getattr(lead, "is_suspended", False):
                logger.warning("[ErasmusMagicLogin] 400 target=%s reason=suspended", magic.target)
                return Response({"detail": "Tu cuenta está suspendida. Contacta soporte."}, status=status.HTTP_400_BAD_REQUEST)
            user = lead.user
            if not user or not user.is_active:
                logger.warning("[ErasmusMagicLogin] 400 target=%s reason=no_user", magic.target)
                return Response({"detail": "Enlace inválido o expirado."}, status=status.HTTP_400_BAD_REQUEST)
            logger.info("[ErasmusMagicLogin] 200 target=%s (reuse)", magic.target)
            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "target": magic.target,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
            })

        if magic.status == ErasmusMagicLink.STATUS_EXPIRED:
            logger.warning("[ErasmusMagicLogin] 400 target=%s reason=status_expired", magic.target)
            return Response({"detail": "Este enlace ha expirado. Solicita uno nuevo."}, status=status.HTTP_400_BAD_REQUEST)
        if magic.status != ErasmusMagicLink.STATUS_LINK_SENT:
            logger.warning("[ErasmusMagicLogin] 400 target=%s reason=bad_status status=%s", magic.target, magic.status)
            return Response({"detail": "Enlace no válido."}, status=status.HTTP_400_BAD_REQUEST)
        if not magic.is_link_valid:
            logger.warning("[ErasmusMagicLogin] 400 target=%s reason=link_expired link_expires_at=%s", magic.target, magic.link_expires_at)
            magic.status = ErasmusMagicLink.STATUS_EXPIRED
            magic.save(update_fields=["status", "updated_at"])
            return Response({"detail": "Este enlace ha expirado. Solicita uno nuevo."}, status=status.HTTP_400_BAD_REQUEST)

        lead = magic.lead
        if getattr(lead, "is_suspended", False):
            return Response({"detail": "Tu cuenta está suspendida. Contacta soporte."}, status=status.HTTP_400_BAD_REQUEST)
        user = lead.user

        # If lead has no user (e.g. registered without email), create/link one so magic-link can log them in
        if not user or not user.is_active:
            logger.info(
                "[ErasmusMagicLogin] Lead %s sin user activo (user=%s, is_active=%s); creando/enlazando.",
                lead.id, getattr(lead.user, "id", None), getattr(lead.user, "is_active", None),
            )
            from django.contrib.auth import get_user_model
            from core.phone_utils import normalize_phone_e164

            User = get_user_model()
            email = (lead.email or "").strip()
            phone_full = f"{lead.phone_country_code or ''}{lead.phone_number or ''}".strip()
            normalized_phone = normalize_phone_e164(phone_full) if phone_full else None

            if email and User.objects.filter(email__iexact=email).exists():
                user = User.objects.get(email__iexact=email)
                if not user.is_active:
                    return Response({"detail": "Tu cuenta no está activa. Contacta soporte."}, status=status.HTTP_400_BAD_REQUEST)
                lead.user = user
                lead.save(update_fields=["user", "updated_at"])
            elif email:
                try:
                    user = User.create_guest_user(
                        email=email,
                        first_name=lead.first_name,
                        last_name=lead.last_name,
                        phone=normalized_phone or phone_full or None,
                    )
                    lead.user = user
                    lead.save(update_fields=["user", "updated_at"])
                except Exception:
                    return Response({"detail": "No se pudo crear la sesión. Contacta soporte."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                # Lead sin email: crear usuario invitado con email placeholder único
                placeholder_email = f"erasmus-{lead.id}@guest.tuki.local"
                if User.objects.filter(email__iexact=placeholder_email).exists():
                    user = User.objects.get(email__iexact=placeholder_email)
                else:
                    try:
                        user = User.create_guest_user(
                            email=placeholder_email,
                            first_name=lead.first_name or "",
                            last_name=lead.last_name or "",
                            phone=normalized_phone or phone_full or None,
                        )
                    except Exception:
                        return Response({"detail": "No se pudo crear la sesión. Contacta soporte."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                lead.user = user
                lead.save(update_fields=["user", "updated_at"])

        magic.status = ErasmusMagicLink.STATUS_USED
        magic.used_at = now
        magic.save(update_fields=["status", "used_at", "updated_at"])

        logger.info("[ErasmusMagicLogin] 200 target=%s lead=%s", magic.target, lead.id)
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "target": magic.target,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
        })
