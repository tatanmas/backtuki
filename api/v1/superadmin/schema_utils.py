"""
Schema and instructions for Superadmin JSON upload flow.
Used by GET /api/v1/superadmin/schema/<entity>/ to return schema + instructions for LLM.
"""

from rest_framework import serializers


def _serializer_field_to_schema(name, field):
    """Introspect a DRF serializer field and return a schema dict."""
    info = {
        "required": getattr(field, "required", True),
        "read_only": getattr(field, "read_only", False),
    }
    if getattr(field, "help_text", None):
        info["help_text"] = str(field.help_text)
    if getattr(field, "default", serializers.empty) is not serializers.empty:
        info["default"] = field.default
    if hasattr(field, "choices") and field.choices:
        choices = field.choices
        if isinstance(choices, dict):
            info["choices"] = list(choices.keys())
        else:
            info["choices"] = [c[0] for c in choices]
    if hasattr(field, "max_length") and field.max_length is not None:
        info["max_length"] = field.max_length
    if hasattr(field, "min_value") and field.min_value is not None:
        info["min_value"] = field.min_value
    if hasattr(field, "max_value") and field.max_value is not None:
        info["max_value"] = field.max_value
    if hasattr(field, "min_length") and field.min_length is not None:
        info["min_length"] = field.min_length
    if hasattr(field, "max_length") and field.max_length is not None:
        info["max_length"] = field.max_length
    # Type from field class
    for cls, type_name in [
        (serializers.CharField, "string"),
        (serializers.SlugField, "string"),
        (serializers.IntegerField, "integer"),
        (serializers.DecimalField, "number"),
        (serializers.FloatField, "number"),
        (serializers.BooleanField, "boolean"),
        (serializers.DateField, "date"),
        (serializers.DateTimeField, "datetime"),
        (serializers.ListField, "array"),
        (serializers.DictField, "object"),
        (serializers.URLField, "string"),
        (serializers.UUIDField, "uuid"),
        (serializers.ChoiceField, "string"),
        (serializers.EmailField, "string"),
    ]:
        if isinstance(field, cls):
            info["type"] = type_name
            break
    else:
        info["type"] = "unknown"
    return info


def get_serializer_schema(serializer_class):
    """Build a schema dict from a DRF Serializer class."""
    serializer = serializer_class()
    fields = {}
    for name, field in serializer.fields.items():
        if field.read_only:
            continue
        fields[name] = _serializer_field_to_schema(name, field)
    return {"type": "object", "fields": fields}


