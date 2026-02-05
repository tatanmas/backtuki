"""Views for TUKI Creators API."""

import logging
from decimal import Decimal
from django.db.models import Sum, Count

from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.creators.models import CreatorProfile, CreatorRecommendedExperience, PlatformLandingSlot, Relato
from apps.experiences.models import Experience, ExperienceReservation

from .serializers import (
    CreatorProfilePublicSerializer,
    CreatorProfileMeSerializer,
    ExperienceMinimalSerializer,
    RelatoListSerializer,
    RelatoDetailSerializer,
    RelatoPublicSerializer,
)

logger = logging.getLogger(__name__)

# Default slot keys for TUKI Creators landing (created on first read if missing)
DEFAULT_LANDING_SLOT_KEYS = [
    'creators_landing_hero',
    'creators_landing_bento_1',
    'creators_landing_bento_2',
]


class LandingSlotsPublicView(APIView):
    """
    Public: get image URLs for creators landing slots.
    GET /api/v1/creators/landing-slots/
    Returns: { slot_key: { url: string, asset_id: string | null } }
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # Ensure default slots exist
        for key in DEFAULT_LANDING_SLOT_KEYS:
            PlatformLandingSlot.objects.get_or_create(slot_key=key, defaults={'asset_id': None})
        slots = PlatformLandingSlot.objects.filter(slot_key__in=DEFAULT_LANDING_SLOT_KEYS).select_related('asset')
        result = {}
        for slot in slots:
            url = None
            asset_id = None
            if slot.asset_id and slot.asset and not slot.asset.deleted_at:
                url = slot.asset.url
                asset_id = str(slot.asset.id)
            result[slot.slot_key] = {'url': url, 'asset_id': asset_id}
        return Response(result)


class PublicCreatorProfileView(APIView):
    """
    Public profile by slug.
    GET /api/v1/creators/public/<slug>/
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, slug):
        try:
            profile = CreatorProfile.objects.prefetch_related(
                'recommended_experiences__experience'
            ).get(slug=slug)
        except CreatorProfile.DoesNotExist:
            return Response(
                {'error': 'Creator not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        # Only show approved creators publicly (optional: show all for testing)
        if not profile.is_approved:
            return Response(
                {'error': 'Creator not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = CreatorProfilePublicSerializer(profile)
        return Response(serializer.data)


class CreatorMeView(APIView):
    """
    Authenticated creator: get or update my profile.
    GET /api/v1/creators/me/
    PATCH /api/v1/creators/me/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_creator(self, request):
        if not request.user.is_authenticated:
            return None
        try:
            return CreatorProfile.objects.get(user=request.user)
        except CreatorProfile.DoesNotExist:
            return None
    
    def get(self, request):
        creator = self.get_creator(request)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.', 'has_profile': False},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = CreatorProfileMeSerializer(creator)
        return Response({**serializer.data, 'has_profile': True})
    
    def patch(self, request):
        creator = self.get_creator(request)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = CreatorProfileMeSerializer(creator, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CreatorRecommendedExperiencesView(APIView):
    """
    Manage recommended experiences (Mis Recomendados).
    GET /api/v1/creators/me/recommended-experiences/
    POST /api/v1/creators/me/recommended-experiences/  body: { "experience_id": "uuid" }
    DELETE /api/v1/creators/me/recommended-experiences/<experience_id>/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_creator(self, request):
        if not request.user.is_authenticated:
            return None
        try:
            return CreatorProfile.objects.get(user=request.user)
        except CreatorProfile.DoesNotExist:
            return None
    
    def get(self, request):
        creator = self.get_creator(request)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        recs = creator.recommended_experiences.select_related('experience').order_by('order')
        data = [ExperienceMinimalSerializer(r.experience).data for r in recs]
        return Response(data)
    
    def post(self, request):
        creator = self.get_creator(request)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        experience_id = request.data.get('experience_id')
        if not experience_id:
            return Response(
                {'error': 'experience_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            experience = Experience.objects.get(
                id=experience_id,
                status='published',
                is_active=True,
                deleted_at__isnull=True,
            )
        except Experience.DoesNotExist:
            return Response(
                {'error': 'Experience not found or not available'},
                status=status.HTTP_404_NOT_FOUND
            )
        _, created = CreatorRecommendedExperience.objects.get_or_create(
            creator=creator,
            experience=experience,
            defaults={'order': creator.recommended_experiences.count()},
        )
        return Response(
            ExperienceMinimalSerializer(experience).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
    
    def delete(self, request, experience_id=None, **kwargs):
        experience_id = experience_id or kwargs.get('experience_id')
        if not experience_id:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        creator = self.get_creator(request)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        deleted, _ = CreatorRecommendedExperience.objects.filter(
            creator=creator,
            experience_id=experience_id,
        ).delete()
        if not deleted:
            return Response(
                {'error': 'Experience was not in your recommended list'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------- Relatos ----------

class RelatosMeView(APIView):
    """
    Creator: list my relatos, create one.
    GET /api/v1/creators/me/relatos/
    POST /api/v1/creators/me/relatos/  body: { title, slug, body?, status?, experience? }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_creator(self, request):
        if not request.user.is_authenticated:
            return None
        try:
            return CreatorProfile.objects.get(user=request.user)
        except CreatorProfile.DoesNotExist:
            return None

    def get(self, request):
        creator = self.get_creator(request)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        relatos = Relato.objects.filter(creator=creator).order_by('-created_at')
        return Response(RelatoListSerializer(relatos, many=True).data)

    def post(self, request):
        creator = self.get_creator(request)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = RelatoDetailSerializer(
            data=request.data,
            context={'creator': creator},
        )
        serializer.is_valid(raise_exception=True)
        relato = serializer.save(creator=creator)
        if relato.status == 'published' and not relato.published_at:
            from django.utils import timezone
            relato.published_at = timezone.now()
            relato.save(update_fields=['published_at'])
        return Response(RelatoDetailSerializer(relato).data, status=status.HTTP_201_CREATED)


class RelatoMeDetailView(APIView):
    """
    Creator: get, update, delete one of my relatos.
    GET/PATCH/DELETE /api/v1/creators/me/relatos/<uuid:id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_creator(self, request):
        if not request.user.is_authenticated:
            return None
        try:
            return CreatorProfile.objects.get(user=request.user)
        except CreatorProfile.DoesNotExist:
            return None

    def get_relato(self, request, relato_id):
        creator = self.get_creator(request)
        if not creator:
            return None, None
        try:
            relato = Relato.objects.get(id=relato_id, creator=creator)
            return creator, relato
        except Relato.DoesNotExist:
            return creator, None

    def get(self, request, id):
        creator, relato = self.get_relato(request, id)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        if not relato:
            return Response(
                {'error': 'Relato not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(RelatoDetailSerializer(relato).data)

    def patch(self, request, id):
        creator, relato = self.get_relato(request, id)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        if not relato:
            return Response(
                {'error': 'Relato not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = RelatoDetailSerializer(
            relato,
            data=request.data,
            partial=True,
            context={'creator': creator},
        )
        serializer.is_valid(raise_exception=True)
        relato = serializer.save()
        if relato.status == 'published' and not relato.published_at:
            from django.utils import timezone
            relato.published_at = timezone.now()
            relato.save(update_fields=['published_at'])
        return Response(RelatoDetailSerializer(relato).data)

    def delete(self, request, id):
        creator, relato = self.get_relato(request, id)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        if not relato:
            return Response(
                {'error': 'Relato not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        relato.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicRelatoView(APIView):
    """
    Public: get a published relato by creator slug and relato slug.
    GET /api/v1/creators/public/<creator_slug>/relatos/<relato_slug>/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, creator_slug, relato_slug):
        try:
            creator = CreatorProfile.objects.get(slug=creator_slug, is_approved=True)
        except CreatorProfile.DoesNotExist:
            return Response(
                {'error': 'Creator or relato not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        try:
            relato = Relato.objects.get(creator=creator, slug=relato_slug, status='published')
        except Relato.DoesNotExist:
            return Response(
                {'error': 'Creator or relato not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(RelatoPublicSerializer(relato).data)


# ---------- Marketplace, Performance, Earnings ----------

def _get_creator(request):
    if not request.user.is_authenticated:
        return None
    try:
        return CreatorProfile.objects.get(user=request.user)
    except CreatorProfile.DoesNotExist:
        return None


class CreatorMarketplaceView(APIView):
    """
    Creator: list experiences available for recommendation (marketplace with commission preview).
    GET /api/v1/creators/me/marketplace/
    Returns experiences with price and estimated creator commission rate/amount.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        creator = _get_creator(request)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        experiences = Experience.objects.filter(
            status='published',
            is_active=True,
            deleted_at__isnull=True,
        ).order_by('-created_at')[:100]
        from .serializers import ExperienceMinimalSerializer
        data = []
        for exp in experiences:
            item = ExperienceMinimalSerializer(exp).data
            rate = exp.creator_commission_rate if exp.creator_commission_rate is not None else Decimal('0.15')
            price = exp.price or Decimal('0')
            item['estimated_commission_rate'] = float(rate)
            item['estimated_commission'] = float(price * rate)
            data.append(item)
        return Response(data)


class CreatorPerformanceView(APIView):
    """
    Creator: KPIs from attributed reservations.
    GET /api/v1/creators/me/performance/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        creator = _get_creator(request)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        reservations = ExperienceReservation.objects.filter(creator=creator)
        paid = reservations.filter(status='paid')
        total_earnings = paid.aggregate(s=Sum('creator_commission_amount'))['s'] or Decimal('0')
        bookings_count = paid.count()
        pending = reservations.filter(
            creator_commission_status__in=('pending', 'earned'),
            status='paid',
        ).aggregate(s=Sum('creator_commission_amount'))['s'] or Decimal('0')
        return Response({
            'total_earnings': float(total_earnings),
            'bookings_count': bookings_count,
            'pending_withdrawal': float(pending),
            'currency': 'CLP',
        })


class CreatorEarningsView(APIView):
    """
    Creator: list earnings (attributed reservations with commission).
    GET /api/v1/creators/me/earnings/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        creator = _get_creator(request)
        if not creator:
            return Response(
                {'error': 'No creator profile for this user.'},
                status=status.HTTP_404_NOT_FOUND
            )
        reservations = (
            ExperienceReservation.objects.filter(creator=creator, status='paid')
            .select_related('experience')
            .order_by('-created_at')[:50]
        )
        items = []
        for r in reservations:
            items.append({
                'reservation_id': r.reservation_id,
                'experience_title': r.experience.title if r.experience_id else None,
                'amount': float(r.creator_commission_amount or 0),
                'status': r.creator_commission_status or 'pending',
                'created_at': r.created_at.isoformat() if r.created_at else None,
            })
        return Response({'results': items})
