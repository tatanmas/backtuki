"""Serializers for Erasmus registration API."""

from rest_framework import serializers
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.erasmus.models import ErasmusLead, ErasmusExtraField
from apps.erasmus.options_data import get_erasmus_options


def validate_phone_with_phonenumbers(phone_country_code: str, phone_number: str) -> str:
    """Validate and return E.164 phone or raise ValidationError."""
    try:
        import phonenumbers
    except ImportError:
        # Fallback: basic digit check if phonenumbers not installed
        combined = (phone_country_code or "").replace("+", "").strip() + (phone_number or "").replace(" ", "")
        if not combined.isdigit() or len(combined) < 10:
            raise serializers.ValidationError("Número de teléfono inválido.")
        return f"+{combined}"

    raw = f"{phone_country_code or ''}{phone_number or ''}".replace(" ", "")
    if not raw.startswith("+"):
        raw = f"+{raw.lstrip('0')}"
    try:
        parsed = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException:
        raise serializers.ValidationError("Número de teléfono inválido.")
    if not phonenumbers.is_valid_number(parsed):
        raise serializers.ValidationError("Número de teléfono no válido para ese país.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class ErasmusRegisterSerializer(serializers.Serializer):
    """Payload for POST /api/v1/erasmus/register/."""

    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    nickname = serializers.CharField(max_length=100, required=False, allow_blank=True)
    birth_date = serializers.DateField()
    country = serializers.CharField(max_length=100, required=False, allow_blank=True)
    city = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    phone_country_code = serializers.CharField(max_length=10)
    phone_number = serializers.CharField(max_length=20)
    instagram = serializers.CharField(max_length=100, required=False, allow_blank=True)

    stay_reason = serializers.ChoiceField(choices=["university", "practicas", "other"])
    stay_reason_detail = serializers.CharField(max_length=500, required=False, allow_blank=True)
    university = serializers.CharField(max_length=255, required=False, allow_blank=True)
    degree = serializers.CharField(max_length=255, required=False, allow_blank=True)

    arrival_date = serializers.DateField(required=False, allow_null=True)
    departure_date = serializers.DateField(required=False, allow_null=True)

    budget_stay = serializers.CharField(max_length=200, required=False, allow_blank=True)

    has_accommodation_in_chile = serializers.BooleanField(required=False, default=False)
    wants_rumi4students_contact = serializers.BooleanField(required=False, default=False)

    destinations = serializers.ListField(child=serializers.CharField(max_length=100), required=False, default=list)
    interested_experiences = serializers.ListField(child=serializers.CharField(max_length=100), required=False, default=list)
    interests = serializers.ListField(child=serializers.CharField(max_length=100), required=False, default=list)

    source_slug = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    utm_source = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    utm_medium = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    utm_campaign = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)

    # Idioma con el que vieron el formulario (selector arriba). Para enviar mensaje de bienvenida en su idioma.
    form_locale = serializers.CharField(max_length=10, required=False, allow_blank=True, default="es")

    extra_data = serializers.JSONField(required=False, default=dict)

    # Consent (T&C Especiales Registro Erasmus)
    accept_tc_erasmus = serializers.BooleanField(required=True)
    accept_privacy_erasmus = serializers.BooleanField(required=True)
    consent_email = serializers.BooleanField(required=False, default=False)
    consent_whatsapp = serializers.BooleanField(required=False, default=False)
    consent_share_providers = serializers.BooleanField(required=False, default=False)

    # Community directory
    languages_spoken = serializers.ListField(
        child=serializers.CharField(max_length=20), required=False, default=list
    )
    opt_in_community = serializers.BooleanField(required=False, default=True)
    community_bio = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    community_show_dates = serializers.BooleanField(required=False, default=True)
    community_show_age = serializers.BooleanField(required=False, default=True)
    community_show_whatsapp = serializers.BooleanField(required=False, default=False)

    def validate_email(self, value):
        """Email is optional; if provided, validate format. Magic-login supports leads without email."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        value = value.strip() if isinstance(value, str) else value
        # Use parent EmailField validation for format when present
        return value

    def validate_phone_number(self, value):
        country_code = self.initial_data.get("phone_country_code") or ""
        try:
            validate_phone_with_phonenumbers(country_code, value)
        except serializers.ValidationError as e:
            raise serializers.ValidationError(e.detail)
        return value

    def validate_departure_date(self, value):
        arrival_raw = self.initial_data.get("arrival_date")
        arrival = parse_date(arrival_raw) if isinstance(arrival_raw, str) else arrival_raw
        if hasattr(arrival, "date") and callable(getattr(arrival, "date")):
            arrival = arrival.date()
        if arrival and value and value < arrival:
            raise serializers.ValidationError("La fecha de vuelta debe ser posterior a la de llegada.")
        return value

    def validate(self, attrs):
        reason = attrs.get("stay_reason")
        if reason == "university":
            if not (attrs.get("university") or "").strip():
                raise serializers.ValidationError({"university": "Indica la universidad donde estudiarás."})
            if not (attrs.get("degree") or "").strip():
                raise serializers.ValidationError({"degree": "Indica la carrera o programa."})
        if attrs.get("opt_in_community"):
            instagram = (attrs.get("instagram") or "").strip().lstrip("@")
            if not instagram:
                raise serializers.ValidationError({"instagram": "Si quieres aparecer en la comunidad, indica tu Instagram."})
        return attrs

    # Quiz de perfil (paso 6): claves fijas que se guardan en extra_data sin ErasmusExtraField
    QUIZ_EXTRA_KEYS = {
        "quiz_accommodation",
        "quiz_saturday",
        "quiz_physical",
        "quiz_social",
        "quiz_travel_style",
        "quiz_avoid",
    }
    # Housing (Rumi): cuando wants_rumi4students_contact, el front envía esto en extra_data
    HOUSING_EXTRA_KEYS = {
        "accommodation_help_where",
        "accommodation_help_budget_monthly",
        "accommodation_help_types",
    }

    def validate_extra_data(self, value):
        if not isinstance(value, dict):
            return {}
        extra_fields = {
            f.field_key: f
            for f in ErasmusExtraField.objects.filter(is_active=True)
        }
        allowed_keys = set(extra_fields.keys()) | self.QUIZ_EXTRA_KEYS | self.HOUSING_EXTRA_KEYS
        unknown = set(value.keys()) - allowed_keys
        if unknown:
            value = {k: v for k, v in value.items() if k in allowed_keys}
        return value

    def create(self, validated_data):
        import secrets
        from django.contrib.auth import get_user_model
        User = get_user_model()

        extra_data = validated_data.pop("extra_data", {}) or {}
        source_slug = validated_data.pop("source_slug", None) or None
        if source_slug == "":
            source_slug = None
        form_locale = (validated_data.pop("form_locale", None) or "").strip().lower() or "es"
        if form_locale not in ("es", "en", "pt", "de", "it", "fr"):
            form_locale = "es"
        languages_spoken = validated_data.pop("languages_spoken", []) or []
        opt_in_community = validated_data.pop("opt_in_community", True)
        community_bio = (validated_data.pop("community_bio", None) or "").strip()[:2000]
        community_show_dates = validated_data.pop("community_show_dates", True)
        community_show_age = validated_data.pop("community_show_age", True)
        community_show_whatsapp = validated_data.pop("community_show_whatsapp", False)

        consent = {
            "accept_tc_erasmus": validated_data.pop("accept_tc_erasmus", False),
            "accept_privacy_erasmus": validated_data.pop("accept_privacy_erasmus", False),
            "consent_email": validated_data.pop("consent_email", False),
            "consent_whatsapp": validated_data.pop("consent_whatsapp", False),
            "consent_share_providers": validated_data.pop("consent_share_providers", False),
        }
        community_profile_token = secrets.token_urlsafe(32)
        # Instagram: guardar siempre sin @
        if "instagram" in validated_data and validated_data["instagram"]:
            validated_data["instagram"] = (validated_data["instagram"] or "").strip().lstrip("@")[:100]
        lead = ErasmusLead.objects.create(
            **validated_data,
            source_slug=source_slug,
            form_locale=form_locale,
            extra_data=extra_data,
            languages_spoken=languages_spoken,
            opt_in_community=opt_in_community,
            community_bio=community_bio,
            community_show_dates=community_show_dates,
            community_show_age=community_show_age,
            community_show_whatsapp=community_show_whatsapp,
            community_profile_token=community_profile_token,
            **consent,
        )

        # Erasmus registration flow: update metadata, log form submitted, then WhatsApp result, then complete
        flow_id = self.context.get("flow_id")
        if flow_id:
            try:
                from core.flow_logger import FlowLogger
                flow_logger = FlowLogger.from_flow_id(flow_id)
                if flow_logger and flow_logger.flow and flow_logger.flow.status == "in_progress":
                    flow_logger.flow.metadata = dict(flow_logger.flow.metadata or {})
                    flow_logger.flow.metadata["erasmus_lead_id"] = str(lead.id)
                    flow_logger.flow.save(update_fields=["metadata"])
                    flow_logger.log_event(
                        "ERASMUS_FORM_SUBMITTED",
                        source="api",
                        status="success",
                        message="Erasmus lead created",
                        metadata={"erasmus_lead_id": str(lead.id)},
                    )
                    # Enviar guías por destino por WhatsApp y registrar resultado en el flow
                    from apps.erasmus.services import send_erasmus_guides_whatsapp
                    whatsapp_result = send_erasmus_guides_whatsapp(lead)
                    if whatsapp_result.get("ok"):
                        flow_logger.log_event(
                            "ERASMUS_WHATSAPP_GUIDES_SENT",
                            source="api",
                            status="success",
                            message="Guías enviadas por WhatsApp al lead",
                        )
                    else:
                        flow_logger.log_event(
                            "ERASMUS_WHATSAPP_GUIDES_FAILED",
                            source="api",
                            status="failure",
                            message="Fallo envío guías por WhatsApp",
                            metadata={"error": whatsapp_result.get("error") or "Unknown error"},
                        )
                    flow_logger.complete(message="Erasmus registration completed")
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Erasmus: complete flow on lead create failed: %s", e)
        else:
            # No flow_id: still send WhatsApp (same as before) but no flow events
            try:
                from apps.erasmus.services import send_erasmus_guides_whatsapp
                send_erasmus_guides_whatsapp(lead)
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Erasmus: send_erasmus_guides_whatsapp failed: %s", e)

        # Notificar a Rumi (grupo configurado en SuperAdmin) si el lead pidió contacto para housing
        try:
            from apps.erasmus.partner_notifications import notify_rumi_housing_lead
            notify_rumi_housing_lead(lead)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Erasmus: notify_rumi_housing_lead failed: %s", e)

        email = (validated_data.get("email") or "").strip()
        if email:
            from core.phone_utils import normalize_phone_e164
            phone_full = f"{validated_data.get('phone_country_code', '')}{validated_data.get('phone_number', '')}"
            normalized_phone = normalize_phone_e164(phone_full) if phone_full else ""
            existing = User.objects.filter(email__iexact=email).first()
            if existing:
                lead.user = existing
                lead.save(update_fields=["user"])
            else:
                try:
                    user = User.create_guest_user(
                        email=email,
                        first_name=validated_data.get("first_name"),
                        last_name=validated_data.get("last_name"),
                        phone=normalized_phone or phone_full or None,
                    )
                    lead.user = user
                    lead.save(update_fields=["user"])
                except Exception:
                    # Lead is already saved; optional user link failed (e.g. DB/constraint)
                    raise
        return lead
