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
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_country_code = serializers.CharField(max_length=10)
    phone_number = serializers.CharField(max_length=20)
    instagram = serializers.CharField(max_length=100, required=False, allow_blank=True)

    stay_reason = serializers.ChoiceField(choices=["university", "practicas", "other"])
    stay_reason_detail = serializers.CharField(max_length=500, required=False, allow_blank=True)
    university = serializers.CharField(max_length=255, required=False, allow_blank=True)
    degree = serializers.CharField(max_length=255, required=False, allow_blank=True)

    arrival_date = serializers.DateField()
    departure_date = serializers.DateField()

    has_accommodation_in_chile = serializers.BooleanField(required=False, default=False)
    wants_rumi4students_contact = serializers.BooleanField(required=False, default=False)

    destinations = serializers.ListField(child=serializers.CharField(max_length=100), required=False, default=list)
    interested_experiences = serializers.ListField(child=serializers.CharField(max_length=100), required=False, default=list)
    interests = serializers.ListField(child=serializers.CharField(max_length=100), required=False, default=list)

    source_slug = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    utm_source = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    utm_medium = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    utm_campaign = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)

    extra_data = serializers.JSONField(required=False, default=dict)

    # Consent (T&C Especiales Registro Erasmus)
    accept_tc_erasmus = serializers.BooleanField(required=True)
    accept_privacy_erasmus = serializers.BooleanField(required=True)
    consent_email = serializers.BooleanField(required=False, default=False)
    consent_whatsapp = serializers.BooleanField(required=False, default=False)
    consent_share_providers = serializers.BooleanField(required=False, default=False)

    def validate_email(self, value):
        if value and isinstance(value, str):
            value = value.strip()
        return value or None

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
        return attrs

    def validate_extra_data(self, value):
        if not isinstance(value, dict):
            return {}
        extra_fields = {
            f.field_key: f
            for f in ErasmusExtraField.objects.filter(is_active=True)
        }
        allowed_keys = set(extra_fields.keys())
        unknown = set(value.keys()) - allowed_keys
        if unknown:
            value = {k: v for k, v in value.items() if k in allowed_keys}
        return value

    def create(self, validated_data):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        extra_data = validated_data.pop("extra_data", {}) or {}
        source_slug = validated_data.pop("source_slug", None) or None
        if source_slug == "":
            source_slug = None

        consent = {
            "accept_tc_erasmus": validated_data.pop("accept_tc_erasmus", False),
            "accept_privacy_erasmus": validated_data.pop("accept_privacy_erasmus", False),
            "consent_email": validated_data.pop("consent_email", False),
            "consent_whatsapp": validated_data.pop("consent_whatsapp", False),
            "consent_share_providers": validated_data.pop("consent_share_providers", False),
        }
        lead = ErasmusLead.objects.create(
            **validated_data,
            source_slug=source_slug,
            extra_data=extra_data,
            **consent,
        )

        # Complete Erasmus registration flow if flow_id was provided
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
                    flow_logger.complete(message="Erasmus registration completed")
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Erasmus: complete flow on lead create failed: %s", e)

        # Enviar guías por destino por WhatsApp (al menos una guía por cada destino seleccionado)
        try:
            from apps.erasmus.services import send_erasmus_guides_whatsapp
            send_erasmus_guides_whatsapp(lead)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Erasmus: send_erasmus_guides_whatsapp failed: %s", e)

        email = (validated_data.get("email") or "").strip()
        if email:
            from core.phone_utils import normalize_phone_e164
            phone_full = f"{validated_data.get('phone_country_code', '')}{validated_data.get('phone_number', '')}"
            normalized_phone = normalize_phone_e164(phone_full) if phone_full else ""
            if not User.objects.filter(email__iexact=email).exists():
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
