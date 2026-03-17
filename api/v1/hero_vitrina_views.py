"""
Public API: Hero vitrina (landing) — ordered list of content_type + object_id for the hero slider.
No authentication required.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from apps.creators.models import HeroVitrinaItem


@api_view(['GET'])
@permission_classes([AllowAny])
def hero_vitrina_list(request):
    """
    GET /api/v1/hero-vitrina/
    Returns ordered list of { id, content_type, object_id, order } for the landing hero slider.
    Frontend resolves IDs to full experience/accommodation/event/car data.
    """
    items = HeroVitrinaItem.objects.all().order_by('order', 'created_at')
    payload = [
        {
            'id': str(item.id),
            'content_type': item.content_type,
            'object_id': str(item.object_id),
            'order': item.order,
        }
        for item in items
    ]
    return Response(payload)
