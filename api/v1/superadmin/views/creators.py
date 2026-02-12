"""
SuperAdmin TUKI Creators list.
Enterprise: list all creator profiles for admin oversight.
"""

import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.creators.models import CreatorProfile
from apps.experiences.models import ExperienceReservation
from django.db.models import Count, Sum, Q

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)


class SuperAdminCreatorsListView(APIView):
    """
    List all TUKI Creators (SuperAdmin only).
    GET /api/v1/superadmin/creators/
    Returns creators with user email and basic stats.
    """
    permission_classes = [IsSuperUser]

    def get(self, request):
        creators = (
            CreatorProfile.objects
            .select_related('user')
            .annotate(
                reservations_count=Count(
                    'experience_reservations',
                    filter=Q(experience_reservations__status='paid'),
                    distinct=True,
                ),
                earned_total=Sum(
                    'experience_reservations__creator_commission_amount',
                    filter=Q(
                        experience_reservations__status='paid',
                        experience_reservations__creator_commission_status='earned',
                    ),
                    distinct=False,
                ),
                paid_total=Sum(
                    'experience_reservations__creator_commission_amount',
                    filter=Q(
                        experience_reservations__status='paid',
                        experience_reservations__creator_commission_status='paid',
                    ),
                    distinct=False,
                ),
            )
            .order_by('-created_at')
        )
        results = []
        for c in creators:
            results.append({
                'id': str(c.id),
                'display_name': c.display_name,
                'slug': c.slug,
                'email': c.user.email if c.user_id else None,
                'phone': c.phone or '',
                'is_approved': c.is_approved,
                'created_at': c.created_at.isoformat() if c.created_at else None,
                'updated_at': c.updated_at.isoformat() if c.updated_at else None,
                'reservations_count': c.reservations_count or 0,
                'earned_total': float(c.earned_total or 0),
                'paid_total': float(c.paid_total or 0),
            })
        return Response({'results': results, 'count': len(results)})
