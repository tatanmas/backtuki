"""Public API views for travel guides: list and detail by slug."""
from rest_framework import permissions
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import TravelGuide
from .serializers import PublicTravelGuideListSerializer, PublicTravelGuideDetailSerializer
from .booking import get_block_by_key, build_public_booking_offer


class PublicTravelGuideListView(ListAPIView):
    """
    GET /api/v1/public/travel-guides/
    Returns published guides. Query params: destination_slug, template.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicTravelGuideListSerializer

    def get_queryset(self):
        qs = TravelGuide.objects.filter(status='published').select_related('destination')
        destination_slug = self.request.query_params.get('destination_slug')
        if destination_slug:
            qs = qs.filter(destination__slug=destination_slug)
        template = self.request.query_params.get('template')
        if template:
            qs = qs.filter(template=template)
        return qs.order_by('display_order', '-published_at')


class PublicTravelGuideBySlugView(RetrieveAPIView):
    """
    GET /api/v1/public/travel-guides/<slug>/
    Returns a single guide by slug (published, or draft if ?preview_token= matches).
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicTravelGuideDetailSerializer
    lookup_url_kwarg = 'slug'
    lookup_field = 'slug'

    def get_object(self):
        slug = self.kwargs.get(self.lookup_url_kwarg)
        preview_token = self.request.query_params.get('preview_token', '').strip()
        qs = TravelGuide.objects.filter(slug=slug).select_related('destination')
        guide = qs.first()
        if not guide:
            from rest_framework.exceptions import NotFound
            raise NotFound()
        if guide.status == 'published':
            return guide
        if preview_token and guide.preview_token and guide.preview_token == preview_token:
            return guide
        from rest_framework.exceptions import NotFound
        raise NotFound()

    def get_queryset(self):
        return TravelGuide.objects.all().select_related('destination')

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class PublicTravelGuideExperienceBookingView(APIView):
    """
    GET /api/v1/public/travel-guides/<slug>/experience-booking/<block_key>/
    Return resolved booking context for one embedded experience block inside a guide.
    """

    permission_classes = [permissions.AllowAny]

    def get_guide(self, request, slug):
        preview_token = request.query_params.get('preview_token', '').strip()
        guide = TravelGuide.objects.filter(slug=slug).first()
        if not guide:
            return None
        if guide.status == 'published':
            return guide
        if preview_token and guide.preview_token and guide.preview_token == preview_token:
            return guide
        return None

    def get(self, request, slug, block_key):
        guide = self.get_guide(request, slug)
        if not guide:
            from rest_framework.exceptions import NotFound
            raise NotFound()
        block = get_block_by_key(guide, block_key)
        if not block:
            from rest_framework.exceptions import NotFound
            raise NotFound()
        payload = build_public_booking_offer(guide, block)
        if not payload:
            from rest_framework.exceptions import NotFound
            raise NotFound()
        return Response(payload)
