"""Superadmin views for Erasmus: leads, tracking links, extra fields (dynamic form questions)."""

import csv
import json
import logging
from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpResponse
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
    ErasmusActivityInstance,
    ErasmusWhatsAppGroup,
)
from apps.media.models import MediaAsset
from apps.erasmus.lead_import import (
    normalize_lead,
    REQUIRED_KEYS_FULL,
    REQUIRED_KEYS_INCOMPLETE,
)
from api.v1.superadmin.serializers import (
    JsonErasmusTimelineItemSerializer,
    JsonErasmusActivityCreateSerializer,
    JsonErasmusActivityInstanceSerializer,
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
        "arrival_date", "departure_date", "has_accommodation_in_chile", "wants_rumi4students_contact",
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
        return Response(_lead_to_dict(lead))

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
        lead.completion_status = "complete"
        update_fields = [
            "first_name", "last_name", "nickname", "birth_date", "country", "city", "email",
            "phone_country_code", "phone_number", "instagram",
            "stay_reason", "stay_reason_detail", "university", "degree",
            "arrival_date", "departure_date",
            "has_accommodation_in_chile", "wants_rumi4students_contact",
            "destinations", "interested_experiences", "interests", "extra_data",
            "accept_tc_erasmus", "accept_privacy_erasmus", "consent_email", "consent_whatsapp", "consent_share_providers",
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
        "experience_id": str(act.experience_id) if act.experience_id else None,
        "created_at": act.created_at.isoformat() if act.created_at else None,
        "updated_at": act.updated_at.isoformat() if act.updated_at else None,
    }
    if include_instances:
        data["instances"] = [
            {
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
            }
            for inst in act.instances.order_by("display_order", "scheduled_date", "scheduled_year", "scheduled_month")
        ]
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


class ErasmusActivityListView(APIView):
    """GET /api/v1/superadmin/erasmus/activities/ – list all activities (optional: is_active, search)."""
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
        result = [_activity_to_dict(act) for act in qs]
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
            act.itinerary = data["itinerary"] if isinstance(data["itinerary"], list) else []
        if "images" in data:
            act.images = _normalize_images(data["images"] if isinstance(data["images"], list) else [])
        if "display_order" in data:
            act.display_order = int(data["display_order"]) if data["display_order"] is not None else 0
        if "is_active" in data:
            act.is_active = bool(data["is_active"])
        if "experience_id" in data:
            act.experience_id = data["experience_id"] if data["experience_id"] else None
        act.save()
        return Response(_activity_to_dict(act, include_instances=True))


class ErasmusActivityInstanceListCreateView(APIView):
    """GET/POST /api/v1/superadmin/erasmus/activities/<activity_id>/instances/"""
    permission_classes = [IsSuperUser]

    def get(self, request, activity_id):
        try:
            act = ErasmusActivity.objects.get(id=activity_id)
        except ErasmusActivity.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        instances = [
            {
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
            }
            for inst in act.instances.order_by("display_order", "scheduled_date", "scheduled_year", "scheduled_month")
        ]
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
        return Response({
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
        })

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
        try:
            inst.full_clean()
            inst.save()
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
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
        })

    def delete(self, request, activity_id, instance_id):
        try:
            inst = ErasmusActivityInstance.objects.get(id=instance_id, activity_id=activity_id)
        except ErasmusActivityInstance.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        inst.delete()
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
            self.get_queryset().values("id", "name", "link", "order", "is_active")
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
        obj = ErasmusWhatsAppGroup.objects.create(
            name=name, link=link, order=order, is_active=is_active
        )
        return Response(
            {"id": obj.id, "name": obj.name, "link": obj.link, "order": obj.order, "is_active": obj.is_active},
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        return Response({
            "id": obj.id, "name": obj.name, "link": obj.link, "order": obj.order, "is_active": obj.is_active,
        })

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        if "name" in request.data:
            obj.name = (request.data["name"] or "").strip()
        if "link" in request.data:
            obj.link = (request.data["link"] or "").strip()
        if "order" in request.data:
            obj.order = int(request.data["order"])
        if "is_active" in request.data:
            obj.is_active = bool(request.data["is_active"])
        obj.save()
        return Response({
            "id": obj.id, "name": obj.name, "link": obj.link, "order": obj.order, "is_active": obj.is_active,
        })

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


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
        obj = ErasmusWhatsAppGroup.objects.create(
            name=name, link=link, order=i, is_active=True
        )
        created.append({"id": obj.id, "name": obj.name, "link": obj.link, "order": obj.order})
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
