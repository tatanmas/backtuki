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
    ErasmusActivity,
    ErasmusActivityExtraField,
    ErasmusActivityInstance,
    ErasmusActivityInstanceRegistration,
    ErasmusActivityReview,
    ErasmusLocalPartner,
    ErasmusMagicLink,
    ErasmusWhatsAppGroup,
)
from apps.erasmus.activity_display import get_activity_display_data
from apps.erasmus.options_data import get_erasmus_options
from apps.erasmus.services import get_guides_for_destinations
from apps.landing_destinations.models import LandingDestination
from apps.landing_destinations.views import _build_destination_media_urls_from_request
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
    """GET /api/v1/erasmus/timeline/ – timeline: solo ErasmusActivityInstance (actividad instanciada en fecha)."""
    permission_classes = [AllowAny]

    def get(self, request):
        result = []
        try:
            instances = ErasmusActivityInstance.objects.filter(
                is_active=True,
                activity__is_active=True,
            ).select_related("activity", "activity__experience").order_by(
                "display_order", "scheduled_date", "scheduled_year", "scheduled_month", "created_at"
            )
            for inst in instances:
                act = inst.activity
                display = get_activity_display_data(act)
                scheduled_label = None
                if inst.scheduled_label_es or inst.scheduled_label_en:
                    scheduled_label = {"es": inst.scheduled_label_es or "", "en": inst.scheduled_label_en or inst.scheduled_label_es or ""}
                display_count = _instance_interested_display_count(inst)
                capacity = getattr(inst, "capacity", None)
                is_agotado = getattr(inst, "is_agotado", False)
                result.append({
                    "id": str(inst.id),
                    "itemType": "instance",
                    "activityId": str(act.id),
                    "experienceId": str(act.experience_id) if act.experience_id else None,
                    "title": {"es": display["title_es"], "en": display["title_en"]},
                    "location": display["location"] or "",
                    "image": display["image"] or "",
                    "scheduledDate": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                    "scheduledMonth": inst.scheduled_month,
                    "scheduledYear": inst.scheduled_year,
                    "scheduledLabel": scheduled_label,
                    "display_order": inst.display_order,
                    "interestedCount": display_count,
                    "capacity": capacity,
                    "is_agotado": is_agotado,
                    "isPast": inst.is_past,
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


def _instance_interested_display_count(inst):
    """Real inscritos + interested_count_boost for public display."""
    real = ErasmusLead.objects.filter(
        interested_experiences__contains=[str(inst.id)]
    ).count()
    boost = getattr(inst, "interested_count_boost", 0) or 0
    return real + boost


class ErasmusActivitiesListView(APIView):
    """GET /api/v1/erasmus/activities/ – public list of active activities (for cards view)."""
    permission_classes = [AllowAny]

    def get(self, request):
        activities = ErasmusActivity.objects.filter(is_active=True).select_related("experience").order_by("display_order", "created_at")
        result = []
        for act in activities:
            display = get_activity_display_data(act)
            result.append({
                "id": str(act.id),
                "slug": act.slug,
                "title": {"es": display["title_es"], "en": display["title_en"]},
                "short_description": {"es": display["short_description_es"], "en": display["short_description_en"]},
                "location": display["location"] or "",
                "image": display["image"] or "",
                "images": display["images"],
                "display_order": act.display_order,
            })
        return Response(result)


class ErasmusActivityDetailView(APIView):
    """GET /api/v1/erasmus/activities/<uuid:activity_id>/ – activity detail with instances."""
    permission_classes = [AllowAny]

    def get(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.select_related("experience").get(id=activity_id, is_active=True)
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
            interested_count = ErasmusLead.objects.filter(
                interested_experiences__contains=[str(inst.id)]
            ).count()
            instance_list.append({
                "id": str(inst.id),
                "scheduledDate": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                "scheduledMonth": inst.scheduled_month,
                "scheduledYear": inst.scheduled_year,
                "scheduledLabel": scheduled_label,
                "startTime": _format_time(getattr(inst, "start_time", None)),
                "endTime": _format_time(getattr(inst, "end_time", None)),
                "display_order": inst.display_order,
                "interestedCount": interested_count,
                "capacity": getattr(inst, "capacity", None),
                "is_agotado": getattr(inst, "is_agotado", False),
            })
        return Response(_activity_detail_payload(act, instance_list))


def _activity_detail_payload(act, instance_list):
    """Build the same payload for activity detail (by id or by slug). Uses display data when activity is linked to an Experience. Includes extra_fields for inscription form."""
    display = get_activity_display_data(act)
    payload = {
        "id": str(act.id),
        "slug": act.slug,
        "experienceId": str(act.experience_id) if act.experience_id else None,
        "title": {"es": display["title_es"], "en": display["title_en"]},
        "description": {"es": display["description_es"], "en": display["description_en"]},
        "short_description": {"es": display["short_description_es"], "en": display["short_description_en"]},
        "location": display["location"] or "",
        "locationName": display["location_name"] or "",
        "locationAddress": display["location_address"] or "",
        "durationMinutes": display["duration_minutes"],
        "included": display["included"],
        "notIncluded": display["not_included"],
        "itinerary": display["itinerary"],
        "images": display["images"],
        "image": display["image"] or "",
        "display_order": act.display_order,
        "detailLayout": getattr(act, "detail_layout", "default") or "default",
        "instances": instance_list,
    }
    extra_fields = _serialize_activity_extra_fields(act)
    if extra_fields:
        payload["extra_fields"] = extra_fields
    return payload


class ErasmusActivityDetailBySlugView(APIView):
    """GET /api/v1/erasmus/activities/by-slug/<slug>/ – same as activity detail but lookup by slug."""
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            act = ErasmusActivity.objects.select_related("experience").get(slug=slug, is_active=True)
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
                "interestedCount": _instance_interested_display_count(inst),
                "capacity": getattr(inst, "capacity", None),
                "is_agotado": getattr(inst, "is_agotado", False),
                "isPast": inst.is_past,
            })
        return Response(_activity_detail_payload(act, instance_list))


def _instance_review_label(inst):
    """Label for instance in review list (date or label_es or month/year)."""
    if inst.scheduled_date:
        return inst.scheduled_date.strftime("%d/%m/%Y")
    if inst.scheduled_label_es:
        return inst.scheduled_label_es
    if inst.scheduled_month and inst.scheduled_year:
        return f"{inst.scheduled_month:02d}/{inst.scheduled_year}"
    return str(inst.id)


class ErasmusActivityReviewsListView(APIView):
    """GET /api/v1/erasmus/activities/<activity_id>/reviews/ – public list of reviews for an activity (with instance date)."""
    permission_classes = [AllowAny]

    def get(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id, is_active=True)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        reviews = (
            ErasmusActivityReview.objects.filter(instance__activity_id=act.id)
            .select_related("instance")
            .order_by("-created_at")
        )
        results = []
        for r in reviews:
            inst = r.instance
            results.append({
                "id": r.id,
                "instance_id": str(inst.id),
                "instance_label": _instance_review_label(inst),
                "instance_scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                "author_name": r.author_name,
                "author_origin": r.author_origin or "",
                "rating": r.rating,
                "body": r.body,
                "review_date": r.created_at.isoformat() if r.created_at else None,
            })
        return Response({"results": results, "count": len(results)})


class ErasmusActivityInstanceDetailView(APIView):
    """GET /api/v1/erasmus/instances/<uuid:instance_id>/ – single instance with activity data (for timeline click)."""
    permission_classes = [AllowAny]

    def get(self, request, instance_id):
        try:
            inst = ErasmusActivityInstance.objects.select_related("activity", "activity__experience").get(
                id=instance_id,
                is_active=True,
                activity__is_active=True,
            )
        except ErasmusActivityInstance.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        act = inst.activity
        display = get_activity_display_data(act)
        scheduled_label = None
        if inst.scheduled_label_es or inst.scheduled_label_en:
            scheduled_label = {"es": inst.scheduled_label_es or "", "en": inst.scheduled_label_en or inst.scheduled_label_es or ""}
        return Response({
            "id": str(inst.id),
            "itemType": "instance",
            "activityId": str(act.id),
            "experienceId": str(act.experience_id) if act.experience_id else None,
            "title": {"es": display["title_es"], "en": display["title_en"]},
            "description": {"es": display["description_es"], "en": display["description_en"]},
            "short_description": {"es": display["short_description_es"], "en": display["short_description_en"]},
            "location": display["location"] or "",
            "locationName": display["location_name"] or "",
            "locationAddress": display["location_address"] or "",
            "durationMinutes": display["duration_minutes"],
            "included": display["included"],
            "notIncluded": display["not_included"],
            "itinerary": display["itinerary"],
            "images": display["images"],
            "image": display["image"] or "",
            "scheduledDate": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
            "scheduledMonth": inst.scheduled_month,
            "scheduledYear": inst.scheduled_year,
            "scheduledLabel": scheduled_label,
            "startTime": _format_time(getattr(inst, "start_time", None)),
            "endTime": _format_time(getattr(inst, "end_time", None)),
            "display_order": inst.display_order,
            "interestedCount": _instance_interested_display_count(inst),
            "capacity": getattr(inst, "capacity", None),
            "is_agotado": getattr(inst, "is_agotado", False),
            "isPast": inst.is_past,
            "extra_fields": _serialize_activity_extra_fields(act),
        })


class ErasmusTimelineEntryDetailView(APIView):
    """GET /api/v1/erasmus/timeline/<uuid:entry_id>/ – detail for one timeline entry (ErasmusActivityInstance) by id."""
    permission_classes = [AllowAny]

    def get(self, request, entry_id):
        payload = _get_timeline_entry_payload(entry_id)
        if payload is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.user.is_authenticated:
            lead = getattr(request.user, "erasmus_leads", None)
            if lead is not None:
                lead = request.user.erasmus_leads.order_by("-created_at").first()
                if lead and (lead.interested_experiences or []):
                    ids = [str(x).strip() for x in lead.interested_experiences if x]
                    if str(entry_id) in ids:
                        payload["userIsInterested"] = True
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
        # Destinos de Tuki (panel superadmin): lista para cards en el formulario Erasmus.
        # Resolver imagen hero (hero_media_id o hero_image) con URL absoluta, igual que public/destinations.
        dests = LandingDestination.objects.filter(is_active=True).order_by("country", "name")
        data["destinations_list"] = []
        for d in dests:
            hero_url, _ = _build_destination_media_urls_from_request(d, request)
            data["destinations_list"].append({
                "slug": d.slug,
                "name": d.name,
                "country": d.country or "",
                "image": hero_url or "",
            })
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
    """GET /api/v1/erasmus/whatsapp-groups/ – list of { name, link, image_url?, category } for profile and public page."""
    permission_classes = [AllowAny]

    def get(self, request):
        groups = list(
            ErasmusWhatsAppGroup.objects.filter(is_active=True)
            .order_by("order", "id")
            .values("name", "link", "image_url", "category")
        )
        return Response([
            {
                "name": g["name"],
                "link": g["link"],
                "image_url": g["image_url"] or None,
                "category": g["category"] or "tuki",
            }
            for g in groups
        ])


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
        # Ensure every registration has a flow for observability (e.g. WhatsApp result)
        if flow_id is None:
            try:
                flow = FlowLogger.start_flow(
                    "erasmus_registration",
                    user=None,
                    metadata={"source": "register_no_flow_id"},
                )
                if flow and flow.flow_id:
                    flow_id = flow.flow_id
            except Exception as e:
                logger.warning("Erasmus: start_flow when no flow_id failed (non-blocking): %s", e)
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


def _lead_profile_photo_url(request, lead):
    """Build absolute URL for lead's profile_photo if set."""
    if not lead or not lead.profile_photo:
        return None
    raw = lead.profile_photo.url
    return request.build_absolute_uri(raw) if raw and not raw.startswith(("http://", "https://")) else raw


class ErasmusMyCommunityProfileView(APIView):
    """
    GET/POST /api/v1/erasmus/my-community-profile/
    Authenticated user's Erasmus community profile (from linked lead).
    GET: return current profile. POST: update (multipart: photo + form fields).
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get_lead(self, request):
        lead = getattr(request.user, "erasmus_leads", None)
        if lead is None:
            return None
        return lead.order_by("-created_at").first()

    def get(self, request):
        lead = self._get_lead(request)
        if not lead:
            return Response(
                {"detail": "No tienes un perfil Erasmus vinculado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            "lead_id": str(lead.id),
            "opt_in_community": bool(lead.opt_in_community),
            "profile_photo_url": _lead_profile_photo_url(request, lead),
            "community_bio": (lead.community_bio or "").strip(),
            "instagram": (lead.instagram or "").strip().replace("@", ""),
            "languages_spoken": list(lead.languages_spoken) if lead.languages_spoken else [],
            "community_show_dates": bool(lead.community_show_dates),
            "community_show_age": bool(lead.community_show_age),
            "community_show_whatsapp": bool(lead.community_show_whatsapp),
        }, status=status.HTTP_200_OK)

    def post(self, request):
        lead = self._get_lead(request)
        if not lead:
            return Response(
                {"detail": "No tienes un perfil Erasmus vinculado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        update_fields = ["updated_at"]

        # opt_in_community
        opt_in = request.data.get("opt_in_community")
        if opt_in is not None:
            lead.opt_in_community = bool(opt_in) if not isinstance(opt_in, str) else opt_in.lower() in ("true", "1", "yes")
            update_fields.append("opt_in_community")

        # community_bio
        bio = request.data.get("community_bio") or request.data.get("bio")
        if bio is not None:
            lead.community_bio = (bio if isinstance(bio, str) else str(bio))[:2000]
            update_fields.append("community_bio")

        # instagram (without @)
        instagram = request.data.get("instagram")
        if instagram is not None:
            lead.instagram = (instagram if isinstance(instagram, str) else str(instagram)).strip().replace("@", "")[:100]
            update_fields.append("instagram")

        # profile_photo
        photo = request.FILES.get("profile_photo")
        if photo:
            if photo.size > 5 * 1024 * 1024:
                return Response({"detail": "La imagen no debe superar 5 MB."}, status=status.HTTP_400_BAD_REQUEST)
            lead.profile_photo = photo
            update_fields.append("profile_photo")

        # languages_spoken
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
            update_fields.append("languages_spoken")

        # visibility flags
        for field, key in [
            ("community_show_dates", "community_show_dates"),
            ("community_show_age", "community_show_age"),
            ("community_show_whatsapp", "community_show_whatsapp"),
        ]:
            val = request.data.get(key)
            if val is not None:
                setattr(lead, field, bool(val) if not isinstance(val, str) else val.lower() in ("true", "1", "yes"))
                update_fields.append(field)

        lead.save(update_fields=update_fields)
        return Response({
            "success": True,
            "opt_in_community": lead.opt_in_community,
            "community_bio": lead.community_bio or "",
            "instagram": (lead.instagram or "").strip(),
            "profile_photo_url": _lead_profile_photo_url(request, lead),
            "languages_spoken": lead.languages_spoken or [],
            "community_show_dates": lead.community_show_dates,
            "community_show_age": lead.community_show_age,
            "community_show_whatsapp": lead.community_show_whatsapp,
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
    """POST /api/v1/erasmus/express-interest/ – vincular lead por teléfono e indicar interés en una actividad (instance id)."""
    permission_classes = [AllowAny]

    def post(self, request):
        phone_country_code = (request.data.get("phone_country_code") or "").strip()
        phone_number = (request.data.get("phone_number") or "").strip()
        activity_instance_id = (request.data.get("activity_instance_id") or request.data.get("timeline_item_id") or "").strip()
        activity_id = activity_instance_id
        if not phone_country_code or not phone_number:
            return Response(
                {"detail": "Faltan código de país o número de teléfono."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not activity_id:
            return Response(
                {"detail": "Falta el id de la instancia (activity_instance_id)."},
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
                {
                    "success": False,
                    "detail": "No encontramos un registro Erasmus con ese número. Completa primero el formulario de registro.",
                },
                status=status.HTTP_200_OK,
            )
        instance = ErasmusActivityInstance.objects.filter(
            id=activity_id,
            is_active=True,
            activity__is_active=True,
        ).select_related("activity").first()
        if not instance:
            return Response(
                {"success": False, "detail": "No encontramos esa fecha o actividad."},
                status=status.HTTP_200_OK,
            )
        if instance.is_past:
            return Response(
                {"success": False, "detail": "Esta actividad ya finalizó. No se pueden inscribir más personas."},
                status=status.HTTP_200_OK,
            )
        if getattr(instance, "is_agotado", False):
            return Response(
                {"success": False, "detail": "Esta fecha está agotada. No se aceptan más inscripciones."},
                status=status.HTTP_200_OK,
            )
        if getattr(instance, "capacity", None) is not None:
            current_count = ErasmusLead.objects.filter(
                interested_experiences__contains=[str(instance.id)]
            ).count()
            if current_count >= instance.capacity:
                return Response(
                    {"success": False, "detail": "No quedan cupos para esta fecha."},
                    status=status.HTTP_200_OK,
                )
        activity = instance.activity
        extra_fields = list(
            ErasmusActivityExtraField.objects.filter(activity=activity, is_active=True).order_by("order", "id")
        )
        raw_extra = request.data.get("extra_data")
        if not isinstance(raw_extra, dict):
            raw_extra = {}
        # Validate required activity extra fields
        for ef in extra_fields:
            if ef.required:
                val = raw_extra.get(ef.field_key)
                if val is None:
                    return Response(
                        {"detail": f"Falta el campo requerido: {ef.label}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if isinstance(val, list):
                    if len(val) == 0:
                        return Response(
                            {"detail": f"Falta el campo requerido: {ef.label}."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                elif isinstance(val, str) and not val.strip():
                    return Response(
                        {"detail": f"Falta el campo requerido: {ef.label}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        allowed_keys = {ef.field_key for ef in extra_fields}
        extra_data = {k: v for k, v in raw_extra.items() if k in allowed_keys and v is not None}
        # Normalize values (e.g. list for multiselect, str for others)
        for k in list(extra_data.keys()):
            v = extra_data[k]
            if isinstance(v, list):
                extra_data[k] = v
            else:
                extra_data[k] = str(v).strip() if v is not None else ""
        experiences = list(lead.interested_experiences or [])
        if activity_id not in experiences:
            experiences.append(activity_id)
            lead.interested_experiences = experiences
            lead.save(update_fields=["interested_experiences", "updated_at"])
        reg, _ = ErasmusActivityInstanceRegistration.objects.update_or_create(
            lead=lead,
            instance=instance,
            defaults={"extra_data": extra_data},
        )
        # Free activities: create order+link so WhatsApp send is tracked and "Ver pedido" is available
        if not getattr(activity, "is_paid", False) or not (getattr(activity, "price", None) and activity.price > 0):
            try:
                from apps.erasmus.payment_link_service import get_or_create_order_for_free_inscription
                get_or_create_order_for_free_inscription(lead, instance)
            except Exception as e:
                logger.exception("Erasmus: get_or_create_order_for_free_inscription failed: %s", e)
        try:
            from apps.erasmus.partner_notifications import notify_activity_inscription, send_activity_instance_whatsapp_to_lead
            notify_activity_inscription(lead, instance)
            send_activity_instance_whatsapp_to_lead(lead, instance)
        except Exception as e:
            logger.exception("Erasmus: notify_activity_inscription / send_whatsapp_to_lead failed: %s", e)
        return Response(
            {
                "success": True,
                "message": "Gracias por registrarte. Ya formas parte de la experiencia. Puedes revisar los detalles de tu reserva en tu cuenta. ¡Nos vemos!",
            },
            status=status.HTTP_200_OK,
        )


def _serialize_activity_extra_fields(activity):
    """List of extra field definitions for public form (activity inscription).
    Options may have optional cutoff_iso (ISO datetime in server timezone, or legacy UTC with Z).
    Options past cutoff are excluded. All comparisons use server timezone (America/Santiago).
    """
    from django.utils.dateparse import parse_datetime

    server_tz = timezone.get_current_timezone()
    qs = ErasmusActivityExtraField.objects.filter(activity=activity, is_active=True).order_by("order", "id")
    now = timezone.now()
    result = []
    for ef in qs:
        raw_options = ef.options or []
        options = []
        for opt in raw_options:
            if not isinstance(opt, dict):
                continue
            cutoff_iso = opt.get("cutoff_iso")
            if cutoff_iso:
                cutoff_dt = parse_datetime(cutoff_iso)
                if cutoff_dt:
                    if timezone.is_naive(cutoff_dt):
                        cutoff_dt = timezone.make_aware(cutoff_dt, server_tz)
                    else:
                        cutoff_dt = cutoff_dt.astimezone(server_tz)
                    if now >= cutoff_dt:
                        continue
            options.append({"value": opt.get("value", ""), "label": opt.get("label", "")})
        result.append({
            "field_key": ef.field_key,
            "label": ef.label,
            "type": ef.type,
            "required": ef.required,
            "placeholder": ef.placeholder or "",
            "help_text": ef.help_text or "",
            "options": options,
        })
    return result


def _get_timeline_entry_payload(entry_id):
    """Detalle de un entry del timeline por id. Solo ErasmusActivityInstance (actividad instanciada). Uses display data when activity is linked to Experience."""
    try:
        inst = ErasmusActivityInstance.objects.select_related("activity", "activity__experience").get(
            id=entry_id,
            is_active=True,
            activity__is_active=True,
        )
    except (ErasmusActivityInstance.DoesNotExist, ValueError):
        return None
    act = inst.activity
    display = get_activity_display_data(act)
    scheduled_label = None
    if inst.scheduled_label_es or inst.scheduled_label_en:
        scheduled_label = {"es": inst.scheduled_label_es or "", "en": inst.scheduled_label_en or inst.scheduled_label_es or ""}
    display_count = _instance_interested_display_count(inst)
    capacity = getattr(inst, "capacity", None)
    is_agotado = getattr(inst, "is_agotado", False)
    return {
        "id": str(inst.id),
        "itemType": "instance",
        "activityId": str(act.id),
        "experienceId": str(act.experience_id) if act.experience_id else None,
        "title": {"es": display["title_es"], "en": display["title_en"]},
        "description": {"es": display["description_es"], "en": display["description_en"]},
        "short_description": {"es": display["short_description_es"], "en": display["short_description_en"]},
        "location": display["location"] or "",
        "locationName": display["location_name"] or "",
        "locationAddress": display["location_address"] or "",
        "durationMinutes": display["duration_minutes"],
        "included": display["included"],
        "notIncluded": display["not_included"],
        "itinerary": display["itinerary"],
        "images": display["images"],
        "capacity": capacity,
        "is_agotado": is_agotado,
        "image": display["image"] or "",
        "scheduledDate": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
        "scheduledMonth": inst.scheduled_month,
        "scheduledYear": inst.scheduled_year,
        "scheduledLabel": scheduled_label,
        "startTime": _format_time(getattr(inst, "start_time", None)),
        "endTime": _format_time(getattr(inst, "end_time", None)),
        "display_order": inst.display_order,
        "interestedCount": display_count,
        "isPast": inst.is_past,
        "detailLayout": getattr(act, "detail_layout", "default") or "default",
        "instructions_es": getattr(inst, "instructions_es", "") or "",
        "instructions_en": getattr(inst, "instructions_en", "") or "",
        "whatsapp_message_es": getattr(inst, "whatsapp_message_es", "") or "",
        "whatsapp_message_en": getattr(inst, "whatsapp_message_en", "") or "",
        "extra_fields": _serialize_activity_extra_fields(act),
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
