"""Public API views for Erasmus registration and options."""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.flow_logger import FlowLogger
from apps.erasmus.models import ErasmusDestinationGuide, ErasmusExtraField
from apps.erasmus.options_data import get_erasmus_options
from apps.erasmus.services import get_guides_for_destinations
from apps.landing_destinations.models import LandingDestination
from .serializers import ErasmusRegisterSerializer

logger = logging.getLogger(__name__)


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
        return Response(data)


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
        return Response(
            {"success": True, "message": "Gracias por inscribirte. Te hemos enviado por WhatsApp las guías de los destinos que elegiste. También quedarán en tu perfil."},
            status=status.HTTP_201_CREATED,
        )


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