# Instructions per entity for LLM to generate valid JSON. Keep in sync with create-from-json payloads.
ENTITY_INSTRUCTIONS = {
    "experience": """Genera un JSON válido para crear una experiencia (tour) en Tuki.
El objeto debe contener los campos que espera la API de creación desde JSON.
Campos requeridos típicos: title, description. Para tours con reserva WhatsApp: is_whatsapp_reservation=true, price, currency (CLP).
Opcionales: short_description, slug, status (draft|published), type (tour|activity|...), duration_minutes, location_name, itinerary (array), images (array de URLs), recurrence_pattern, date_price_overrides.
Opcional: reviews (array de objetos). Cada reseña: author_name (string), rating (1-5), body o text (string), review_date (YYYY-MM-DD opcional), source (string opcional, ej. google, getyourguide). Puedes pegar reseñas en bruto y la IA las ordenará en este formato.
Fechas en YYYY-MM-DD. Precios en número (ej. 15000 para $15.000 CLP).
Consulta el schema devuelto por GET /api/v1/superadmin/schema/experience/ para la lista exacta de campos y tipos.""",

    "accommodation": """Genera un JSON válido para crear un alojamiento en Tuki.
El objeto debe tener al menos: title. Opcional: organizer_id (UUID; si no se envía, el alojamiento queda vinculado al superadmin).
Otros campos: slug (o se genera del título), description, short_description, status (draft|published|cancelled), property_type (cabin|house|apartment|hotel|hostel|villa|other),
location_name, location_address, country, city, latitude, longitude, guests, bedrooms, full_bathrooms, half_bathrooms (o legacy bathrooms: entero o 4.5 → 4 completos + 1 medio), beds, price, currency (CLP), amenities (array de strings), not_amenities (array).
min_nights (entero, opcional): mínimo de noches para reservar; si no se define, se hereda de la central de arrendamiento o del hotel.
Para unidades de central de arrendamiento: rental_hub_id (UUID), unit_type, tower, floor, unit_number, square_meters (mismo formato que alojamientos normales).
Opcional: reviews (array de objetos). Cada reseña: author_name (obligatorio), rating (1-5), text o body (texto), review_date (YYYY-MM-DD), author_location, stay_type, host_reply. Si envías reviews, se calculan rating_avg y review_count automáticamente. También puedes enviar rating_avg (número 1-5, ej. 4.9; si envías 4.93 se guarda como 4.9) y review_count sin reviews.
Consulta el schema en GET /api/v1/superadmin/schema/accommodation/ para la lista exacta.""",

    "destination": """Genera un JSON válido para crear un destino (LandingDestination) en Tuki.
Campos requeridos: name, slug. Opcionales: country, region, description, hero_image (URL), hero_media_id (UUID), gallery_media_ids (array de UUIDs), images (array URLs), latitude, longitude, is_active,
travel_guides (array de objetos), transportation (array), accommodation_ids (array UUIDs), experience_ids (array UUIDs), event_ids (array UUIDs), featured_type, featured_id.
Consulta el schema en GET /api/v1/superadmin/schema/destination/ para la lista exacta.""",

    "erasmus_lead": """Genera un JSON para cargar uno o más leads Erasmus. Formato: { "leads": [ {...}, ... ], "allow_incomplete": false }.
Cada lead: obligatorios (carga completa): first_name, last_name, birth_date (YYYY-MM-DD), phone_country_code, phone_number, stay_reason (university|practicas|other), arrival_date, departure_date (YYYY-MM-DD).
Con allow_incomplete=true solo son obligatorios: first_name, last_name, phone_country_code, phone_number; el resto opcional (lead queda "Por completar").
Opcionales: nickname, country, city, email, instagram, university, degree, budget_stay, destinations (array), interests (array), extra_data (objeto), consent_*, accept_tc_erasmus, accept_privacy_erasmus.
Consulta GET /api/v1/superadmin/schema/erasmus_lead/ y docs/CARGA_LEADS_ERASMUS.md.""",

    "erasmus_timeline_item": """Genera un JSON para crear ítems del timeline Erasmus. Formato: { "items": [ {...}, ... ] } o un solo objeto.
Cada ítem: title_es, title_en (strings), location (string), image (URL opcional), scheduled_date (YYYY-MM-DD), display_order (entero), experience_id (UUID opcional), is_active (boolean).
Consulta GET /api/v1/superadmin/schema/erasmus_timeline_item/ para la lista exacta.""",

    "bank_statement": """Genera un JSON para importar una cartola bancaria en Tuki.
Formato: { "bank_account_id": "uuid" o "bank_account_name": "nombre exacto", "lines": [ {...}, ... ] }.
Cada línea: statement_date (YYYY-MM-DD, obligatorio), value_date (YYYY-MM-DD, opcional), external_reference (string), description (string), amount (número: positivo=ingreso, negativo=egreso), balance_after (número opcional).
Fechas en YYYY-MM-DD. Montos en CLP. Referencia: docs/CARGA_CARTOLAS_BANCARIAS.md y carga/cartolas/ejemplo_cartola.json.""",

    "vendor_bill": """Genera un JSON para cargar facturas de proveedor (VendorBill) en Tuki.
Formato: { "bills": [ {...}, ... ] }. Cada factura puede incluir vendor (objeto con name, tax_id, ...) para crear proveedor si no existe, o vendor_id (UUID).
Campos obligatorios: bill_number, issue_date (YYYY-MM-DD), due_date (YYYY-MM-DD), total_amount. Opcionales: subtotal_amount, tax_amount, currency (CLP), description, external_reference, expense_lines (array).
expense_lines: expense_category_id, tax_treatment_id, cost_center_id (opcional), description, net_amount, tax_amount, gross_amount.
Referencia: docs/CARGA_FACTURAS.md y carga/facturas/ejemplo_facturas.json.""",

    "external_revenue": """Genera un JSON para cargar revenue externo (eventos pre-plataforma, Excel histórico) en Tuki.
Formato: { "records": [ {...}, ... ] } o array directo. Cada registro: external_reference (obligatorio), effective_date (YYYY-MM-DD obligatorio), gross_amount, platform_fee_amount, payable_amount.
organizer_id (UUID): opcional; si no se envía, el registro queda "huérfano" (solo para reportes).
already_paid (boolean): true = ya fue pagado/transferido al organizador (eventos pre-plataforma). Default false.
Opcionales: source_type (manual, event_order, etc.), source_system, product_label, description, currency (CLP), event_id, experience_id, accommodation_id, car_id.
Referencia: docs/CARGA_REVENUE_EXTERNO.md y carga/revenue-externo/ejemplo_revenue.json.""",
}

