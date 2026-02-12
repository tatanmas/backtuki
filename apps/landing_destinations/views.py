"""Views for landing destinations: superadmin CRUD and public API."""

import logging
import re
import requests
from rest_framework import viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.conf import settings

from .models import LandingDestination
from .serializers import LandingDestinationSerializer, LandingDestinationListSerializer

logger = logging.getLogger(__name__)


def _absolute_media_url(relative_path, request=None):
    """Build absolute URL for a relative media path (request host or BACKEND_URL)."""
    if not relative_path:
        return ""
    if relative_path.startswith(("http://", "https://")):
        return relative_path
    if request:
        return request.build_absolute_uri(relative_path)
    base = getattr(settings, "BACKEND_URL", None) or "http://localhost:8000"
    path = relative_path.lstrip("/")
    return f"{base.rstrip('/')}/{path}" if path else base


def _normalize_media_url(url):
    """Rewrite any localhost media URL to BACKEND_URL (fixes stored DB values from dev)."""
    if not url or not isinstance(url, str):
        return url or ""
    if "localhost" not in url and "127.0.0.1" not in url:
        return url
    base = getattr(settings, "BACKEND_URL", None)
    if not base:
        return url
    base = base.rstrip("/")
    # Keep path: e.g. http://localhost:8000/media/global/... -> base + /media/global/...
    for prefix in ("http://localhost:8000/", "http://localhost/", "https://localhost:8000/", "https://localhost/"):
        if url.startswith(prefix):
            path = url[len(prefix):].lstrip("/")
            return f"{base}/{path}" if path else base
    if "127.0.0.1" in url:
        path_match = re.search(r"https?://127\.0\.0\.1(?::\d+)?(/.+)?", url)
        if path_match:
            path = (path_match.group(1) or "").lstrip("/")
            return f"{base}/{path}" if path else base
    return url


def _resolve_media_urls(hero_media_id, gallery_media_ids):
    """Resolve media asset IDs to URLs. Returns (hero_url, list_of_gallery_urls)."""
    from apps.media.models import MediaAsset
    hero_url = None
    gallery_urls = []
    ids_to_resolve = []
    if hero_media_id:
        ids_to_resolve.append(hero_media_id)
    if gallery_media_ids:
        ids_to_resolve.extend(gallery_media_ids)
    if not ids_to_resolve:
        return None, []
    assets = MediaAsset.objects.filter(id__in=ids_to_resolve, deleted_at__isnull=True)
    url_by_id = {str(a.id): a.url for a in assets if a.url}
    if hero_media_id:
        hero_url = url_by_id.get(str(hero_media_id))
    for eid in gallery_media_ids or []:
        u = url_by_id.get(str(eid))
        if u:
            gallery_urls.append(u)
    return hero_url, gallery_urls


class LandingDestinationViewSet(viewsets.ModelViewSet):
    """Superadmin CRUD for landing destinations. Superuser only."""

    queryset = LandingDestination.objects.all()
    serializer_class = LandingDestinationSerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = "id"
    lookup_url_kwarg = "id"

    def get_serializer_class(self):
        if self.action == "list":
            return LandingDestinationListSerializer
        return LandingDestinationSerializer


def _experience_to_card(exp):
    """Map Experience to frontend card shape (id, title, image, price, rating, reviews, location, duration)."""
    images = getattr(exp, "images", None) or []
    image = images[0] if images else ""
    return {
        "id": str(exp.id),
        "title": exp.title,
        "slug": exp.slug,
        "image": image,
        "price": float(exp.price) if exp.price is not None else 0,
        "rating": 0,
        "reviews": 0,
        "location": {"name": exp.location_name or "", "address": exp.location_address or ""},
        "duration": f"{exp.duration_minutes} min" if exp.duration_minutes else None,
        "countryName": exp.country.name if exp.country else None,
    }


def _event_to_card(ev, request=None):
    """Map Event to frontend card shape for featured block."""
    image = ""
    if hasattr(ev, "images") and ev.images.exists():
        first = ev.images.first()
        if first and getattr(first, "image", None):
            image = _absolute_media_url(first.image.url, request=request)
    return {
        "id": str(ev.id),
        "title": ev.title,
        "slug": ev.slug,
        "image": image,
        "price": 0,
        "rating": 0,
        "reviews": 0,
        "location": {"name": getattr(ev, "location_name", "") or "", "address": ""},
        "duration": None,
        "countryName": None,
    }


