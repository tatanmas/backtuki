"""Superadmin views for Erasmus: leads, tracking links, extra fields (dynamic form questions)."""

import csv
import json
import logging
from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.superadmin.permissions import IsSuperUser
from apps.erasmus.models import (
    ErasmusLead,
    ErasmusTrackingLink,
    ErasmusExtraField,
    ErasmusDestinationGuide,
    ErasmusLocalPartner,
    ErasmusTimelineItem,
    ErasmusActivity,
    ErasmusActivityExtraField,
    ErasmusActivityInstance,
    ErasmusActivityInstanceRegistration,
    ErasmusActivityPublicLink,
    ErasmusActivityReview,
    ErasmusActivityInscriptionPayment,
    ErasmusWhatsAppGroup,
    ErasmusPartnerNotificationConfig,
    ErasmusActivityNotificationConfig,
    ErasmusWelcomeMessageConfig,
)
from apps.whatsapp.models import WhatsAppChat
from apps.media.models import MediaAsset
from apps.erasmus.whatsapp_og import fetch_whatsapp_group_image
from apps.experiences.models import Experience
from apps.erasmus.lead_import import (
    normalize_lead,
    REQUIRED_KEYS_FULL,
    REQUIRED_KEYS_INCOMPLETE,
)
from rest_framework.exceptions import ValidationError as DRFValidationError
from api.v1.superadmin.serializers import (
    JsonErasmusTimelineItemSerializer,
    JsonErasmusActivityCreateSerializer,
    JsonErasmusActivityInstanceSerializer,
    validate_itinerary_items,
)

logger = logging.getLogger(__name__)

# Claves que el formulario guarda en extra_data pero no están en ErasmusExtraField (quiz + Rumi).
# Incluirlas aquí para que CSV y tabla superadmin muestren siempre estas columnas con label legible.
FIXED_EXTRA_KEYS_META = (
    # Quiz perfil
    ("quiz_avoid", "Quiz: qué evitar"),
    ("quiz_social", "Quiz: social"),
    ("quiz_physical", "Quiz: actividad física"),
    ("quiz_saturday", "Quiz: sábado"),
    ("quiz_travel_style", "Quiz: estilo de viaje"),
    ("quiz_accommodation", "Quiz: alojamiento"),
    # Rumi / alojamiento (zona, presupuesto, tipos)
    ("accommodation_help_types", "Rumi: tipos de alojamiento"),
    ("accommodation_help_where", "Rumi: zona donde vivir"),
    ("accommodation_help_budget_monthly", "Rumi: presupuesto mensual"),
)

# Mapeo value -> label (español) para convertir respuestas del quiz y Rumi en el CSV a texto legible.
FIXED_EXTRA_OPTIONS_LABELS = {
    "quiz_accommodation": {
        "camping": "Tienda de campaña o camping",
        "hostel_shared": "Habitación compartida en hostel",
        "hostel_private": "Habitación privada en hostel o guesthouse",
        "hotel_apartment": "Hotel o departamento privado",
    },
    "quiz_saturday": {
        "nature": "Caminar por naturaleza, cerros o senderos",
        "beach": "Día de playa o actividades en el mar",
        "city": "Recorrer ciudad, arquitectura, museos o barrios",
        "food": "Probar comida local, cafés, mercados o vino",
        "sport": "Hacer deporte, entrenamiento o actividades físicas",
        "nightlife": "Música en vivo, bares, fiestas o vida nocturna",
        "relax": "Un plan tranquilo para descansar y conversar",
        "sunset": "Ver puesta del sol en dunas o cerro",
    },
    "quiz_physical": {
        "suave": "Suave, caminatas cortas y terreno fácil",
        "medio": "Medio, actividades de varias horas con algo de exigencia",
        "alto": "Alto, día completo y cansancio fuerte",
        "muy_alto": "Muy alto, rutas técnicas o condiciones exigentes",
    },
    "quiz_social": {
        "grupo_grande": "Conocer mucha gente, me gusta el grupo grande",
        "grupo_mediano": "Grupo mediano, me gusta conversar pero sin tanta gente",
        "grupo_pequeno": "Grupo pequeño, prefiero planes tranquilos",
        "solo_pocos": "Prefiero recomendaciones para hacer por mi cuenta o con pocas personas",
    },
    "quiz_travel_style": {
        "planificar_maximo": "Me gusta planificar y aprovechar al máximo el tiempo",
        "planificar_tranquilo": "Me gusta planificar, pero con ritmo tranquilo",
        "improvisar_mucho": "Me gusta decidir en el momento y hacer muchas cosas",
        "improvisar_relajado": "Me gusta decidir en el momento y mantenerlo relajado",
    },
    "quiz_avoid": {
        "altura": "Altura o exposición",
        "agua": "Agua o mar",
        "frio": "Frío o nieve",
        "fisico_intenso": "Actividad física intensa",
        "camping": "Camping",
        "vida_nocturna": "Vida nocturna",
        "viajes_largos": "Viajes largos por carretera",
    },
    "accommodation_help_types": {
        "alone": "Quiero un lugar solo (casa/departamento para mí)",
        "shared_students": "Quiero compartir con otros estudiantes (nacionales o internacionales)",
        "residence": "Quiero una residencia (estilo estudiante)",
        "family_chile": "Quiero vivir con una familia chilena",
    },
}


def _extra_value_to_csv_display(raw, field_key, extra_field_options_by_key):
    """Convierte el valor guardado (código) a texto legible para el CSV usando opciones del form."""
    if raw is None or raw == "":
        return ""
    opt_map = FIXED_EXTRA_OPTIONS_LABELS.get(field_key) or extra_field_options_by_key.get(field_key) or {}
    if not opt_map:
        # Sin mapeo: texto libre o legacy
        if isinstance(raw, list):
            return ", ".join(str(x) for x in raw)
        if isinstance(raw, dict):
            return json.dumps(raw, ensure_ascii=False)
        return str(raw)
    # Mapear valor(es) a label
    if isinstance(raw, list):
        return ", ".join(opt_map.get(v, str(v)) for v in raw)
    return opt_map.get(raw, str(raw))


def _lead_to_dict(lead):
    """Serialize one ErasmusLead for API (handles null dates and completion_status)."""
    return {
        "id": str(lead.id),
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "nickname": lead.nickname or "",
        "birth_date": str(lead.birth_date) if lead.birth_date else "",
        "country": lead.country or "",
        "city": lead.city or "",
        "email": lead.email or "",
        "phone_country_code": lead.phone_country_code,
        "phone_number": lead.phone_number,
        "instagram": lead.instagram or "",
        "stay_reason": lead.stay_reason,
        "stay_reason_detail": lead.stay_reason_detail or "",
        "university": lead.university or "",
        "degree": lead.degree or "",
        "arrival_date": str(lead.arrival_date) if lead.arrival_date else "",
        "departure_date": str(lead.departure_date) if lead.departure_date else "",
        "budget_stay": lead.budget_stay or "",
        "has_accommodation_in_chile": lead.has_accommodation_in_chile,
        "wants_rumi4students_contact": lead.wants_rumi4students_contact,
        "destinations": lead.destinations,
        "interested_experiences": getattr(lead, "interested_experiences", []) or [],
        "interests": lead.interests,
        "source_slug": lead.source_slug or "",
        "utm_source": lead.utm_source or "",
        "utm_medium": lead.utm_medium or "",
        "utm_campaign": lead.utm_campaign or "",
        "extra_data": lead.extra_data,
        "accept_tc_erasmus": lead.accept_tc_erasmus,
        "accept_privacy_erasmus": lead.accept_privacy_erasmus,
        "consent_email": lead.consent_email,
        "consent_whatsapp": lead.consent_whatsapp,
        "consent_share_providers": lead.consent_share_providers,
        "completion_status": getattr(lead, "completion_status", "complete"),
        "is_suspended": getattr(lead, "is_suspended", False),
        "created_at": lead.created_at.isoformat() if lead.created_at else "",
        "form_locale": getattr(lead, "form_locale", "") or "es",
        "opt_in_community": getattr(lead, "opt_in_community", False),
        "community_bio": getattr(lead, "community_bio", "") or "",
        "languages_spoken": getattr(lead, "languages_spoken", []) or [],
        "community_show_dates": getattr(lead, "community_show_dates", True),
        "community_show_age": getattr(lead, "community_show_age", True),
        "community_show_whatsapp": getattr(lead, "community_show_whatsapp", False),
        "user_id": str(lead.user_id) if lead.user_id else None,
        "is_activated": bool(lead.user_id),
    }


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
            return _export_leads_csv(qs)

        # Pagination-friendly list
        page = int(request.query_params.get("page", 1))
        page_size = min(int(request.query_params.get("page_size", 50)), 200)
        start = (page - 1) * page_size
        end = start + page_size
        leads = qs[start:end]
        data = []
        for lead in leads:
            data.append(_lead_to_dict(lead))
        # Metadata for extra_data keys so frontend can show all questions with labels (ErasmusExtraField + fijas quiz/Rumi)
        extra_fields_meta = list(
            ErasmusExtraField.objects.filter(is_active=True).order_by("order", "id").values("field_key", "label")
        )
        for key, label in FIXED_EXTRA_KEYS_META:
            extra_fields_meta.append({"field_key": key, "label": label})
        return Response({
            "results": data,
            "count": qs.count(),
            "extra_fields_meta": extra_fields_meta,
        })


    def _export_csv(self, qs):
        return _export_leads_csv(qs)