# Static schema for entities that don't use a DRF serializer (or not yet)
ERASMUS_LEAD_SCHEMA = {
    "type": "object",
    "fields": {
        "first_name": {"type": "string", "required": True, "max_length": 150},
        "last_name": {"type": "string", "required": True, "max_length": 150},
        "birth_date": {"type": "date", "required": False, "help_text": "YYYY-MM-DD"},
        "phone_country_code": {"type": "string", "required": True, "max_length": 10},
        "phone_number": {"type": "string", "required": True, "max_length": 20},
        "stay_reason": {"type": "string", "required": True, "choices": ["university", "practicas", "other"]},
        "arrival_date": {"type": "date", "required": False, "help_text": "YYYY-MM-DD"},
        "departure_date": {"type": "date", "required": False, "help_text": "YYYY-MM-DD"},
        "budget_stay": {"type": "string", "required": False, "help_text": "Presupuesto aproximado para viajes durante el intercambio (estancias, paseos, experiencias)"},
        "nickname": {"type": "string", "required": False},
        "country": {"type": "string", "required": False},
        "city": {"type": "string", "required": False},
        "email": {"type": "string", "required": False},
        "instagram": {"type": "string", "required": False},
        "university": {"type": "string", "required": False},
        "degree": {"type": "string", "required": False},
        "destinations": {"type": "array", "required": False},
        "interests": {"type": "array", "required": False},
        "extra_data": {"type": "object", "required": False},
    },
}

ERASMUS_TIMELINE_ITEM_SCHEMA = {
    "type": "object",
    "fields": {
        "title_es": {"type": "string", "required": True},
        "title_en": {"type": "string", "required": False, "allow_blank": True},
        "location": {"type": "string", "required": False, "allow_blank": True},
        "image": {"type": "string", "required": False, "help_text": "URL"},
        "scheduled_date": {"type": "date", "required": False, "help_text": "YYYY-MM-DD"},
        "display_order": {"type": "integer", "required": False, "default": 0},
        "experience_id": {"type": "uuid", "required": False},
        "is_active": {"type": "boolean", "required": False, "default": True},
    },
}

BANK_STATEMENT_SCHEMA = {
    "type": "object",
    "fields": {
        "bank_account_id": {"type": "uuid", "required": False, "help_text": "UUID de la cuenta; alternativamente usar bank_account_name"},
        "bank_account_name": {"type": "string", "required": False, "help_text": "Nombre exacto de la cuenta"},
        "lines": {"type": "array", "required": True, "help_text": "Array de líneas. Cada línea: statement_date, value_date?, external_reference?, description?, amount, balance_after?"},
    },
}

VENDOR_BILL_SCHEMA = {
    "type": "object",
    "fields": {
        "bills": {"type": "array", "required": True, "help_text": "Array de facturas. Cada una: vendor_id o vendor (objeto), bill_number, issue_date, due_date, total_amount, expense_lines?"},
    },
}

EXTERNAL_REVENUE_SCHEMA = {
    "type": "object",
    "fields": {
        "records": {"type": "array", "required": True, "help_text": "Array de registros. Cada uno: external_reference, effective_date, gross_amount, organizer_id?, already_paid?"},
    },
}
