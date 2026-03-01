"""Views for landing destinations: superadmin CRUD and public API."""

import logging
import re
from urllib.parse import urlparse

import requests
from rest_framework import viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.conf import settings

from .models import LandingDestination
from .serializers import LandingDestinationSerializer, LandingDestinationListSerializer

logger = logging.getLogger(__name__)


def _rewrite_media_url_to_request_host(url, request):
    """Rewrite a media URL to use the request's scheme and host (so images load from same domain as the page)."""
    if not url or not request:
        return url or ""
    parsed = urlparse(url)
    path = parsed.path or ""
    if not path:
        return url
    return request.build_absolute_uri(path)


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


def _build_destination_media_urls_from_request(dest, request):
    """
    Build hero and gallery URLs using the request host (robust: same as San Pedro).
    Does not depend on BACKEND_URL or MediaAsset.url; uses asset.file.url + request.build_absolute_uri.
    Returns (hero_image, images_list).
    """
    from apps.media.models import MediaAsset
    hero_image = ""
    images = []
    if not request:
        return hero_image, images
    # Hero: one asset by hero_media_id
    if dest.hero_media_id:
        a = MediaAsset.objects.filter(id=dest.hero_media_id, deleted_at__isnull=True).first()
        if a and a.file:
            hero_image = request.build_absolute_uri(a.file.url)
    # Fallback to legacy hero_image URL if no media asset
    if not hero_image and getattr(dest, "hero_image", None):
        raw = dest.hero_image.strip()
        if raw:
            hero_image = _normalize_media_url(raw)
            hero_image = _rewrite_media_url_to_request_host(hero_image, request) if hero_image else ""
    # Gallery: preserve order from gallery_media_ids
    if dest.gallery_media_ids:
        assets_map = {
            str(a.id): a
            for a in MediaAsset.objects.filter(
                id__in=dest.gallery_media_ids, deleted_at__isnull=True
            )
            if a.file
        }
        for eid in dest.gallery_media_ids:
            a = assets_map.get(str(eid))
            if a:
                images.append(request.build_absolute_uri(a.file.url))
    if not images and getattr(dest, "images", None):
        for raw in dest.images or []:
            if raw:
                u = _normalize_media_url(raw)
                if u:
                    images.append(_rewrite_media_url_to_request_host(u, request))
    return hero_image, images


class LandingDestinationViewSet(viewsets.ModelViewSet):
    """Superadmin CRUD for landing destinations. Superuser only.
    List returns all destinations (no pagination) so admin can see and manage the full list."""

    queryset = LandingDestination.objects.all()
    serializer_class = LandingDestinationSerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = "id"
    lookup_url_kwarg = "id"
    pagination_class = None  # Return all destinations in list (superadmin needs full list)

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