def _export_leads_csv(qs):
    """Build CSV for Erasmus leads (all fixed fields + extra_data as columns).
    Cabeceras y celdas usan las mismas etiquetas que en el form (no claves técnicas).
    """
    # 1) Labels for extra columns + value->label para ErasmusExtraField (select/multiselect)
    extra_label_by_key = {}
    extra_field_options_by_key = {}  # field_key -> {value: label} para convertir respuestas a texto
    for row in ErasmusExtraField.objects.filter(is_active=True).order_by("order", "id").values(
        "field_key", "label", "type", "options"
    ):
        extra_label_by_key[row["field_key"]] = row["label"]
        opts = row.get("options") or []
        if opts and row.get("type") in ("select", "multiselect", "radio"):
            extra_field_options_by_key[row["field_key"]] = {
                str(o.get("value")): o.get("label", o.get("value"))
                for o in opts
                if isinstance(o, dict) and "value" in o
            }
    for key, label in FIXED_EXTRA_KEYS_META:
        extra_label_by_key[key] = label
    # 2) Column order: model first, then fixed, then legacy from leads
    extra_from_model = list(
        ErasmusExtraField.objects.filter(is_active=True).order_by("order", "id").values_list("field_key", flat=True)
    )
    extra_keys_ordered = list(extra_from_model)
    seen = set(extra_keys_ordered)
    for key, _label in FIXED_EXTRA_KEYS_META:
        if key not in seen:
            seen.add(key)
            extra_keys_ordered.append(key)
    for lead in qs.order_by("-created_at")[:5000]:
        ed = lead.extra_data or {}
        for k in ed.keys():
            if k not in seen:
                seen.add(k)
                extra_keys_ordered.append(k)
    # Headers: base + labels como en el form (legacy sin label = key)
    extra_headers = [extra_label_by_key.get(k, k) for k in extra_keys_ordered]
    base_headers = [
        "id", "first_name", "last_name", "nickname", "birth_date", "country", "city", "email",
        "phone_country_code", "phone_number", "instagram", "form_locale",
        "stay_reason", "stay_reason_detail", "university", "degree",
        "arrival_date", "departure_date", "budget_stay",
        "has_accommodation_in_chile", "wants_rumi4students_contact",
        "destinations", "interested_experiences", "interests",
        "source_slug", "utm_source", "utm_medium", "utm_campaign",
        "accept_tc_erasmus", "accept_privacy_erasmus", "consent_email", "consent_whatsapp", "consent_share_providers",
        "completion_status", "is_suspended", "created_at",
        "opt_in_community", "community_bio", "languages_spoken",
        "community_show_dates", "community_show_age", "community_show_whatsapp",
    ]
    headers = base_headers + extra_headers
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="erasmus-leads.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for lead in qs:
        ed = lead.extra_data or {}
        base_row = [
            lead.id, lead.first_name, lead.last_name, lead.nickname or "", lead.birth_date or "",
            lead.country or "", lead.city or "", lead.email or "", lead.phone_country_code, lead.phone_number,
            lead.instagram or "", getattr(lead, "form_locale", "") or "",
            lead.stay_reason, lead.stay_reason_detail or "", lead.university or "", lead.degree or "",
            lead.arrival_date or "", lead.departure_date or "",
            lead.budget_stay or "",
            getattr(lead, "has_accommodation_in_chile", False),
            getattr(lead, "wants_rumi4students_contact", False),
            json.dumps(lead.destinations, ensure_ascii=False),
            json.dumps(getattr(lead, "interested_experiences", []) or [], ensure_ascii=False),
            json.dumps(lead.interests, ensure_ascii=False),
            lead.source_slug or "", lead.utm_source or "", lead.utm_medium or "", lead.utm_campaign or "",
            getattr(lead, "accept_tc_erasmus", False), getattr(lead, "accept_privacy_erasmus", False),
            getattr(lead, "consent_email", False), getattr(lead, "consent_whatsapp", False),
            getattr(lead, "consent_share_providers", False),
            getattr(lead, "completion_status", "complete"), getattr(lead, "is_suspended", False),
            lead.created_at.isoformat() if lead.created_at else "",
            getattr(lead, "opt_in_community", False), getattr(lead, "community_bio", "") or "",
            json.dumps(getattr(lead, "languages_spoken", []) or [], ensure_ascii=False),
            getattr(lead, "community_show_dates", True), getattr(lead, "community_show_age", True),
            getattr(lead, "community_show_whatsapp", False),
        ]
        extra_row = [
            _extra_value_to_csv_display(ed.get(k), k, extra_field_options_by_key)
            for k in extra_keys_ordered
        ]
        writer.writerow(base_row + extra_row)
    return response


class ErasmusLeadsExportView(APIView):
    """GET /api/v1/superadmin/erasmus/leads/export/ – CSV export (same filters as list)."""
    permission_classes = [IsSuperUser]

    def get(self, request):
        qs = ErasmusLead.objects.all().order_by("-created_at")
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
        return _export_leads_csv(qs)


def _this_week_range():
    """Return (start, end) for current week (Monday–Sunday) and next 7 days for arrivals."""
    today = date.today()
    # Week start = last Monday
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


class ErasmusDashboardView(APIView):
    """GET /api/v1/superadmin/erasmus/dashboard/ – arriving this week, birthdays this week, recent stats."""
    permission_classes = [IsSuperUser]

    def get(self, request):
        today = date.today()
        week_start, week_end = _this_week_range()
        next_week_end = today + timedelta(days=7)

        # Llegando esta semana: arrival_date between today and today+7 (or in current week if you prefer)
        arriving_qs = ErasmusLead.objects.filter(
            arrival_date__isnull=False,
            arrival_date__gte=today,
            arrival_date__lte=next_week_end,
        ).order_by("arrival_date")
        arriving = [_lead_to_dict(lead) for lead in arriving_qs[:50]]

        # Cumpleaños de la semana: birth_date in current week (use month-day for “this week” birthdays)
        def in_week(d):
            if d is None:
                return False
            try:
                this_year_d = d.replace(year=today.year)
                return week_start <= this_year_d <= week_end
            except ValueError:
                return False  # 29 feb
        all_with_birth = ErasmusLead.objects.filter(birth_date__isnull=False).order_by("birth_date__month", "birth_date__day")
        birthdays = [_lead_to_dict(lead) for lead in all_with_birth if in_week(lead.birth_date)][:50]

        # Registros recientes (últimos 7 días)
        recent_start = today - timedelta(days=7)
        recent_count = ErasmusLead.objects.filter(created_at__date__gte=recent_start).count()

        return Response({
            "arriving_this_week": arriving,
            "birthdays_this_week": birthdays,
            "recent_count": recent_count,
            "week_start": str(week_start),
            "week_end": str(week_end),
        })


