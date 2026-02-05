"""Unified public search: destinations, events, experiences, accommodations."""

from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q

from .models import LandingDestination


class PublicSearchView(APIView):
    """
    GET /api/v1/public/search?q=...&type=destinations|events|experiences|accommodations
    Returns { destinations: [], events: [], experiences: [], accommodations: [] }
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        type_filter = request.query_params.get("type", "").strip().lower()

        result = {"destinations": [], "events": [], "experiences": [], "accommodations": []}

        if not q:
            return Response(result)

        # Destinations
        if type_filter in ("", "destinations"):
            dests = LandingDestination.objects.filter(
                is_active=True
            ).filter(
                Q(name__icontains=q) | Q(slug__icontains=q) | Q(region__icontains=q) | Q(country__icontains=q)
            )[:10]
            result["destinations"] = [
                {"id": str(d.id), "name": d.name, "slug": d.slug, "image": d.hero_image, "region": d.region}
                for d in dests
            ]

        # Events
        if type_filter in ("", "events"):
            try:
                from apps.events.models import Event
                events = Event.objects.filter(
                    status="published",
                    visibility="public",
                ).filter(
                    Q(title__icontains=q) | Q(description__icontains=q) | Q(short_description__icontains=q)
                )[:10]
                event_list = []
                for ev in events:
                    img = ""
                    if hasattr(ev, "images") and ev.images.exists():
                        first = ev.images.first()
                        if first and getattr(first, "image", None):
                            img = first.image.url
                    event_list.append({
                        "id": str(ev.id),
                        "title": ev.title,
                        "slug": ev.slug,
                        "image": img,
                        "description": (ev.short_description or ev.description or "")[:200],
                    })
                result["events"] = event_list
            except Exception:
                pass

        # Experiences
        if type_filter in ("", "experiences"):
            try:
                from apps.experiences.models import Experience
                exps = Experience.objects.filter(
                    status="published",
                    is_active=True,
                    deleted_at__isnull=True,
                ).filter(
                    Q(title__icontains=q) | Q(description__icontains=q) | Q(short_description__icontains=q)
                )[:10]
                exp_list = []
                for ex in exps:
                    images = getattr(ex, "images", None) or []
                    img = images[0] if images else ""
                    exp_list.append({
                        "id": str(ex.id),
                        "title": ex.title,
                        "slug": ex.slug,
                        "image": img,
                        "price": float(ex.price) if ex.price is not None else 0,
                        "description": (ex.short_description or ex.description or "")[:200],
                    })
                result["experiences"] = exp_list
            except Exception:
                pass

        # Accommodations (no model yet)
        if type_filter == "accommodations":
            result["accommodations"] = []

        return Response(result)