def _build_featured(dest, request=None):
    """Build featured payload { type, id, ...card } from destination featured_type/featured_id."""
    if not dest.featured_type or not dest.featured_id:
        return None
    try:
        uid = dest.featured_id
        if dest.featured_type == "experience":
            from apps.experiences.models import Experience
            exp = Experience.objects.filter(
                id=uid, status="published", is_active=True, deleted_at__isnull=True
            ).first()
            if exp:
                card = _experience_to_card(exp)
                return {"type": "experience", "id": str(uid), **card}
        elif dest.featured_type == "event":
            from apps.events.models import Event
            ev = Event.objects.filter(id=uid, status="published", visibility="public").first()
            if ev:
                card = _event_to_card(ev, request=request)
                return {"type": "event", "id": str(uid), **card}
        elif dest.featured_type == "accommodation":
            # No Accommodation model yet; return minimal placeholder or None
            return None
    except Exception as e:
        logger.warning("Failed to build featured for destination %s: %s", dest.slug, e)
    return None


class PublicDestinationBySlugView(APIView):
    """Public API: GET destination by slug. Only includes sections that have content."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        dest = get_object_or_404(LandingDestination, slug=slug, is_active=True)

        hero_media_url, gallery_media_urls = _resolve_media_urls(
            dest.hero_media_id, dest.gallery_media_ids
        )
        hero_image = _normalize_media_url(hero_media_url or dest.hero_image or "")
        raw_images = gallery_media_urls if gallery_media_urls else (dest.images or [])
        images = [_normalize_media_url(u) for u in raw_images] if raw_images else []

        from apps.experiences.models import Experience
        exp_ids = [str(e.experience_id) for e in dest.destination_experiences.order_by("order")]
        experiences = []
        if exp_ids:
            qs = Experience.objects.filter(
                id__in=exp_ids,
                status="published",
                is_active=True,
                deleted_at__isnull=True,
            )
            exp_map = {str(e.id): e for e in qs}
            for eid in exp_ids:
                if eid in exp_map:
                    experiences.append(_experience_to_card(exp_map[eid]))

        event_ids = [str(e.event_id) for e in dest.destination_events.order_by("order")]
        events = []
        if event_ids:
            from apps.events.models import Event
            qs = Event.objects.filter(
                id__in=event_ids,
                status="published",
                visibility="public",
            )
            ev_map = {str(e.id): e for e in qs}
            for eid in event_ids:
                if eid in ev_map:
                    events.append(_event_to_card(ev_map[eid], request=request))

        accommodations = []

        featured = _build_featured(dest, request=request)

        travel_guides = dest.travel_guides or []
        transportation = dest.transportation or []

        payload = {
            "slug": dest.slug,
            "name": dest.name,
            "country": dest.country,
            "region": dest.region or "",
            "description": dest.description,
            "heroImage": hero_image,
            "images": images,
            "temperature": dest.temperature,
            "localTime": dest.local_time or "",
            "latitude": dest.latitude,
            "longitude": dest.longitude,
            "travelGuides": travel_guides,
            "transportation": transportation,
            "accommodations": accommodations,
            "experiences": experiences,
            "events": events,
            "featured": featured,
        }
        return Response(payload)


class PublicDestinationWeatherTimeView(APIView):
    """
    Public API: GET current temperature and local time for a destination by slug.
    Uses latitude/longitude and Open-Meteo (no API key). Destination must have lat/lon set.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        dest = get_object_or_404(LandingDestination, slug=slug, is_active=True)
        if dest.latitude is None or dest.longitude is None:
            return Response(
                {"detail": "Destino sin coordenadas configuradas."},
                status=400,
            )
        try:
            url = (
                "https://api.open-meteo.com/v1/forecast"
                "?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m&timezone=auto"
            ).format(lat=dest.latitude, lon=dest.longitude)
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()
            current = data.get("current", {})
            temp = current.get("temperature_2m")
            tz = data.get("timezone", "")
            from datetime import datetime
            try:
                from zoneinfo import ZoneInfo
                now = datetime.now(ZoneInfo(tz)) if tz else datetime.utcnow()
                local_time = now.strftime("%H:%M")
            except Exception:
                local_time = ""
            return Response({
                "temperature": temp,
                "local_time": local_time,
                "timezone": tz,
            })
        except requests.RequestException as e:
            logger.warning("Weather API error for %s: %s", slug, e)
            return Response(
                {"detail": "No se pudo obtener clima u hora para este destino."},
                status=502,
            )