class ErasmusLeadDetailView(APIView):
    """GET /api/v1/superadmin/erasmus/leads/<id>/ – one lead (for pre-fill). PATCH – update lead (complete form)."""
    permission_classes = [IsSuperUser]

    def get(self, request, lead_id):
        try:
            lead = ErasmusLead.objects.get(id=lead_id)
        except (ErasmusLead.DoesNotExist, ValueError):
            return Response({"detail": "Lead no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        extra_fields_meta = list(
            ErasmusExtraField.objects.filter(is_active=True).order_by("order", "id").values("field_key", "label")
        )
        for key, label in FIXED_EXTRA_KEYS_META:
            extra_fields_meta.append({"field_key": key, "label": label})
        payload = _lead_to_dict(lead)
        payload["extra_fields_meta"] = extra_fields_meta
        return Response(payload)

    def patch(self, request, lead_id):
        try:
            lead = ErasmusLead.objects.get(id=lead_id)
        except (ErasmusLead.DoesNotExist, ValueError):
            return Response({"detail": "Lead no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data or {}
        # Allowed fields for update (same as registration form)
        from django.utils.dateparse import parse_date
        if "first_name" in data:
            lead.first_name = (data["first_name"] or "").strip()[:150]
        if "last_name" in data:
            lead.last_name = (data["last_name"] or "").strip()[:150]
        if "nickname" in data:
            lead.nickname = (data["nickname"] or "").strip()[:100]
        if "birth_date" in data:
            val = parse_date(data["birth_date"]) if isinstance(data["birth_date"], str) else data["birth_date"]
            lead.birth_date = val
        if "country" in data:
            lead.country = (data["country"] or "").strip()[:100]
        if "city" in data:
            lead.city = (data["city"] or "").strip()[:150]
        if "email" in data:
            lead.email = (data["email"] or "").strip() or None
        if "phone_country_code" in data:
            lead.phone_country_code = (data["phone_country_code"] or "").strip()[:10]
        if "phone_number" in data:
            lead.phone_number = (data["phone_number"] or "").strip()[:20]
        if "instagram" in data:
            lead.instagram = (data["instagram"] or "").strip().lstrip("@")[:100]
        if "stay_reason" in data and data["stay_reason"] in ("university", "practicas", "other"):
            lead.stay_reason = data["stay_reason"]
        if "stay_reason_detail" in data:
            lead.stay_reason_detail = (data["stay_reason_detail"] or "").strip()[:500]
        if "university" in data:
            lead.university = (data["university"] or "").strip()[:255]
        if "degree" in data:
            lead.degree = (data["degree"] or "").strip()[:255]
        if "arrival_date" in data:
            val = parse_date(data["arrival_date"]) if isinstance(data["arrival_date"], str) else data["arrival_date"]
            lead.arrival_date = val
        if "departure_date" in data:
            val = parse_date(data["departure_date"]) if isinstance(data["departure_date"], str) else data["departure_date"]
            lead.departure_date = val
        if "budget_stay" in data:
            lead.budget_stay = (data["budget_stay"] or "").strip()[:200]
        if "has_accommodation_in_chile" in data:
            lead.has_accommodation_in_chile = bool(data["has_accommodation_in_chile"])
        if "wants_rumi4students_contact" in data:
            lead.wants_rumi4students_contact = bool(data["wants_rumi4students_contact"])
        if "destinations" in data and isinstance(data["destinations"], list):
            lead.destinations = [str(x)[:100] for x in data["destinations"]]
        if "interested_experiences" in data and isinstance(data["interested_experiences"], list):
            lead.interested_experiences = [str(x)[:100] for x in data["interested_experiences"]]
        if "interests" in data and isinstance(data["interests"], list):
            lead.interests = [str(x)[:100] for x in data["interests"]]
        if "extra_data" in data and isinstance(data["extra_data"], dict):
            lead.extra_data = data["extra_data"]
        if "accept_tc_erasmus" in data:
            lead.accept_tc_erasmus = bool(data["accept_tc_erasmus"])
        if "accept_privacy_erasmus" in data:
            lead.accept_privacy_erasmus = bool(data["accept_privacy_erasmus"])
        if "consent_email" in data:
            lead.consent_email = bool(data["consent_email"])
        if "consent_whatsapp" in data:
            lead.consent_whatsapp = bool(data["consent_whatsapp"])
        if "consent_share_providers" in data:
            lead.consent_share_providers = bool(data["consent_share_providers"])
        if "form_locale" in data:
            lead.form_locale = (data["form_locale"] or "").strip()[:10] or "es"
        if "opt_in_community" in data:
            lead.opt_in_community = bool(data["opt_in_community"])
        if "community_bio" in data:
            lead.community_bio = (data["community_bio"] or "").strip()
        if "languages_spoken" in data and isinstance(data["languages_spoken"], list):
            lead.languages_spoken = [str(x)[:20] for x in data["languages_spoken"]]
        if "community_show_dates" in data:
            lead.community_show_dates = bool(data["community_show_dates"])
        if "community_show_age" in data:
            lead.community_show_age = bool(data["community_show_age"])
        if "community_show_whatsapp" in data:
            lead.community_show_whatsapp = bool(data["community_show_whatsapp"])
        lead.completion_status = "complete"
        update_fields = [
            "first_name", "last_name", "nickname", "birth_date", "country", "city", "email",
            "phone_country_code", "phone_number", "instagram",
            "stay_reason", "stay_reason_detail", "university", "degree",
            "arrival_date", "departure_date", "budget_stay",
            "has_accommodation_in_chile", "wants_rumi4students_contact",
            "destinations", "interested_experiences", "interests", "extra_data",
            "accept_tc_erasmus", "accept_privacy_erasmus", "consent_email", "consent_whatsapp", "consent_share_providers",
            "form_locale", "opt_in_community", "community_bio", "languages_spoken",
            "community_show_dates", "community_show_age", "community_show_whatsapp",
            "completion_status", "updated_at",
        ]
        if "is_suspended" in data:
            lead.is_suspended = bool(data["is_suspended"])
            update_fields.append("is_suspended")
            # Al suspender/reactivar, desactivar/activar el usuario enlazado
            if lead.user_id:
                lead.user.is_active = not lead.is_suspended
                lead.user.save(update_fields=["is_active"])
        lead.save(update_fields=update_fields)
        return Response(_lead_to_dict(lead))

    def delete(self, request, lead_id):
        """DELETE lead y todo lo relacionado en cascada; si tiene usuario invitado solo para este lead, se borra también."""
        try:
            lead = ErasmusLead.objects.get(id=lead_id)
        except (ErasmusLead.DoesNotExist, ValueError):
            return Response({"detail": "Lead no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        user = lead.user
        # Borrar lead (ErasmusMagicLink tiene on_delete=CASCADE)
        lead.delete()
        # Si tenía usuario invitado y era el único lead de ese usuario, borrar el usuario
        if user and getattr(user, "is_guest", False):
            if not ErasmusLead.objects.filter(user=user).exists():
                user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ErasmusLeadWelcomeMessageView(APIView):
    """GET /api/v1/superadmin/erasmus/leads/<id>/welcome-message/ – genera mensaje de bienvenida para copiar y enviar manualmente."""
    permission_classes = [IsSuperUser]

    def get(self, request, lead_id):
        try:
            lead = ErasmusLead.objects.get(id=lead_id)
        except (ErasmusLead.DoesNotExist, ValueError):
            return Response({"detail": "Lead no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        from apps.erasmus.access_code_service import (
            get_or_create_manual_welcome_link,
            get_welcome_message_text,
        )

        _magic, magic_link_url = get_or_create_manual_welcome_link(lead)
        message = get_welcome_message_text(lead, magic_link_url)

        phone = (lead.phone_country_code or "").replace(" ", "") + (lead.phone_number or "").replace(" ", "")
        if phone and not phone.startswith("+"):
            phone = "+" + phone

        return Response({
            "message": message,
            "magic_link_url": magic_link_url,
            "phone": phone or "",
        })


# Placeholders available in welcome message templates (same as in access_code_service)
ERASMUS_WELCOME_PLACEHOLDERS = [
    {"key": "first_name", "description": "Nombre del lead"},
    {"key": "link_plataforma", "description": "URL del enlace mágico para acceder a la cuenta"},
    {"key": "magic_link_url", "description": "Igual que link_plataforma"},
    {"key": "email", "description": "Correo del lead"},
]


class ErasmusWelcomeMessageTemplatesView(APIView):
    """
    GET /api/v1/superadmin/erasmus/welcome-message-templates/
    Returns current templates by locale (from DB or default) and list of placeholders.

    PATCH /api/v1/superadmin/erasmus/welcome-message-templates/
    Body: { "messages": { "es": "...", "en": "...", ... } }
    Updates stored templates. Only provided locales are updated; empty string clears that locale (fallback to default).
    """
    permission_classes = [IsSuperUser]

    def get(self, request):
        from apps.erasmus.access_code_service import WELCOME_LOCALES, WELCOME_MESSAGES_DEFAULT

        config = ErasmusWelcomeMessageConfig.objects.filter(
            config_key=ErasmusWelcomeMessageConfig.CONFIG_KEY
        ).first()
        stored = (config.messages_by_locale if config else None) or {}
        # Merge: for each locale return stored if non-empty, else default
        messages = {}
        for loc in WELCOME_LOCALES:
            custom = (stored.get(loc) or "").strip()
            if custom:
                messages[loc] = custom
            else:
                messages[loc] = WELCOME_MESSAGES_DEFAULT.get(loc) or WELCOME_MESSAGES_DEFAULT.get("es") or ""

        return Response({
            "messages": messages,
            "locales": list(WELCOME_LOCALES),
            "placeholders": ERASMUS_WELCOME_PLACEHOLDERS,
        })

    def patch(self, request):
        from apps.erasmus.access_code_service import WELCOME_LOCALES

        data = request.data or {}
        messages_input = data.get("messages")
        if not isinstance(messages_input, dict):
            return Response(
                {"detail": "Se requiere 'messages' (objeto locale -> texto)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config, _ = ErasmusWelcomeMessageConfig.objects.get_or_create(
            config_key=ErasmusWelcomeMessageConfig.CONFIG_KEY,
            defaults={"messages_by_locale": {}},
        )
        current = dict(config.messages_by_locale or {})
        for loc in WELCOME_LOCALES:
            if loc in messages_input:
                val = messages_input[loc]
                if isinstance(val, str):
                    if val.strip():
                        current[loc] = val.strip()
                    else:
                        current.pop(loc, None)
        config.messages_by_locale = current
        config.save(update_fields=["messages_by_locale", "updated_at"])

        # Return same shape as GET
        stored = config.messages_by_locale or {}
        messages = {}
        from apps.erasmus.access_code_service import WELCOME_MESSAGES_DEFAULT
        for loc in WELCOME_LOCALES:
            custom = (stored.get(loc) or "").strip()
            if custom:
                messages[loc] = custom
            else:
                messages[loc] = WELCOME_MESSAGES_DEFAULT.get(loc) or WELCOME_MESSAGES_DEFAULT.get("es") or ""

        return Response({
            "messages": messages,
            "locales": list(WELCOME_LOCALES),
            "placeholders": ERASMUS_WELCOME_PLACEHOLDERS,
        })


@api_view(["POST"])
@permission_classes([IsSuperUser])
def create_erasmus_leads_from_json(request):
    """
    POST /api/v1/superadmin/erasmus/leads/create-from-json/
    Body: { "leads": [ {...}, ... ], "allow_incomplete": false, "skip_duplicates": false }
    Creates ErasmusLead records. Same validation as carga_subir_erasmus_leads.
    """
    data = request.data or {}
    leads_list = data.get("leads")
    if leads_list is None:
        # Accept raw array at top level (e.g. [ {...}, ... ])
        if isinstance(data, list):
            leads_list = data
        else:
            return Response(
                {"detail": "Se requiere 'leads' (array) en el body."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    if not isinstance(leads_list, list):
        return Response(
            {"detail": "'leads' debe ser un array."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    allow_incomplete = bool(data.get("allow_incomplete", False))
    skip_duplicates = bool(data.get("skip_duplicates", False))
    required = REQUIRED_KEYS_INCOMPLETE if allow_incomplete else REQUIRED_KEYS_FULL

    created_count = 0
    skipped_count = 0
    errors = []
    created_ids = []

    for i, raw in enumerate(leads_list):
        if not isinstance(raw, dict):
            errors.append({"index": i + 1, "message": f"Ítem no es un objeto: {type(raw).__name__}"})
            continue
        try:
            for key in required:
                if not raw.get(key):
                    raise ValueError(f"Falta campo obligatorio: {key}")
            normalized = normalize_lead(raw, allow_incomplete=allow_incomplete)
        except Exception as e:
            errors.append({"index": i + 1, "message": str(e)})
            continue

        if skip_duplicates:
            if ErasmusLead.objects.filter(
                phone_country_code=normalized["phone_country_code"],
                phone_number=normalized["phone_number"],
            ).exists():
                skipped_count += 1
                continue

        lead = ErasmusLead.objects.create(**normalized)
        created_count += 1
        created_ids.append(str(lead.id))
        logger.info(f"✅ [JSON_ERASMUS_LEADS] Lead created: {lead.first_name} {lead.last_name} (id={lead.id})")

    return Response(
        {
            "created": created_count,
            "skipped_duplicates": skipped_count,
            "errors": errors if errors else [],
            "created_ids": created_ids,
        },
        status=status.HTTP_201_CREATED if created_count else status.HTTP_400_BAD_REQUEST if errors else status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsSuperUser])
def create_erasmus_timeline_from_json(request):
    """
    POST /api/v1/superadmin/erasmus/timeline/create-from-json/
    Body: { "items": [ { "title_es", "title_en", "location", "image", "scheduled_date", "display_order", "experience_id", "is_active" }, ... ] }
    or a single object (wrapped as one-item list).
    """
    data = request.data or {}
    items_payload = data.get("items")
    if items_payload is None:
        # Accept single object at top level
        if isinstance(data, dict) and "title_es" in data:
            items_payload = [data]
        else:
            return Response(
                {"detail": "Se requiere 'items' (array) o un objeto con title_es en el body."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    if not isinstance(items_payload, list):
        return Response(
            {"detail": "'items' debe ser un array."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    created = []
    errors = []
    for i, raw in enumerate(items_payload):
        if not isinstance(raw, dict):
            errors.append({"index": i + 1, "message": "Ítem no es un objeto."})
            continue
        serializer = JsonErasmusTimelineItemSerializer(data=raw)
        if not serializer.is_valid():
            errors.append({"index": i + 1, "message": serializer.errors})
            continue
        validated = serializer.validated_data
        experience_id = validated.pop("experience_id", None)
        item = ErasmusTimelineItem(
            title_es=validated["title_es"],
            title_en=validated.get("title_en", ""),
            location=validated.get("location", ""),
            image=validated.get("image", ""),
            scheduled_date=validated.get("scheduled_date"),
            display_order=validated.get("display_order", 0),
            is_active=validated.get("is_active", True),
        )
        if experience_id:
            item.experience_id = experience_id
        item.save()
        created.append({
            "id": str(item.id),
            "title_es": item.title_es,
            "scheduled_date": str(item.scheduled_date) if item.scheduled_date else None,
        })
        logger.info(f"✅ [JSON_ERASMUS_TIMELINE] Item created: {item.title_es} (id={item.id})")

    return Response(
        {"created": len(created), "items": created, "errors": errors},
        status=status.HTTP_201_CREATED if created else (status.HTTP_400_BAD_REQUEST if errors else status.HTTP_201_CREATED),
    )


def _parse_time(s):
    """Parse 'HH:MM' or 'HH:MM:SS' string to time object; return None if invalid."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _format_time(t):
    """Format time object to 'HH:MM' string for API."""
    if t is None:
        return None
    return t.strftime("%H:%M")


def _instance_detail_response(inst, inscribed_count=None):
    """Build JSON response for one ErasmusActivityInstance (GET/PATCH)."""
    if inscribed_count is None:
        inscribed_count = ErasmusLead.objects.filter(
            interested_experiences__contains=[str(inst.id)]
        ).count()
    return {
        "id": str(inst.id),
        "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
        "scheduled_month": inst.scheduled_month,
        "scheduled_year": inst.scheduled_year,
        "scheduled_label_es": inst.scheduled_label_es or "",
        "scheduled_label_en": inst.scheduled_label_en or "",
        "start_time": _format_time(getattr(inst, "start_time", None)),
        "end_time": _format_time(getattr(inst, "end_time", None)),
        "display_order": inst.display_order,
        "is_active": inst.is_active,
        "capacity": getattr(inst, "capacity", None),
        "is_agotado": getattr(inst, "is_agotado", False),
        "interested_count_boost": getattr(inst, "interested_count_boost", 0) or 0,
        "instructions_es": getattr(inst, "instructions_es", "") or "",
        "instructions_en": getattr(inst, "instructions_en", "") or "",
        "whatsapp_message_es": getattr(inst, "whatsapp_message_es", "") or "",
        "whatsapp_message_en": getattr(inst, "whatsapp_message_en", "") or "",
        "inscribed_count": inscribed_count,
    }


def _sync_activity_instances(act, instances_payload):
    """
    Replace activity instances with the given list. Items with id update existing;
    items without id create new. Instances not in the list are deleted.
    """
    seen_ids = set()
    for raw in instances_payload:
        if not isinstance(raw, dict):
            continue
        instance_id = raw.get("id") if raw.get("id") else None
        if instance_id:
            try:
                inst = ErasmusActivityInstance.objects.get(id=instance_id, activity_id=act.id)
            except ErasmusActivityInstance.DoesNotExist:
                inst = None
        else:
            inst = None

        if inst is not None:
            # Update existing
            if "scheduled_date" in raw:
                val = raw["scheduled_date"]
                if not val:
                    inst.scheduled_date = None
                elif isinstance(val, date):
                    inst.scheduled_date = val
                elif isinstance(val, str):
                    try:
                        inst.scheduled_date = datetime.strptime(val[:10], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        inst.scheduled_date = None
                else:
                    inst.scheduled_date = None
            if "scheduled_month" in raw:
                inst.scheduled_month = raw["scheduled_month"] if raw["scheduled_month"] is not None else None
            if "scheduled_year" in raw:
                inst.scheduled_year = raw["scheduled_year"] if raw["scheduled_year"] is not None else None
            if "scheduled_label_es" in raw:
                inst.scheduled_label_es = (raw["scheduled_label_es"] or "").strip()[:100]
            if "scheduled_label_en" in raw:
                inst.scheduled_label_en = (raw["scheduled_label_en"] or "").strip()[:100]
            if "start_time" in raw:
                inst.start_time = _parse_time(raw["start_time"])
            if "end_time" in raw:
                inst.end_time = _parse_time(raw["end_time"])
            if "display_order" in raw:
                inst.display_order = int(raw["display_order"]) if raw["display_order"] is not None else 0
            if "is_active" in raw:
                inst.is_active = bool(raw["is_active"])
            if "capacity" in raw:
                r = raw["capacity"]
                inst.capacity = int(r) if r is not None and str(r).strip() != "" else None
            if "is_agotado" in raw:
                inst.is_agotado = bool(raw["is_agotado"])
            if "instructions_es" in raw:
                inst.instructions_es = (raw["instructions_es"] or "").strip()
            if "instructions_en" in raw:
                inst.instructions_en = (raw["instructions_en"] or "").strip()
            if "whatsapp_message_es" in raw:
                inst.whatsapp_message_es = (raw["whatsapp_message_es"] or "").strip()
            if "whatsapp_message_en" in raw:
                inst.whatsapp_message_en = (raw["whatsapp_message_en"] or "").strip()
            if "interested_count_boost" in raw:
                r = raw["interested_count_boost"]
                inst.interested_count_boost = max(0, int(r)) if r is not None and str(r).strip() != "" else 0
            try:
                inst.full_clean()
                inst.save()
            except ValidationError:
                pass
            seen_ids.add(str(inst.id))
        else:
            # Create new (validate with serializer)
            ser = JsonErasmusActivityInstanceSerializer(data=raw)
            if not ser.is_valid():
                continue
            iv = ser.validated_data
            inst = ErasmusActivityInstance(
                activity=act,
                scheduled_date=iv.get("scheduled_date"),
                scheduled_month=iv.get("scheduled_month"),
                scheduled_year=iv.get("scheduled_year"),
                scheduled_label_es=iv.get("scheduled_label_es", ""),
                scheduled_label_en=iv.get("scheduled_label_en", ""),
                start_time=_parse_time(iv.get("start_time")),
                end_time=_parse_time(iv.get("end_time")),
                display_order=iv.get("display_order", 0),
                is_active=iv.get("is_active", True),
                instructions_es=(iv.get("instructions_es") or "").strip(),
                instructions_en=(iv.get("instructions_en") or "").strip(),
                whatsapp_message_es=(iv.get("whatsapp_message_es") or "").strip(),
                whatsapp_message_en=(iv.get("whatsapp_message_en") or "").strip(),
            )
            try:
                inst.full_clean()
                inst.save()
                seen_ids.add(str(inst.id))
            except ValidationError:
                pass

    # Remove instances not in the list
    for inst in act.instances.all():
        if str(inst.id) not in seen_ids:
            inst.delete()


def _activity_to_dict(act, include_instances=False):
    """Serialize ErasmusActivity for API (same structure as Experience: itinerary, meeting point, included/not_included)."""
    images = act.images or []
    main = images[0] if images else None
    if isinstance(main, dict):
        main = main.get("url") or main.get("image") or main.get("src") or ""
    data = {
        "id": str(act.id),
        "slug": act.slug,
        "title_es": act.title_es,
        "title_en": act.title_en or "",
        "description_es": act.description_es or "",
        "description_en": act.description_en or "",
        "short_description_es": act.short_description_es or "",
        "short_description_en": act.short_description_en or "",
        "location": act.location or "",
        "location_name": getattr(act, "location_name", "") or "",
        "location_address": getattr(act, "location_address", "") or "",
        "duration_minutes": getattr(act, "duration_minutes", None),
        "included": getattr(act, "included", None) or [],
        "not_included": getattr(act, "not_included", None) or [],
        "itinerary": getattr(act, "itinerary", None) or [],
        "images": images,
        "image": main or "",
        "display_order": act.display_order,
        "is_active": act.is_active,
        "detail_layout": getattr(act, "detail_layout", "default") or "default",
        "experience_id": str(act.experience_id) if act.experience_id else None,
        "created_at": act.created_at.isoformat() if act.created_at else None,
        "updated_at": act.updated_at.isoformat() if act.updated_at else None,
        "is_paid": getattr(act, "is_paid", False),
        "price": str(act.price) if getattr(act, "price", None) is not None else None,
    }
    if include_instances:
        data["instances"] = []
        for inst in act.instances.order_by("display_order", "scheduled_date", "scheduled_year", "scheduled_month"):
            inscribed_count = ErasmusLead.objects.filter(
                interested_experiences__contains=[str(inst.id)]
            ).count()
            data["instances"].append({
                "id": str(inst.id),
                "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                "scheduled_month": inst.scheduled_month,
                "scheduled_year": inst.scheduled_year,
                "scheduled_label_es": inst.scheduled_label_es or "",
                "scheduled_label_en": inst.scheduled_label_en or "",
                "start_time": _format_time(getattr(inst, "start_time", None)),
                "end_time": _format_time(getattr(inst, "end_time", None)),
                "display_order": inst.display_order,
                "is_active": inst.is_active,
                "capacity": getattr(inst, "capacity", None),
                "is_agotado": getattr(inst, "is_agotado", False),
                "interested_count_boost": getattr(inst, "interested_count_boost", 0) or 0,
                "instructions_es": getattr(inst, "instructions_es", "") or "",
                "instructions_en": getattr(inst, "instructions_en", "") or "",
                "whatsapp_message_es": getattr(inst, "whatsapp_message_es", "") or "",
                "whatsapp_message_en": getattr(inst, "whatsapp_message_en", "") or "",
                "inscribed_count": inscribed_count,
            })
    return data


def _normalize_images(raw_images):
    """Accept list of URLs or list of dicts with url/image/src; return list of URL strings."""
    if not raw_images:
        return []
    out = []
    for item in raw_images:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            out.append(item.get("url") or item.get("image") or item.get("src") or "")
    return out


@api_view(["POST"])
@permission_classes([IsSuperUser])
def link_experience_to_erasmus_activity(request):
    """
    POST /api/v1/superadmin/erasmus/activities/link-experience/

    Create an Erasmus activity that uses an existing Experience as content source.
    Body: {
      "experience_id": "uuid",   # required
      "slug": "optional-slug",    # optional; default: experience.slug, made unique if needed
      "display_order": 0,
      "is_active": true,
      "instances": [ { "scheduled_date": "YYYY-MM-DD", ... }, ... ]  # optional; at least one recommended for timeline
    }
    Public API will show the experience's title, description, images, etc. (single source of truth).
    """
    data = request.data or {}
    experience_id = data.get("experience_id")
    if not experience_id:
        return Response(
            {"detail": "Se requiere 'experience_id' (UUID de la experiencia)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        experience = Experience.objects.get(id=experience_id)
    except (Experience.DoesNotExist, ValueError, TypeError):
        return Response(
            {"detail": "Experiencia no encontrada."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if ErasmusActivity.objects.filter(experience_id=experience_id).exists():
        return Response(
            {"detail": "Esta experiencia ya está vinculada a una actividad Erasmus."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    slug = (data.get("slug") or "").strip() or experience.slug or ""
    if not slug:
        slug = f"erasmus-{str(experience.id)[:8]}"
    base_slug = slug
    counter = 0
    while ErasmusActivity.objects.filter(slug=slug).exists():
        counter += 1
        slug = f"{base_slug}-{counter}"
    title = (experience.title or "").strip() or "Actividad Erasmus"
    act = ErasmusActivity(
        title_es=title,
        title_en=title,
        slug=slug,
        description_es="",
        description_en="",
        short_description_es="",
        short_description_en="",
        location="",
        location_name="",
        location_address="",
        duration_minutes=None,
        included=[],
        not_included=[],
        itinerary=[],
        images=[],
        display_order=int(data.get("display_order", 0)) if data.get("display_order") is not None else 0,
        is_active=data.get("is_active", True) if data.get("is_active") is not None else True,
        detail_layout=(data.get("detail_layout") or "default").strip() or "default",
        experience_id=experience_id,
    )
    act.save()
    instances_payload = data.get("instances") or []
    created_instances = []
    for raw in instances_payload if isinstance(instances_payload, list) else []:
        if not isinstance(raw, dict):
            continue
        inst_ser = JsonErasmusActivityInstanceSerializer(data=raw)
        if not inst_ser.is_valid():
            continue
        iv = inst_ser.validated_data
        start_t = _parse_time(iv.get("start_time"))
        end_t = _parse_time(iv.get("end_time"))
        inst = ErasmusActivityInstance(
            activity=act,
            scheduled_date=iv.get("scheduled_date"),
            scheduled_month=iv.get("scheduled_month"),
            scheduled_year=iv.get("scheduled_year"),
            scheduled_label_es=iv.get("scheduled_label_es", ""),
            scheduled_label_en=iv.get("scheduled_label_en", ""),
            start_time=start_t,
            end_time=end_t,
            display_order=iv.get("display_order", 0),
            is_active=iv.get("is_active", True),
            instructions_es=(iv.get("instructions_es") or "").strip(),
            instructions_en=(iv.get("instructions_en") or "").strip(),
            whatsapp_message_es=(iv.get("whatsapp_message_es") or "").strip(),
            whatsapp_message_en=(iv.get("whatsapp_message_en") or "").strip(),
            interested_count_boost=iv.get("interested_count_boost", 0) or 0,
        )
        try:
            inst.full_clean()
            inst.save()
            created_instances.append({"id": str(inst.id)})
        except ValidationError:
            continue
    logger.info(
        "Erasmus activity linked to experience: %s (id=%s), slug=%s, instances=%s",
        experience.title,
        act.id,
        act.slug,
        len(created_instances),
    )
    return Response(
        {
            "id": str(act.id),
            "slug": act.slug,
            "experience_id": str(experience_id),
            "experience_title": experience.title,
            "instances_created": len(created_instances),
            "instances": created_instances,
        },
        status=status.HTTP_201_CREATED,
    )


class ErasmusActivityListView(APIView):
    """GET /api/v1/superadmin/erasmus/activities/ – list all activities (optional: is_active, search). Includes public_link paths when exist."""
    permission_classes = [IsSuperUser]

    def get(self, request):
        qs = ErasmusActivity.objects.all().order_by("display_order", "created_at")
        is_active = request.query_params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ("true", "1", "yes"))
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                models.Q(title_es__icontains=search)
                | models.Q(title_en__icontains=search)
                | models.Q(slug__icontains=search)
            )
        activities = list(qs)
        result = [_activity_to_dict(act) for act in activities]
        # Attach public link paths for copy-link actions (view inscritos, edit, review, public activity)
        link_map = {
            str(link.activity_id): {
                "view_path": f"/erasmus/lista/{link.view_token}",
                "edit_path": f"/erasmus/editar/{link.edit_token}",
                "review_path": f"/erasmus/resenas/{link.review_token}" if link.review_token else None,
                "public_activity_path": f"/erasmus/actividades/{link.activity.slug}",
            }
            for link in ErasmusActivityPublicLink.objects.filter(
                activity__in=activities
            ).select_related("activity")
        }
        for i, act in enumerate(activities):
            aid = str(act.id)
            result[i]["public_link"] = link_map.get(aid)
        return Response({"results": result, "count": len(result)})


@api_view(["POST"])
@permission_classes([IsSuperUser])
def create_erasmus_activity_from_json(request):
    """
    POST /api/v1/superadmin/erasmus/activities/create-from-json/
    Body: { "activity_data": { ... }, "instances": [ ... ] } (instances optional).
    """
    data = request.data or {}
    activity_payload = data.get("activity_data") or data.get("activity")
    if not activity_payload or not isinstance(activity_payload, dict):
        return Response(
            {"detail": "Se requiere 'activity_data' (objeto) en el body."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer = JsonErasmusActivityCreateSerializer(data=activity_payload)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    validated = serializer.validated_data
    if ErasmusActivity.objects.filter(slug=validated["slug"]).exists():
        return Response(
            {"detail": f"Ya existe una actividad con slug '{validated['slug']}'."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    experience_id = validated.pop("experience_id", None)
    images = _normalize_images(validated.get("images") or [])
    from decimal import Decimal as Dec
    price_val = validated.get("price")
    if price_val is not None and str(price_val).strip() != "":
        try:
            price_decimal = Dec(str(price_val))
        except Exception:
            price_decimal = None
    else:
        price_decimal = None

    act = ErasmusActivity(
        title_es=validated["title_es"],
        title_en=validated.get("title_en", ""),
        slug=validated["slug"],
        description_es=validated.get("description_es", ""),
        description_en=validated.get("description_en", ""),
        short_description_es=validated.get("short_description_es", ""),
        short_description_en=validated.get("short_description_en", ""),
        location=validated.get("location", ""),
        location_name=validated.get("location_name", ""),
        location_address=validated.get("location_address", ""),
        duration_minutes=validated.get("duration_minutes"),
        included=validated.get("included") or [],
        not_included=validated.get("not_included") or [],
        itinerary=validated.get("itinerary") or [],
        images=images,
        display_order=validated.get("display_order", 0),
        is_active=validated.get("is_active", True),
        detail_layout=validated.get("detail_layout", "default") or "default",
        is_paid=validated.get("is_paid", False),
        price=price_decimal,
    )
    if experience_id:
        act.experience_id = experience_id
    act.save()
    instances_payload = data.get("instances") or []
    created_instances = []
    for i, raw in enumerate(instances_payload if isinstance(instances_payload, list) else []):
        if not isinstance(raw, dict):
            continue
        inst_ser = JsonErasmusActivityInstanceSerializer(data=raw)
        if not inst_ser.is_valid():
            continue
        iv = inst_ser.validated_data
        start_t = _parse_time(iv.get("start_time"))
        end_t = _parse_time(iv.get("end_time"))
        inst = ErasmusActivityInstance(
            activity=act,
            scheduled_date=iv.get("scheduled_date"),
            scheduled_month=iv.get("scheduled_month"),
            scheduled_year=iv.get("scheduled_year"),
            scheduled_label_es=iv.get("scheduled_label_es", ""),
            scheduled_label_en=iv.get("scheduled_label_en", ""),
            start_time=start_t,
            end_time=end_t,
            display_order=iv.get("display_order", 0),
            is_active=iv.get("is_active", True),
            instructions_es=(iv.get("instructions_es") or "").strip(),
            instructions_en=(iv.get("instructions_en") or "").strip(),
            whatsapp_message_es=(iv.get("whatsapp_message_es") or "").strip(),
            whatsapp_message_en=(iv.get("whatsapp_message_en") or "").strip(),
            interested_count_boost=iv.get("interested_count_boost", 0) or 0,
        )
        inst.full_clean()
        inst.save()
        created_instances.append({"id": str(inst.id)})
    logger.info(f"✅ [JSON_ERASMUS_ACTIVITY] Activity created: {act.title_es} (id={act.id}), instances={len(created_instances)}")
    return Response(
        {"id": str(act.id), "slug": act.slug, "instances_created": len(created_instances), "instances": created_instances},
        status=status.HTTP_201_CREATED,
    )


class ErasmusActivityDetailView(APIView):
    """GET/PATCH /api/v1/superadmin/erasmus/activities/<id>/ – detail and update (including images)."""
    permission_classes = [IsSuperUser]

    def get(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_activity_to_dict(act, include_instances=True))

    def patch(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data or {}
        if "title_es" in data:
            act.title_es = (data["title_es"] or "").strip()[:255]
        if "title_en" in data:
            act.title_en = (data["title_en"] or "").strip()[:255]
        if "slug" in data and data["slug"]:
            new_slug = (data["slug"] or "").strip()[:255]
            if new_slug != act.slug and ErasmusActivity.objects.filter(slug=new_slug).exists():
                return Response({"detail": "Slug already exists."}, status=status.HTTP_400_BAD_REQUEST)
            act.slug = new_slug
        if "description_es" in data:
            act.description_es = (data["description_es"] or "")[:10000]
        if "description_en" in data:
            act.description_en = (data["description_en"] or "")[:10000]
        if "short_description_es" in data:
            act.short_description_es = (data["short_description_es"] or "").strip()[:500]
        if "short_description_en" in data:
            act.short_description_en = (data["short_description_en"] or "").strip()[:500]
        if "location" in data:
            act.location = (data["location"] or "").strip()[:255]
        if "location_name" in data:
            act.location_name = (data["location_name"] or "").strip()[:255]
        if "location_address" in data:
            act.location_address = (data["location_address"] or "")[:5000]
        if "duration_minutes" in data:
            v = data["duration_minutes"]
            act.duration_minutes = int(v) if v is not None and v != "" else None
        if "included" in data:
            act.included = data["included"] if isinstance(data["included"], list) else []
        if "not_included" in data:
            act.not_included = data["not_included"] if isinstance(data["not_included"], list) else []
        if "itinerary" in data:
            raw = data["itinerary"] if isinstance(data["itinerary"], list) else []
            try:
                validate_itinerary_items(raw)
            except DRFValidationError as e:
                return Response({"detail": str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)
            act.itinerary = raw
        if "images" in data:
            act.images = _normalize_images(data["images"] if isinstance(data["images"], list) else [])
        if "display_order" in data:
            act.display_order = int(data["display_order"]) if data["display_order"] is not None else 0
        if "is_active" in data:
            act.is_active = bool(data["is_active"])
        if "experience_id" in data:
            act.experience_id = data["experience_id"] if data["experience_id"] else None
        if "detail_layout" in data:
            val = (data["detail_layout"] or "").strip()
            if val in ("default", "two_column"):
                act.detail_layout = val
        if "is_paid" in data:
            act.is_paid = bool(data["is_paid"])
        if "price" in data:
            v = data["price"]
            from decimal import Decimal
            act.price = Decimal(str(v)) if v is not None and str(v).strip() != "" else None
        act.save()

        # Optional: sync instances (full replace). If "instances" is present, create/update/delete to match.
        if "instances" in data:
            instances_payload = data["instances"]
            if isinstance(instances_payload, list):
                _sync_activity_instances(act, instances_payload)

        return Response(_activity_to_dict(act, include_instances=True))

    def delete(self, request, activity_id):
        """DELETE /api/v1/superadmin/erasmus/activities/<id>/ – delete activity and its instances."""
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        title = act.title_es or act.slug
        act.delete()  # CASCADE deletes all instances
        logger.info(f"🗑️ [ERASMUS_ACTIVITY] Deleted activity: {title} (id={activity_id})")
        return Response(status=status.HTTP_204_NO_CONTENT)


class ErasmusActivityInstanceListCreateView(APIView):
    """GET/POST /api/v1/superadmin/erasmus/activities/<activity_id>/instances/"""
    permission_classes = [IsSuperUser]

    def get(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        instances = []
        for inst in act.instances.order_by("display_order", "scheduled_date", "scheduled_year", "scheduled_month"):
            inscribed_count = ErasmusLead.objects.filter(
                interested_experiences__contains=[str(inst.id)]
            ).count()
            instances.append({
                "id": str(inst.id),
                "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                "scheduled_month": inst.scheduled_month,
                "scheduled_year": inst.scheduled_year,
                "scheduled_label_es": inst.scheduled_label_es or "",
                "scheduled_label_en": inst.scheduled_label_en or "",
                "start_time": _format_time(getattr(inst, "start_time", None)),
                "end_time": _format_time(getattr(inst, "end_time", None)),
                "display_order": inst.display_order,
                "is_active": inst.is_active,
                "capacity": getattr(inst, "capacity", None),
                "is_agotado": getattr(inst, "is_agotado", False),
                "interested_count_boost": getattr(inst, "interested_count_boost", 0) or 0,
                "instructions_es": getattr(inst, "instructions_es", "") or "",
                "instructions_en": getattr(inst, "instructions_en", "") or "",
                "whatsapp_message_es": getattr(inst, "whatsapp_message_es", "") or "",
                "whatsapp_message_en": getattr(inst, "whatsapp_message_en", "") or "",
                "inscribed_count": inscribed_count,
            })
        return Response({"results": instances})

    def post(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = JsonErasmusActivityInstanceSerializer(data=request.data or {})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        iv = serializer.validated_data
        inst = ErasmusActivityInstance(
            activity=act,
            scheduled_date=iv.get("scheduled_date"),
            scheduled_month=iv.get("scheduled_month"),
            scheduled_year=iv.get("scheduled_year"),
            scheduled_label_es=iv.get("scheduled_label_es", ""),
            scheduled_label_en=iv.get("scheduled_label_en", ""),
            start_time=_parse_time(iv.get("start_time")),
            end_time=_parse_time(iv.get("end_time")),
            display_order=iv.get("display_order", 0),
            is_active=iv.get("is_active", True),
            instructions_es=(iv.get("instructions_es") or "").strip(),
            instructions_en=(iv.get("instructions_en") or "").strip(),
            whatsapp_message_es=(iv.get("whatsapp_message_es") or "").strip(),
            whatsapp_message_en=(iv.get("whatsapp_message_en") or "").strip(),
            interested_count_boost=iv.get("interested_count_boost", 0) or 0,
        )
        try:
            inst.full_clean()
            inst.save()
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"id": str(inst.id), "scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None},
            status=status.HTTP_201_CREATED,
        )


@api_view(["POST"])
@permission_classes([IsSuperUser])
def erasmus_activity_instances_bulk_from_json(request, activity_id):
    """POST /api/v1/superadmin/erasmus/activities/<activity_id>/instances/bulk-from-json/"""
    try:
        act = ErasmusActivity.objects.get(id=activity_id)
    except ErasmusActivity.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    data = request.data or {}
    items = data.get("instances") or data if isinstance(data, list) else []
    created = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        serializer = JsonErasmusActivityInstanceSerializer(data=raw)
        if not serializer.is_valid():
            continue
        iv = serializer.validated_data
        inst = ErasmusActivityInstance(
            activity=act,
            scheduled_date=iv.get("scheduled_date"),
            scheduled_month=iv.get("scheduled_month"),
            scheduled_year=iv.get("scheduled_year"),
            scheduled_label_es=iv.get("scheduled_label_es", ""),
            scheduled_label_en=iv.get("scheduled_label_en", ""),
            start_time=_parse_time(iv.get("start_time")),
            end_time=_parse_time(iv.get("end_time")),
            display_order=iv.get("display_order", 0),
            is_active=iv.get("is_active", True),
            instructions_es=(iv.get("instructions_es") or "").strip(),
            instructions_en=(iv.get("instructions_en") or "").strip(),
            whatsapp_message_es=(iv.get("whatsapp_message_es") or "").strip(),
            whatsapp_message_en=(iv.get("whatsapp_message_en") or "").strip(),
            interested_count_boost=iv.get("interested_count_boost", 0) or 0,
        )
        try:
            inst.full_clean()
            inst.save()
            created.append({"id": str(inst.id)})
        except ValidationError:
            pass
    return Response({"created": len(created), "instances": created}, status=status.HTTP_201_CREATED)


class ErasmusActivityInstanceDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/superadmin/erasmus/activities/<activity_id>/instances/<instance_id>/"""
    permission_classes = [IsSuperUser]

    def get(self, request, activity_id, instance_id):
        try:
            inst = ErasmusActivityInstance.objects.get(id=instance_id, activity_id=activity_id)
        except ErasmusActivityInstance.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        inscribed_count = ErasmusLead.objects.filter(
            interested_experiences__contains=[str(inst.id)]
        ).count()
        return Response(_instance_detail_response(inst, inscribed_count))

    def patch(self, request, activity_id, instance_id):
        try:
            inst = ErasmusActivityInstance.objects.get(id=instance_id, activity_id=activity_id)
        except ErasmusActivityInstance.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data or {}
        if "scheduled_date" in data:
            inst.scheduled_date = data["scheduled_date"] if data["scheduled_date"] else None
        if "scheduled_month" in data:
            inst.scheduled_month = data["scheduled_month"] if data["scheduled_month"] is not None else None
        if "scheduled_year" in data:
            inst.scheduled_year = data["scheduled_year"] if data["scheduled_year"] is not None else None
        if "scheduled_label_es" in data:
            inst.scheduled_label_es = (data["scheduled_label_es"] or "").strip()[:100]
        if "scheduled_label_en" in data:
            inst.scheduled_label_en = (data["scheduled_label_en"] or "").strip()[:100]
        if "start_time" in data:
            inst.start_time = _parse_time(data["start_time"])
        if "end_time" in data:
            inst.end_time = _parse_time(data["end_time"])
        if "display_order" in data:
            inst.display_order = int(data["display_order"]) if data["display_order"] is not None else 0
        if "is_active" in data:
            inst.is_active = bool(data["is_active"])
        if "capacity" in data:
            raw = data["capacity"]
            inst.capacity = int(raw) if raw is not None and str(raw).strip() != "" else None
        if "is_agotado" in data:
            inst.is_agotado = bool(data["is_agotado"])
        if "instructions_es" in data:
            inst.instructions_es = (data["instructions_es"] or "").strip()
        if "instructions_en" in data:
            inst.instructions_en = (data["instructions_en"] or "").strip()
        if "whatsapp_message_es" in data:
            inst.whatsapp_message_es = (data["whatsapp_message_es"] or "").strip()
        if "whatsapp_message_en" in data:
            inst.whatsapp_message_en = (data["whatsapp_message_en"] or "").strip()
        if "interested_count_boost" in data:
            raw = data["interested_count_boost"]
            inst.interested_count_boost = max(0, int(raw)) if raw is not None and str(raw).strip() != "" else 0
        try:
            inst.full_clean()
            inst.save()
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_instance_detail_response(inst))

    def delete(self, request, activity_id, instance_id):
        try:
            inst = ErasmusActivityInstance.objects.get(id=instance_id, activity_id=activity_id)
        except ErasmusActivityInstance.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        inst.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ErasmusActivityInstanceInscriptionsView(APIView):
    """GET /api/v1/superadmin/erasmus/activities/<activity_id>/instances/<instance_id>/inscriptions/ – list leads inscribed for this instance. ?format=csv for CSV export (includes extra_fields columns)."""
    permission_classes = [IsSuperUser]

    def get(self, request, activity_id, instance_id):
        try:
            inst = ErasmusActivityInstance.objects.select_related("activity").get(
                id=instance_id, activity_id=activity_id
            )
        except ErasmusActivityInstance.DoesNotExist:
            return Response({"detail": "No encontrado."}, status=status.HTTP_404_NOT_FOUND)
        act = inst.activity
        extra_field_defs = list(
            ErasmusActivityExtraField.objects.filter(activity=act, is_active=True).order_by("order", "id")
        )
        lead_ids = list(
            ErasmusLead.objects.filter(
                interested_experiences__contains=[str(inst.id)]
            ).values_list("id", flat=True)
        )
        registrations_by_lead = {
            r.lead_id: r
            for r in ErasmusActivityInstanceRegistration.objects.filter(
                instance=inst, lead_id__in=lead_ids
            ).select_related("lead")
        }
        leads = ErasmusLead.objects.filter(id__in=lead_ids).order_by("-updated_at")
        result = []
        for lead in leads:
            reg = registrations_by_lead.get(lead.id)
            extra_data = (reg.extra_data if reg else None) or {}
            result.append({
                "id": str(lead.id),
                "first_name": lead.first_name or "",
                "last_name": lead.last_name or "",
                "email": lead.email or "",
                "phone_country_code": lead.phone_country_code or "",
                "phone_number": lead.phone_number or "",
                "instagram": lead.instagram or "",
                "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
                "extra_data": extra_data,
            })
        if request.query_params.get("format") == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = (
                f'attachment; filename="inscritos_{act.slug}_{inst.id}_{date.today().isoformat()}.csv"'
            )
            response.write("\ufeff")
            writer = csv.writer(response)
            header = [
                "Nombre", "Apellido", "Email", "Código teléfono", "Teléfono", "Instagram", "Fecha actualización"
            ]
            for ef in extra_field_defs:
                header.append(ef.label)
            writer.writerow(header)
            for item in result:
                row = [
                    item["first_name"],
                    item["last_name"],
                    item["email"],
                    item["phone_country_code"],
                    item["phone_number"],
                    item["instagram"] or "",
                    item["updated_at"] or "",
                ]
                ed = item.get("extra_data") or {}
                for ef in extra_field_defs:
                    val = ed.get(ef.field_key)
                    if isinstance(val, list):
                        val = ", ".join(str(x) for x in val) if val else ""
                    else:
                        val = str(val).strip() if val is not None else ""
                    row.append(val)
                writer.writerow(row)
            return response
        return Response({"inscriptions": result, "count": len(result)})


def _public_link_tokens():
    """Generate unique view, edit and review tokens (URL-safe)."""
    import secrets
    return (
        secrets.token_urlsafe(32)[:64],
        secrets.token_urlsafe(32)[:64],
        secrets.token_urlsafe(32)[:64],
    )


class ErasmusActivityPublicLinkView(APIView):
    """
    GET/POST/PATCH /api/v1/superadmin/erasmus/activities/<activity_id>/public-link/
    GET: return existing public link (view_token, edit_token, review_token, links_enabled) + paths.
    POST: create public link for this activity (idempotent); generates review_token if missing.
    PATCH: toggle links_enabled.
    """
    permission_classes = [IsSuperUser]

    def get(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            link = ErasmusActivityPublicLink.objects.get(activity_id=activity_id)
        except ErasmusActivityPublicLink.DoesNotExist:
            return Response({
                "exists": False,
                "view_token": None,
                "edit_token": None,
                "review_token": None,
                "links_enabled": None,
                "review_link_enabled": None,
                "view_path": None,
                "edit_path": None,
                "review_path": None,
            })
        if not link.review_token:
            link.review_token = _public_link_tokens()[-1]
            link.save(update_fields=["review_token"])
        view_path = f"/erasmus/lista/{link.view_token}"
        edit_path = f"/erasmus/editar/{link.edit_token}"
        review_path = f"/erasmus/resenas/{link.review_token}"
        return Response({
            "exists": True,
            "view_token": link.view_token,
            "edit_token": link.edit_token,
            "review_token": link.review_token,
            "links_enabled": link.links_enabled,
            "review_link_enabled": getattr(link, "review_link_enabled", True),
            "view_path": view_path,
            "edit_path": edit_path,
            "review_path": review_path,
        })

    def post(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        vt, et, rt = _public_link_tokens()
        link, created = ErasmusActivityPublicLink.objects.get_or_create(
            activity=act,
            defaults={
                "view_token": vt,
                "edit_token": et,
                "review_token": rt,
                "links_enabled": True,
                "review_link_enabled": True,
            },
        )
        if not created:
            updates = {}
            if not link.view_token or not link.edit_token:
                link.view_token, link.edit_token, _ = _public_link_tokens()
                updates["view_token"] = link.view_token
                updates["edit_token"] = link.edit_token
            if not link.review_token:
                link.review_token = _public_link_tokens()[-1]
                updates["review_token"] = link.review_token
            if updates:
                link.save(update_fields=list(updates.keys()))
        view_path = f"/erasmus/lista/{link.view_token}"
        edit_path = f"/erasmus/editar/{link.edit_token}"
        review_path = f"/erasmus/resenas/{link.review_token}"
        return Response({
            "exists": True,
            "created": created,
            "view_token": link.view_token,
            "edit_token": link.edit_token,
            "review_token": link.review_token,
            "links_enabled": link.links_enabled,
            "review_link_enabled": getattr(link, "review_link_enabled", True),
            "view_path": view_path,
            "edit_path": edit_path,
            "review_path": review_path,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def patch(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            link = ErasmusActivityPublicLink.objects.get(activity_id=activity_id)
        except ErasmusActivityPublicLink.DoesNotExist:
            return Response({"detail": "No public link for this activity. Create one first."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data or {}
        update_fields = []
        if "links_enabled" in data:
            link.links_enabled = bool(data["links_enabled"])
            update_fields.append("links_enabled")
        if "review_link_enabled" in data:
            link.review_link_enabled = bool(data["review_link_enabled"])
            update_fields.append("review_link_enabled")
        if update_fields:
            link.save(update_fields=update_fields)
        review_path = f"/erasmus/resenas/{link.review_token}" if link.review_token else None
        return Response({
            "view_token": link.view_token,
            "edit_token": link.edit_token,
            "review_token": link.review_token,
            "links_enabled": link.links_enabled,
            "review_link_enabled": getattr(link, "review_link_enabled", True),
            "view_path": f"/erasmus/lista/{link.view_token}",
            "edit_path": f"/erasmus/editar/{link.edit_token}",
            "review_path": review_path,
        })


def _instance_review_label_superadmin(inst):
    if inst.scheduled_date:
        return inst.scheduled_date.strftime("%d/%m/%Y")
    if inst.scheduled_label_es:
        return inst.scheduled_label_es
    if inst.scheduled_month and inst.scheduled_year:
        return f"{inst.scheduled_month:02d}/{inst.scheduled_year}"
    return str(inst.id)


class ErasmusActivityReviewsListView(APIView):
    """
    GET /api/v1/superadmin/erasmus/activities/<activity_id>/reviews/
    Query: instance_id (optional) – filter by instance.
    """
    permission_classes = [IsSuperUser]

    def get(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        instance_id = request.query_params.get("instance_id")
        qs = ErasmusActivityReview.objects.filter(instance__activity_id=activity_id).select_related("instance")
        if instance_id:
            qs = qs.filter(instance_id=instance_id)
        qs = qs.order_by("-created_at")
        results = []
        for r in qs:
            inst = r.instance
            results.append({
                "id": r.id,
                "instance_id": str(inst.id),
                "instance_label": _instance_review_label_superadmin(inst),
                "instance_scheduled_date": inst.scheduled_date.isoformat() if inst.scheduled_date else None,
                "author_name": r.author_name,
                "author_origin": r.author_origin or "",
                "rating": r.rating,
                "body": r.body,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return Response({"results": results, "count": len(results)})


class ErasmusActivityReviewDeleteView(APIView):
    """DELETE /api/v1/superadmin/erasmus/activities/<activity_id>/reviews/<int:review_id>/"""
    permission_classes = [IsSuperUser]

    def delete(self, request, activity_id, review_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            review = ErasmusActivityReview.objects.get(id=review_id, instance__activity_id=activity_id)
        except ErasmusActivityReview.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        review.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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


class ErasmusWhatsAppGroupViewSet(viewsets.ModelViewSet):
    """CRUD for Erasmus WhatsApp groups (name + link). Superadmin Erasmus > Grupos WhatsApp."""

    permission_classes = [IsSuperUser]
    queryset = ErasmusWhatsAppGroup.objects.all().order_by("order", "id")

    def list(self, request, *args, **kwargs):
        items = list(
            self.get_queryset().values("id", "name", "link", "image_url", "category", "order", "is_active")
        )
        return Response(items)

    def create(self, request, *args, **kwargs):
        data = request.data
        name = (data.get("name") or "").strip()
        link = (data.get("link") or "").strip()
        if not name or not link:
            return Response(
                {"detail": "name and link required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order = int(data.get("order", 0))
        is_active = bool(data.get("is_active", True))
        image_url = (data.get("image_url") or "").strip() or ""
        category = (data.get("category") or "tuki").strip()
        if category not in ("university", "tuki"):
            category = "tuki"
        obj = ErasmusWhatsAppGroup.objects.create(
            name=name, link=link, order=order, is_active=is_active,
            image_url=image_url, category=category,
        )
        return Response(
            {"id": obj.id, "name": obj.name, "link": obj.link, "image_url": obj.image_url or "", "category": obj.category, "order": obj.order, "is_active": obj.is_active},
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        return Response({
            "id": obj.id, "name": obj.name, "link": obj.link, "image_url": obj.image_url or "", "category": obj.category, "order": obj.order, "is_active": obj.is_active,
        })

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        if "name" in request.data:
            obj.name = (request.data["name"] or "").strip()
        if "link" in request.data:
            obj.link = (request.data["link"] or "").strip()
        if "image_url" in request.data:
            obj.image_url = (request.data["image_url"] or "").strip() or ""
        if "category" in request.data:
            raw = (request.data["category"] or "").strip()
            obj.category = raw if raw in ("university", "tuki") else "tuki"
        if "order" in request.data:
            obj.order = int(request.data["order"])
        if "is_active" in request.data:
            obj.is_active = bool(request.data["is_active"])
        obj.save()
        return Response({
            "id": obj.id, "name": obj.name, "link": obj.link, "image_url": obj.image_url or "", "category": obj.category, "order": obj.order, "is_active": obj.is_active,
        })

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


@api_view(["POST"])
@permission_classes([IsSuperUser])
def erasmus_whatsapp_group_fetch_image(request, pk):
    """
    Fetch og:image from the group's WhatsApp invite page and save as image_url.
    POST /api/v1/superadmin/erasmus/whatsapp-groups/<id>/fetch-image/
    Returns { "image_url": "..." } on success, or 400/404 if no image found or invalid group.
    """
    try:
        obj = ErasmusWhatsAppGroup.objects.get(pk=pk)
    except ErasmusWhatsAppGroup.DoesNotExist:
        return Response({"detail": "Group not found."}, status=status.HTTP_404_NOT_FOUND)
    link = (obj.link or "").strip()
    if not link:
        return Response(
            {"detail": "Group has no link."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    result = fetch_whatsapp_group_image(link)
    if not result.get("image"):
        return Response(
            {"detail": "No se pudo obtener la imagen del enlace (og:image no encontrado)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    obj.image_url = result["image"]
    obj.save(update_fields=["image_url", "updated_at"])
    return Response({"image_url": obj.image_url})


RUMI_HOUSING_SLUG = "rumi_housing"


class ErasmusRumiNotificationConfigView(APIView):
    """
    GET: return Rumi (housing) notification config and list of WhatsApp groups for the selector.
    PATCH: update whatsapp_chat_id and/or is_active for rumi_housing.
    """

    permission_classes = [IsSuperUser]

    def get(self, request):
        config = ErasmusPartnerNotificationConfig.objects.filter(slug=RUMI_HOUSING_SLUG).first()
        if not config:
            config = ErasmusPartnerNotificationConfig.objects.create(
                slug=RUMI_HOUSING_SLUG,
                name="Rumi – Housing",
                is_active=False,
                description="Notificar cuando un registro Erasmus requiere housing (wants_rumi4students_contact).",
            )
        groups = list(
            WhatsAppChat.objects.filter(type="group", is_active=True)
            .order_by("-last_message_at", "-created_at")
            .values("id", "name", "chat_id")
        )
        # Serialize UUID for JSON
        groups_serialized = [
            {"id": str(g["id"]), "name": g["name"] or g["chat_id"], "chat_id": g["chat_id"]}
            for g in groups
        ]
        return Response({
            "config": {
                "slug": config.slug,
                "name": config.name,
                "is_active": config.is_active,
                "whatsapp_chat_id": str(config.whatsapp_chat_id) if config.whatsapp_chat_id else None,
                "whatsapp_chat_name": config.whatsapp_chat.name if config.whatsapp_chat else None,
            },
            "groups": groups_serialized,
        })

    def patch(self, request):
        config = ErasmusPartnerNotificationConfig.objects.filter(slug=RUMI_HOUSING_SLUG).first()
        if not config:
            config = ErasmusPartnerNotificationConfig.objects.create(
                slug=RUMI_HOUSING_SLUG,
                name="Rumi – Housing",
                is_active=False,
                description="Notificar cuando un registro Erasmus requiere housing (wants_rumi4students_contact).",
            )
        data = request.data or {}
        if "whatsapp_chat_id" in data:
            raw = data["whatsapp_chat_id"]
            if raw is None or raw == "":
                config.whatsapp_chat = None
            else:
                try:
                    chat = WhatsAppChat.objects.get(id=raw, type="group")
                    config.whatsapp_chat = chat
                except (WhatsAppChat.DoesNotExist, ValueError, TypeError):
                    return Response(
                        {"detail": "Invalid or unknown group id."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        if "is_active" in data:
            config.is_active = bool(data["is_active"])
        config.save()
        return Response({
            "config": {
                "slug": config.slug,
                "name": config.name,
                "is_active": config.is_active,
                "whatsapp_chat_id": str(config.whatsapp_chat_id) if config.whatsapp_chat_id else None,
                "whatsapp_chat_name": config.whatsapp_chat.name if config.whatsapp_chat else None,
            },
        })


@api_view(["POST"])
@permission_classes([IsSuperUser])
def erasmus_whatsapp_groups_bulk_from_json(request):
    """
    POST with body: { "groups": [ { "name": "...", "link": "..." }, ... ] }
    Replaces all WhatsApp groups: deletes existing and creates from the list.
    Order = index in array.
    """
    try:
        payload = request.data or {}
        groups_data = payload.get("groups")
        if groups_data is None:
            return Response(
                {"detail": "Missing 'groups' array in body"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(groups_data, list):
            return Response(
                {"detail": "'groups' must be an array"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except Exception:
        return Response(
            {"detail": "Invalid JSON body"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    created = []
    ErasmusWhatsAppGroup.objects.all().delete()
    for i, raw in enumerate(groups_data):
        if not isinstance(raw, dict):
            continue
        name = (raw.get("name") or "").strip()
        link = (raw.get("link") or raw.get("url") or "").strip()
        if not name or not link:
            continue
        image_url = (raw.get("image_url") or "").strip() or ""
        category = (raw.get("category") or "tuki").strip()
        if category not in ("university", "tuki"):
            category = "tuki"
        obj = ErasmusWhatsAppGroup.objects.create(
            name=name, link=link, order=i, is_active=True,
            image_url=image_url, category=category,
        )
        created.append({"id": obj.id, "name": obj.name, "link": obj.link, "image_url": obj.image_url or "", "category": obj.category, "order": obj.order})
    logger.info("[ErasmusWhatsAppGroups] Bulk replaced with %s groups", len(created))
    return Response({"count": len(created), "groups": created}, status=status.HTTP_200_OK)


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


class ErasmusActivityExtraFieldViewSet(viewsets.ModelViewSet):
    """CRUD for activity-specific extra fields (inscription form): /api/v1/superadmin/erasmus/activities/<activity_id>/extra-fields/"""
    permission_classes = [IsSuperUser]
    lookup_url_kwarg = "pk"

    def get_queryset(self):
        activity_id = self.kwargs.get("activity_id")
        if not activity_id:
            return ErasmusActivityExtraField.objects.none()
        return ErasmusActivityExtraField.objects.filter(activity_id=activity_id).order_by("order", "id")

    @staticmethod
    def _normalize_options_cutoff_server_tz(options):
        """Return options with cutoff_iso in server timezone (YYYY-MM-DDTHH:mm:ss) for form display."""
        if not options or not isinstance(options, list):
            return options or []
        server_tz = timezone.get_current_timezone()
        result = []
        for opt in options:
            if not isinstance(opt, dict):
                result.append(opt)
                continue
            out = dict(opt)
            cutoff_iso = opt.get("cutoff_iso")
            if cutoff_iso:
                dt = parse_datetime(cutoff_iso)
                if dt:
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt, server_tz)
                    else:
                        dt = dt.astimezone(server_tz)
                    out["cutoff_iso"] = dt.strftime("%Y-%m-%dT%H:%M:%S")
            result.append(out)
        return result

    def _payload(self, obj):
        return {
            "id": obj.id,
            "field_key": obj.field_key,
            "label": obj.label,
            "type": obj.type,
            "required": obj.required,
            "placeholder": obj.placeholder or "",
            "help_text": obj.help_text or "",
            "order": obj.order,
            "is_active": obj.is_active,
            "options": self._normalize_options_cutoff_server_tz(obj.options or []),
        }

    def list(self, request, *args, **kwargs):
        activity_id = self.kwargs.get("activity_id")
        try:
            ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        items = [self._payload(obj) for obj in self.get_queryset()]
        return Response(items)

    def create(self, request, *args, **kwargs):
        activity_id = self.kwargs.get("activity_id")
        try:
            activity = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data
        field_key = (data.get("field_key") or "").strip().lower().replace(" ", "_")
        if not field_key:
            return Response({"detail": "field_key required"}, status=status.HTTP_400_BAD_REQUEST)
        if ErasmusActivityExtraField.objects.filter(activity=activity, field_key=field_key).exists():
            return Response({"detail": "field_key already exists for this activity"}, status=status.HTTP_400_BAD_REQUEST)
        obj = ErasmusActivityExtraField.objects.create(
            activity=activity,
            label=(data.get("label") or field_key).strip(),
            field_key=field_key,
            type=data.get("type", "text"),
            required=bool(data.get("required", False)),
            placeholder=(data.get("placeholder") or "")[:255],
            help_text=(data.get("help_text") or "").strip(),
            order=int(data.get("order", 0)),
            is_active=bool(data.get("is_active", True)),
            options=data.get("options") or [],
        )
        return Response(self._payload(obj), status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        return Response(self._payload(obj))

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        for key in ("label", "type", "required", "placeholder", "help_text", "order", "is_active", "options"):
            if key in request.data:
                if key == "order":
                    obj.order = int(request.data[key])
                elif key == "is_active":
                    obj.is_active = bool(request.data[key])
                elif key == "options":
                    obj.options = request.data[key] if isinstance(request.data[key], list) else []
                elif key == "required":
                    obj.required = bool(request.data[key])
                else:
                    setattr(obj, key, request.data[key] if key != "placeholder" else (request.data[key] or "")[:255])
        if "field_key" in request.data and request.data["field_key"]:
            fk = request.data["field_key"].strip().lower().replace(" ", "_")
            if ErasmusActivityExtraField.objects.filter(activity=obj.activity, field_key=fk).exclude(id=obj.id).exists():
                return Response({"detail": "field_key already exists for this activity"}, status=status.HTTP_400_BAD_REQUEST)
            obj.field_key = fk
        obj.save()
        return Response(self._payload(obj))

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


def _local_partner_payload(partner):
    """Build API dict for one ErasmusLocalPartner (includes asset_id, asset_url for media library)."""
    asset_url = None
    asset_filename = None
    if partner.asset_id and partner.asset and not getattr(partner.asset, "deleted_at", None):
        asset_url = getattr(partner.asset, "url", None)
        asset_filename = getattr(partner.asset, "original_filename", None)
    return {
        "id": partner.id,
        "name": partner.name,
        "role": partner.role or "",
        "bio": partner.bio or "",
        "instagram_username": (partner.instagram_username or "").strip().lstrip("@"),
        "whatsapp_number": partner.whatsapp_number or "",
        "order": partner.order,
        "is_active": partner.is_active,
        "asset_id": str(partner.asset_id) if partner.asset_id else None,
        "asset_url": asset_url,
        "asset_filename": asset_filename,
    }


class ErasmusLocalPartnerViewSet(viewsets.ModelViewSet):
    """CRUD for local partners (equipo). Photo from media library via asset_id."""
    permission_classes = [IsSuperUser]
    queryset = ErasmusLocalPartner.objects.all().select_related("asset").order_by("order", "id")

    def list(self, request, *args, **kwargs):
        return Response([_local_partner_payload(p) for p in self.get_queryset()])

    def create(self, request, *args, **kwargs):
        data = request.data
        name = (data.get("name") or "").strip()
        if not name:
            return Response({"detail": "name required"}, status=status.HTTP_400_BAD_REQUEST)
        asset_id = data.get("asset_id")
        asset = None
        if asset_id:
            try:
                asset = MediaAsset.objects.get(id=asset_id, deleted_at__isnull=True)
            except (MediaAsset.DoesNotExist, ValidationError, TypeError, ValueError):
                pass
        max_order = ErasmusLocalPartner.objects.aggregate(m=models.Max("order"))
        order = (max_order.get("m") or -1) + 1
        obj = ErasmusLocalPartner.objects.create(
            name=name,
            role=(data.get("role") or "").strip(),
            bio=(data.get("bio") or "").strip(),
            instagram_username=(data.get("instagram_username") or "").strip().lstrip("@"),
            whatsapp_number=(data.get("whatsapp_number") or "").strip(),
            order=int(data.get("order", order)),
            is_active=bool(data.get("is_active", True)),
            asset=asset,
        )
        return Response(_local_partner_payload(obj), status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        return Response(_local_partner_payload(self.get_object()))

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        for key in ("name", "role", "bio", "instagram_username", "whatsapp_number", "order", "is_active"):
            if key in request.data:
                if key == "name":
                    obj.name = (request.data[key] or "").strip()
                elif key == "order":
                    obj.order = int(request.data[key])
                elif key == "is_active":
                    obj.is_active = bool(request.data[key])
                else:
                    val = request.data[key]
                    if key == "instagram_username":
                        obj.instagram_username = (val or "").strip().lstrip("@")
                    else:
                        setattr(obj, key, (val or "").strip())
        if "asset_id" in request.data:
            aid = request.data["asset_id"]
            if not aid:
                obj.asset = None
            else:
                try:
                    obj.asset = MediaAsset.objects.get(id=aid, deleted_at__isnull=True)
                except (MediaAsset.DoesNotExist, ValidationError, TypeError, ValueError):
                    pass
        obj.save()
        return Response(_local_partner_payload(obj))

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


@api_view(["POST"])
@permission_classes([IsSuperUser])
def erasmus_inscription_payment_exclude_from_revenue(request, payment_id):
    """
    POST /api/v1/superadmin/erasmus/inscription-payments/<payment_id>/exclude_from_revenue/
    Body: { "exclude": true } or { "exclude": false }
    Marks an Erasmus activity inscription payment as excluded from revenue (cortesía) or included.
    """
    try:
        payment = ErasmusActivityInscriptionPayment.objects.get(id=payment_id)
    except ErasmusActivityInscriptionPayment.DoesNotExist:
        return Response(
            {"success": False, "detail": "Pago de inscripción no encontrado."},
            status=status.HTTP_404_NOT_FOUND,
        )
    data = request.data or {}
    exclude = data.get("exclude")
    if exclude is None:
        return Response(
            {"success": False, "detail": "Indica 'exclude': true o false en el body."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    exclude = bool(exclude)
    if payment.exclude_from_revenue == exclude:
        return Response(
            {
                "success": True,
                "message": "El pago ya tiene ese estado.",
                "exclude_from_revenue": payment.exclude_from_revenue,
            },
            status=status.HTTP_200_OK,
        )
    payment.exclude_from_revenue = exclude
    payment.save(update_fields=["exclude_from_revenue", "updated_at"])
    logger.info(
        "SuperAdmin ErasmusActivityInscriptionPayment id=%s exclude_from_revenue=%s",
        payment.id,
        payment.exclude_from_revenue,
    )
    return Response(
        {
            "success": True,
            "message": "Excluido del revenue." if exclude else "Incluido en revenue.",
            "exclude_from_revenue": payment.exclude_from_revenue,
        },
        status=status.HTTP_200_OK,
    )