def _car_to_card(car, request=None):
    """Map Car (car_rental) to frontend card shape for destination section / featured."""
    image = ""
    if getattr(car, "gallery_media_ids", None):
        from apps.media.models import MediaAsset
        first_id = car.gallery_media_ids[0] if car.gallery_media_ids else None
        if first_id:
            asset = MediaAsset.objects.filter(id=first_id, deleted_at__isnull=True).first()
            if asset and getattr(asset, "file", None) and asset.file:
                url = asset.file.url
                image = request.build_absolute_uri(url) if request and url.startswith("/") else _normalize_media_url(url)
    if not image and getattr(car, "images", None) and len(car.images) > 0:
        raw = car.images[0]
        image = _normalize_media_url(raw if isinstance(raw, str) else raw.get("url", ""))
    company_name = car.company.name if car.company else ""
    return {
        "id": str(car.id),
        "title": car.title,
        "slug": car.slug,
        "image": image,
        "price": float(car.price_per_day) if car.price_per_day is not None else 0,
        "price_per_day": float(car.price_per_day) if car.price_per_day is not None else 0,
        "company_name": company_name,
        "location": {"name": company_name, "address": ""},
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
            from apps.accommodations.models import Accommodation
            from apps.accommodations.serializers import _accommodation_to_public_dict
            acc = Accommodation.objects.filter(
                id=uid, status="published", deleted_at__isnull=True
            ).first()
            if acc:
                d = _accommodation_to_public_dict(acc, request=request)
                imgs = d.get("images") or []
                return {
                    "type": "accommodation",
                    "id": str(uid),
                    "title": d["title"],
                    "image": imgs[0] if imgs else "",
                    "price": d["price"],
                    "rating": d.get("rating"),
                    "reviews": d.get("reviews"),
                    "location": d.get("location"),
                }
        elif dest.featured_type == "car_rental":
            from apps.car_rental.models import Car
            car = Car.objects.filter(
                id=uid, status="published", deleted_at__isnull=True
            ).select_related("company").first()
            if car:
                card = _car_to_card(car, request=request)
                return {"type": "car_rental", "id": str(uid), **card}
    except Exception as e:
        logger.warning("Failed to build featured for destination %s: %s", dest.slug, e)
    return None


class PublicDestinationBySlugView(APIView):
    """Public API: GET destination by slug. Only includes sections that have content."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        dest = get_object_or_404(LandingDestination, slug=slug, is_active=True)

        # Robust: build media URLs from request + asset.file (same behaviour as San Pedro, no BACKEND_URL dependency)
        if request:
            hero_image, images = _build_destination_media_urls_from_request(dest, request)
        else:
            hero_media_url, gallery_media_urls = _resolve_media_urls(
                dest.hero_media_id, dest.gallery_media_ids
            )
            hero_image = _normalize_media_url(hero_media_url or getattr(dest, "hero_image", "") or "")
            raw_images = gallery_media_urls or (getattr(dest, "images", None) or [])
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
        acc_ids = getattr(dest, "accommodation_ids", None) or []
        if acc_ids:
            try:
                from apps.accommodations.models import Accommodation
                from apps.accommodations.serializers import _accommodation_to_public_dict

                qs = Accommodation.objects.filter(
                    id__in=[str(aid) for aid in acc_ids],
                    status="published",
                    deleted_at__isnull=True,
                )
                acc_map = {str(a.id): a for a in qs}
                for aid in acc_ids:
                    aid_str = str(aid).strip()
                    acc = acc_map.get(aid_str)
                    if acc:
                        d = _accommodation_to_public_dict(acc, request=request)
                        imgs = d.get("images") or []
                        accommodations.append({
                            "id": d["id"],
                            "title": d["title"],
                            "image": imgs[0] if imgs else "",
                            "price": d["price"],
                            "rating": d["rating"],
                            "reviews": d["reviews"],
                            "location": d["location"],
                        })
            except Exception as e:
                logger.warning("Failed to load accommodations for destination %s: %s", dest.slug, e)

        car_rentals = []
        car_ids = getattr(dest, "car_rental_ids", None) or []
        if car_ids:
            try:
                from apps.car_rental.models import Car

                qs = Car.objects.filter(
                    id__in=[str(cid) for cid in car_ids],
                    status="published",
                    deleted_at__isnull=True,
                ).select_related("company")
                car_map = {str(c.id): c for c in qs}
                for cid in car_ids:
                    cid_str = str(cid).strip()
                    car = car_map.get(cid_str)
                    if car:
                        car_rentals.append(_car_to_card(car, request=request))
            except Exception as e:
                logger.warning("Failed to load car rentals for destination %s: %s", dest.slug, e)

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
            "car_rentals": car_rentals,
            "experiences": experiences,
            "events": events,
            "featured": featured,
        }
        return Response(payload)


class PublicDestinationListView(APIView):
    """
    Public API: GET list of all active destinations.
    Returns [{ slug, name, country, region, heroImage }] for the destinations page.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        dests = LandingDestination.objects.filter(is_active=True).order_by("country", "name")
        result = []
        for d in dests:
            hero_image, _ = _build_destination_media_urls_from_request(d, request)
            result.append({
                "slug": d.slug,
                "name": d.name,
                "country": d.country or "",
                "region": d.region or "",
                "heroImage": hero_image,
            })
        return Response(result)


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
