"""
SuperAdmin Schema API: GET /api/v1/superadmin/schema/<entity>/
Returns schema + instructions for JSON upload flow (for LLM-assisted JSON generation).
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..permissions import IsSuperUser
from ..schema_utils import (
    get_serializer_schema,
    ENTITY_INSTRUCTIONS,
    ERASMUS_LEAD_SCHEMA,
    ERASMUS_TIMELINE_ITEM_SCHEMA,
    BANK_STATEMENT_SCHEMA,
    VENDOR_BILL_SCHEMA,
    EXTERNAL_REVENUE_SCHEMA,
)
from ..serializers import (
    JsonExperienceCreateSerializer,
    JsonAccommodationCreateSerializer,
    JsonDestinationCreateSerializer,
    JsonErasmusTimelineItemSerializer,
)

VALID_ENTITIES = {
    "experience",
    "accommodation",
    "destination",
    "erasmus_lead",
    "erasmus_timeline_item",
    "bank_statement",
    "vendor_bill",
    "external_revenue",
}


@api_view(["GET"])
@permission_classes([IsSuperUser])
def schema_for_entity(request, entity):
    """
    GET /api/v1/superadmin/schema/<entity>/
    Returns { "schema": {...}, "instructions": "..." } for the given entity.
    Entity: experience | accommodation | destination | erasmus_lead | erasmus_timeline_item
    """
    entity = (entity or "").strip().lower()
    if entity not in VALID_ENTITIES:
        return Response(
            {
                "detail": f"Entidad no válida. Use una de: {', '.join(sorted(VALID_ENTITIES))}.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    instructions = ENTITY_INSTRUCTIONS.get(entity, "")

    if entity == "experience":
        schema = get_serializer_schema(JsonExperienceCreateSerializer)
    elif entity == "accommodation":
        schema = get_serializer_schema(JsonAccommodationCreateSerializer)
    elif entity == "destination":
        schema = get_serializer_schema(JsonDestinationCreateSerializer)
    elif entity == "erasmus_lead":
        schema = ERASMUS_LEAD_SCHEMA
    elif entity == "erasmus_timeline_item":
        schema = get_serializer_schema(JsonErasmusTimelineItemSerializer)
    elif entity == "bank_statement":
        schema = BANK_STATEMENT_SCHEMA
    elif entity == "vendor_bill":
        schema = VENDOR_BILL_SCHEMA
    elif entity == "external_revenue":
        schema = EXTERNAL_REVENUE_SCHEMA
    else:
        schema = {"type": "object", "fields": {}}

    return Response({
        "entity": entity,
        "schema": schema,
        "instructions": instructions,
    })
