"""
Public API for contests/sorteos: GET contest by slug, GET terms, POST register.
Registration creates a flow and a participation code (WhatsApp confirmation).
"""
import logging
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from apps.erasmus.models import (
    Contest,
    ContestSlideConfig,
    ContestExtraField,
    ContestRegistration,
    ContestParticipationCode,
)
from apps.erasmus.contest_services import (
    generate_contest_code,
    render_contest_whatsapp_message,
)
from core.flow_logger import FlowLogger

logger = logging.getLogger(__name__)


def _contest_visible(contest: Contest) -> bool:
    """Contest is visible if active and within optional date range."""
    if not contest.is_active:
        return False
    now = timezone.now()
    if contest.starts_at and now < contest.starts_at:
        return False
    if contest.ends_at and now > contest.ends_at:
        return False
    return True


def _build_asset_url(request, asset) -> str | None:
    """Build absolute URL for a media asset."""
    if not asset or getattr(asset, "deleted_at", None):
        return None
    raw_url = getattr(asset, "url", None) if asset else None
    if not raw_url:
        return None
    if raw_url.startswith(("http://", "https://")):
        return raw_url
    path = raw_url.lstrip("/")
    return request.build_absolute_uri(f"/{path}" if path else "/")


class ContestDetailView(APIView):
    """GET /api/v1/contests/<slug>/ – public contest detail (slides, experience summary, extra_fields, requirements)."""
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            contest = Contest.objects.select_related("experience").get(slug=slug)
        except Contest.DoesNotExist:
            return Response({"detail": "Concurso no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if not _contest_visible(contest):
            return Response({"detail": "Concurso no disponible."}, status=status.HTTP_404_NOT_FOUND)

        # Slides
        slides = []
        for cfg in (
            ContestSlideConfig.objects.filter(contest=contest, asset__isnull=False)
            .select_related("asset")
            .order_by("order", "id")
        ):
            if getattr(cfg.asset, "deleted_at", None):
                continue
            url = _build_asset_url(request, cfg.asset)
            if url:
                slides.append({"url": url, "caption": cfg.caption or ""})

        # Experience summary
        experience_summary = None
        if contest.experience_id:
            exp = contest.experience
            first_image = None
            images = getattr(exp, "images", None) or []
            if images:
                first_item = images[0]
                if isinstance(first_item, str):
                    first_image = first_item if first_item.startswith(("http", "/")) else None
                elif isinstance(first_item, dict) and first_item.get("url"):
                    first_image = first_item["url"]
            experience_summary = {
                "id": str(exp.id),
                "title": exp.title,
                "slug": exp.slug,
                "first_image": first_image,
                "short_description": (getattr(exp, "short_description", None) or "")[:300],
                "detail_url": f"/experiences/public/{exp.slug}/",
                "included": getattr(exp, "included", None) if isinstance(getattr(exp, "included", None), list) else [],
                "not_included": getattr(exp, "not_included", None) if isinstance(getattr(exp, "not_included", None), list) else [],
            }

        # Extra fields for form
        extra_fields = list(
            ContestExtraField.objects.filter(contest=contest, is_active=True)
            .order_by("order", "id")
            .values("field_key", "label", "type", "required", "placeholder", "help_text", "options")
        )

        return Response({
            "slug": contest.slug,
            "title": contest.title,
            "subtitle": contest.subtitle,
            "headline": contest.headline,
            "requirements_html": contest.requirements_html or "",
            "slides": slides,
            "experience": experience_summary,
            "extra_fields": extra_fields,
            "is_active": contest.is_active,
        })


class ContestTermsView(APIView):
    """GET /api/v1/contests/<slug>/terms/ – HTML terms and conditions for the contest."""
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            contest = Contest.objects.get(slug=slug)
        except Contest.DoesNotExist:
            return Response({"detail": "Concurso no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if not _contest_visible(contest):
            return Response({"detail": "Concurso no disponible."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"html": contest.terms_and_conditions_html or ""})


class ContestRegisterView(APIView):
    """POST /api/v1/contests/<slug>/register/ – register for contest; creates flow and participation code (WhatsApp)."""
    permission_classes = [AllowAny]

    def post(self, request, slug):
        try:
            contest = Contest.objects.get(slug=slug)
        except Contest.DoesNotExist:
            return Response({"detail": "Concurso no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if not _contest_visible(contest):
            return Response({"detail": "Concurso no disponible."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        first_name = (data.get("first_name") or "").strip()
        last_name = (data.get("last_name") or "").strip()
        if not first_name or not last_name:
            return Response(
                {"detail": "Nombre y apellido son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = (data.get("email") or "").strip() or None
        phone_country_code = (data.get("phone_country_code") or "").strip() or ""
        phone_number = (data.get("phone_number") or "").strip() or ""
        extra_data = data.get("extra_data")
        if not isinstance(extra_data, dict):
            extra_data = {}
        accept_terms = bool(data.get("accept_terms"))

        if not accept_terms:
            return Response(
                {"detail": "Debes aceptar los términos y condiciones para participar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate extra_data against ContestExtraField
        extra_field_keys = set(
            ContestExtraField.objects.filter(contest=contest, is_active=True).values_list("field_key", flat=True)
        )
        allowed_extra = {k: v for k, v in extra_data.items() if k in extra_field_keys}
        required_keys = set(
            ContestExtraField.objects.filter(contest=contest, is_active=True, required=True).values_list("field_key", flat=True)
        )
        missing = required_keys - set(allowed_extra.keys())
        if missing:
            return Response(
                {"detail": f"Faltan campos obligatorios: {', '.join(sorted(missing))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            flow = FlowLogger.start_flow(
                "contest_registration",
                user=None,
                organizer=contest.experience.organizer if contest.experience_id else None,
                experience=contest.experience,
                metadata={
                    "contest_id": str(contest.id),
                    "contest_slug": contest.slug,
                },
            )
            flow_obj = flow.flow if flow else None
        except Exception as e:
            logger.warning("Contest register: start_flow failed (non-blocking): %s", e)
            flow_obj = None

        registration = ContestRegistration.objects.create(
            contest=contest,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone_country_code=phone_country_code,
            phone_number=phone_number,
            extra_data=allowed_extra,
            accept_terms=True,
            flow=flow_obj,
        )

        code_str = generate_contest_code(contest)
        ContestParticipationCode.objects.create(
            contest=contest,
            registration=registration,
            code=code_str,
            status="pending",
            flow=flow_obj,
        )

        if flow_obj:
            flow = FlowLogger(flow_obj)
            flow.log_event(
                "CONTEST_REGISTRATION_CREATED",
                source="api",
                status="success",
                message=f"Registration and code {code_str} created",
                metadata={"registration_id": registration.id, "code": code_str},
            )

        # WhatsApp number from settings or default Tuki
        from django.conf import settings as django_settings
        whatsapp_number = getattr(django_settings, "TUKI_WHATSAPP_NUMBER", "") or getattr(django_settings, "TUKI_WHATSAPP", "")
        whatsapp_link = ""
        if whatsapp_number:
            import urllib.parse
            msg = f"Hola, mi código de participación es: {code_str}"
            whatsapp_link = f"https://wa.me/{whatsapp_number.replace(' ', '').replace('+', '')}?text={urllib.parse.quote(msg)}"

        return Response(
            {
                "success": True,
                "message": "Gracias por inscribirte. Envía tu código por WhatsApp para confirmar tu participación.",
                "code": code_str,
                "whatsapp_link": whatsapp_link,
            },
            status=status.HTTP_201_CREATED,
        )
