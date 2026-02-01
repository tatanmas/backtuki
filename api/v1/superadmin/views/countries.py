"""
SuperAdmin Countries Views
Endpoints para gestión de países.
"""

from rest_framework import viewsets
import logging

from core.models import Country
from core.serializers import CountrySerializer

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)

class CountryViewSet(viewsets.ModelViewSet):
    """
    🚀 ENTERPRISE: Country Management ViewSet for SuperAdmin.
    
    Allows SuperAdmin to manage countries for categorizing experiences and accommodations.
    """
    
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [IsSuperUser]  # ENTERPRISE: Solo superusers
    
    def get_queryset(self):
        """Return active countries by default, or all if requested."""
        queryset = Country.objects.all()
        active_only = self.request.query_params.get('active_only', 'true')
        if active_only.lower() == 'true':
            queryset = queryset.filter(is_active=True)
        return queryset.order_by('display_order', 'name')


