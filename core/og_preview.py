"""
Open Graph (and Twitter Card) meta tags for shareable frontend routes.

When nginx proxies requests for /erasmus/actividades/entry/<id>, /alojamientos/<id>,
/events/<id>, /experiences/<id>, /guias/<slug> to Django, this view returns the SPA
index.html with dynamic og:title, og:description, og:image (and twitter:*) so
WhatsApp/Facebook show rich link previews. Crawlers do not execute JavaScript, so
meta must be server-rendered.
"""

import re
import uuid as uuid_mod
import logging
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, Http404
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

# Default meta when resource not found or for fallback
DEFAULT_OG_TITLE = "Tuki"
DEFAULT_OG_DESCRIPTION = "Tuki Tickets - Eventos, experiencias y reservas!"
DEFAULT_OG_IMAGE_RELATIVE = "/og-image.png"

# Path patterns: (pattern, type_key)
OG_PATH_PATTERNS = [
    (re.compile(r"^/erasmus/actividades/entry/([^/]+)/?$"), "erasmus_entry"),
    (re.compile(r"^/alojamientos/([^/]+)/?$"), "accommodation"),
    (re.compile(r"^/events/([^/]+)/?$"), "event"),
    (re.compile(r"^/experiences/([^/]+)/?$"), "experience"),
    (re.compile(r"^/guias/([^/]+)/?$"), "travel_guide"),
]


def _parse_path(path):
    """Return (type_key, identifier) or (None, None)."""
    for pattern, type_key in OG_PATH_PATTERNS:
        m = pattern.match(path)
        if m:
            return type_key, m.group(1).strip("/") or m.group(1)
    return None, None


def _absolute_uri(request, path_or_url):
    """Return absolute URL for a path or keep URL if already absolute."""
    if not path_or_url:
        return ""
    s = path_or_url.strip()
    if s.startswith(("http://", "https://")):
        return s
    if not s.startswith("/"):
        s = "/" + s
    return request.build_absolute_uri(s)


def _get_og_data_erasmus_entry(request, entry_id):
    """Fetch OG data for Erasmus timeline entry (activity instance)."""
    from api.v1.erasmus.views import _get_timeline_entry_payload

    try:
        payload = _get_timeline_entry_payload(entry_id)
    except Exception:
        return None
    if not payload:
        return None
    title_obj = payload.get("title") or {}
    title = title_obj.get("es") or title_obj.get("en") or "Actividad"
    desc_obj = payload.get("short_description") or payload.get("description") or {}
    desc = desc_obj.get("es") or desc_obj.get("en") or ""
    if len(desc) > 160:
        desc = desc[:157] + "..."
    image = payload.get("image") or ""
    image_url = _absolute_uri(request, image) if image else ""
    return {"title": title, "description": desc or title, "image": image_url}


def _get_og_data_accommodation(request, slug_or_id):
    """Fetch OG data for accommodation by id or slug. Draft (unlisted) allowed for link sharing."""
    from apps.accommodations.models import Accommodation
    from apps.accommodations.serializers import _resolve_images

    qs = Accommodation.objects.filter(
        status__in=("published", "draft"),
        deleted_at__isnull=True,
    )
    acc = None
    try:
        acc = qs.get(slug=slug_or_id)
    except Accommodation.DoesNotExist:
        try:
            uid = uuid_mod.UUID(str(slug_or_id))
            acc = qs.get(id=uid)
        except (ValueError, TypeError, Accommodation.DoesNotExist):
            pass
    if not acc:
        return None
    images = _resolve_images(acc, request)
    image_url = (images[0] if images else "") or ""
    if image_url and not image_url.startswith(("http://", "https://")):
        image_url = request.build_absolute_uri(image_url)
    title = acc.title or "Alojamiento"
    desc = (acc.short_description or (acc.description or "")[:160] or title).strip()
    if len(desc) > 160:
        desc = desc[:157] + "..."
    return {"title": title, "description": desc, "image": image_url}


def _get_og_data_event(request, event_id):
    """Fetch OG data for public event by id."""
    from apps.events.models import Event

    try:
        event = Event.objects.filter(
            status="published",
            visibility="public",
            requires_email_validation=False,
            deleted_at__isnull=True,
        ).get(id=event_id)
    except (Event.DoesNotExist, ValueError, TypeError):
        return None
    title = event.title or "Evento"
    desc = (event.short_description or (event.description or "")[:160] or title).strip()
    if len(desc) > 160:
        desc = desc[:157] + "..."
    image_url = ""
    first_image = event.images.first()
    if first_image and getattr(first_image, "image", None):
        image_url = request.build_absolute_uri(first_image.image.url)
    return {"title": title, "description": desc, "image": image_url}


def _first_image_url_from_experience(experience, request):
    """Get first image URL from Experience.images (list of URLs or dicts)."""
    images = getattr(experience, "images", None) or []
    if not images:
        return ""
    first = images[0]
    if isinstance(first, str):
        url = first
    elif isinstance(first, dict):
        url = first.get("url") or first.get("image") or first.get("src") or ""
    else:
        return ""
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    return request.build_absolute_uri(url if url.startswith("/") else "/" + url)


def _get_og_data_experience(request, slug_or_id):
    """Fetch OG data for experience by id or slug."""
    from apps.experiences.models import Experience

    base_filters = {"deleted_at__isnull": True, "status": "published", "is_active": True}
    exp = None
    try:
        exp = Experience.objects.filter(**base_filters).get(slug=slug_or_id)
    except Experience.DoesNotExist:
        try:
            uuid_mod.UUID(str(slug_or_id))
            exp = Experience.objects.filter(**base_filters).get(id=slug_or_id)
        except (ValueError, TypeError, Experience.DoesNotExist):
            pass
    if not exp:
        return None
    title = exp.title or "Experiencia"
    desc = (exp.short_description or (exp.description or "")[:160] or title).strip()
    if len(desc) > 160:
        desc = desc[:157] + "..."
    image_url = _first_image_url_from_experience(exp, request)
    return {"title": title, "description": desc, "image": image_url}


def _get_og_data_travel_guide(request, slug):
    """Fetch OG data for published travel guide by slug (or draft when preview_token matches). Image: og_image, else first hero slide, else hero."""
    from apps.travel_guides.models import TravelGuide
    from apps.travel_guides.serializers import _resolve_hero_url, _resolve_hero_slides

    try:
        preview_token = (request.GET.get("preview_token") or "").strip()
        qs = TravelGuide.objects.filter(
            slug=slug,
            deleted_at__isnull=True,
        )
        guide = qs.first()
        if not guide:
            return None
        if guide.status != "published":
            if not (preview_token and getattr(guide, "preview_token", None) and guide.preview_token == preview_token):
                return None
        # Safe string coercion (model can have null/empty in edge cases)
        raw_title = getattr(guide, "meta_title", None) or getattr(guide, "title", None) or "Guía de viaje"
        title = (raw_title if isinstance(raw_title, str) else str(raw_title or "")).strip() or "Guía de viaje"
        raw_desc = getattr(guide, "meta_description", None) or getattr(guide, "excerpt", None) or ""
        desc = (raw_desc if isinstance(raw_desc, str) else str(raw_desc or "")).strip()
        if len(desc) > 160:
            desc = desc[:157] + "..."
        if not desc:
            desc = title
        image_url = ""
        og_image = getattr(guide, "og_image", None)
        if og_image and isinstance(og_image, str) and og_image.strip():
            image_url = og_image.strip()
            if not image_url.startswith(("http://", "https://")):
                image_url = _absolute_uri(request, image_url)
        if not image_url:
            try:
                slides = _resolve_hero_slides(guide, request)
                if slides and isinstance(slides, list):
                    first = slides[0]
                    if isinstance(first, dict):
                        image_url = (first.get("image") or "").strip()
            except Exception as e:
                logger.warning("OG travel_guide: _resolve_hero_slides failed for slug=%s: %s", slug, e)
            if not image_url:
                try:
                    image_url = (_resolve_hero_url(guide, request) or "").strip()
                except Exception as e:
                    logger.warning("OG travel_guide: _resolve_hero_url failed for slug=%s: %s", slug, e)
        if image_url and not image_url.startswith(("http://", "https://")):
            try:
                image_url = request.build_absolute_uri(image_url)
            except Exception:
                image_url = ""
        return {"title": title, "description": desc, "image": image_url}
    except Exception as e:
        logger.exception("OG travel_guide: failed for slug=%s: %s", slug, e)
        return None


def get_og_data_for_path(request):
    """
    Resolve request.path to OG data dict: title, description, image (absolute URL).
    Returns None if path does not match, resource not found, or any error (never raises).
    """
    try:
        path = (request.path or "").strip()
        type_key, identifier = _parse_path(path)
        if not type_key or not identifier:
            return None
        if type_key == "erasmus_entry":
            return _get_og_data_erasmus_entry(request, identifier)
        if type_key == "accommodation":
            return _get_og_data_accommodation(request, identifier)
        if type_key == "event":
            return _get_og_data_event(request, identifier)
        if type_key == "experience":
            return _get_og_data_experience(request, identifier)
        if type_key == "travel_guide":
            return _get_og_data_travel_guide(request, identifier)
        return None
    except Exception as e:
        logger.exception("OG get_og_data_for_path failed: path=%s %s", getattr(request, "path", ""), e)
        return None


def _safe_meta_str(s, default=""):
    """Escape for HTML attribute content: strip and escape <, >, quotes."""
    if s is None:
        s = default
    s = (s if isinstance(s, str) else str(s))[:500]
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").strip() or default


def inject_meta_into_html(html, meta, canonical_url, default_image_absolute=""):
    """
    Inject or replace Open Graph and Twitter Card meta tags in HTML string.
    meta: dict with title, description, image (optional). Never raises.
    """
    meta = meta or {}
    title = _safe_meta_str(meta.get("title"), DEFAULT_OG_TITLE)
    description = _safe_meta_str(meta.get("description"), DEFAULT_OG_DESCRIPTION)
    image = (meta.get("image") or default_image_absolute or "")
    if image and not isinstance(image, str):
        image = str(image)[:2000]

    # Replace <title>...</title>
    html = re.sub(r"<title>[^<]*</title>", f"<title>{title}</title>", html, count=1)
    # Replace meta name="description"
    html = re.sub(
        r'<meta\s+name="description"\s+content="[^"]*"\s*/?>',
        f'<meta name="description" content="{description}" />',
        html,
        count=1,
    )
    # Replace og:image
    html = re.sub(
        r'<meta\s+property="og:image"\s+content="[^"]*"\s*/?>',
        f'<meta property="og:image" content="{image}" />' if image else f'<meta property="og:image" content="{default_image_absolute}" />',
        html,
        count=1,
    )

    # Collect tags to add if not present (one block before </head>)
    to_add = []
    for attr, content in [
        ("og:title", title),
        ("og:description", description),
        ("og:url", canonical_url),
        ("og:type", "website"),
        ("og:site_name", "Tuki"),
    ]:
        pattern = re.compile(
            r'<meta\s+property="' + re.escape(attr) + r'"\s+content="[^"]*"\s*/?>',
            re.IGNORECASE,
        )
        new_tag = f'<meta property="{attr}" content="{content}" />'
        if pattern.search(html):
            html = pattern.sub(new_tag, html, count=1)
        else:
            to_add.append(new_tag)

    for name, content in [
        ("twitter:card", "summary_large_image"),
        ("twitter:title", title),
        ("twitter:description", description),
        ("twitter:image", image),
    ]:
        if name == "twitter:image" and not image:
            continue
        pattern = re.compile(
            r'<meta\s+name="' + re.escape(name) + r'"\s+content="[^"]*"\s*/?>',
            re.IGNORECASE,
        )
        new_tag = f'<meta name="{name}" content="{content}" />'
        if pattern.search(html):
            html = pattern.sub(new_tag, html, count=1)
        else:
            to_add.append(new_tag)

    if to_add:
        block = "\n    ".join(to_add) + "\n  "
        html = html.replace("</head>", block + "</head>", 1)

    return html


def get_frontend_index_html():
    """Read frontend index.html from configured path. Return None if not found."""
    path = getattr(settings, "FRONTEND_INDEX_PATH", None)
    if not path:
        path = Path(settings.BASE_DIR) / "static" / "frontend_index.html"
    path = Path(path)
    if not path.is_file():
        logger.warning("OG preview: FRONTEND_INDEX_PATH file not found: %s", path)
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.exception("OG preview: failed to read index: %s", e)
        return None


@method_decorator(require_GET, name="get")
class OGPreviewView(View):
    """
    Serves the SPA index.html with injected Open Graph (and Twitter) meta tags
    for shareable routes. Nginx should proxy /erasmus/actividades/entry/*,
    /alojamientos/*, /events/*, /experiences/*, /guias/* to this view.
    """

    def get(self, request, *args, **kwargs):
        path = (request.path or "").strip()
        try:
            canonical_url = request.build_absolute_uri(path)
            default_image_absolute = request.build_absolute_uri(DEFAULT_OG_IMAGE_RELATIVE)
        except Exception as e:
            logger.warning("OG preview: build_absolute_uri failed: %s", e)
            canonical_url = ""
            default_image_absolute = ""

        meta = get_og_data_for_path(request)
        if not meta:
            meta = {
                "title": DEFAULT_OG_TITLE,
                "description": DEFAULT_OG_DESCRIPTION,
                "image": default_image_absolute,
            }

        html = get_frontend_index_html()
        if not html:
            raise Http404(
                "OG preview: frontend index not found. Set FRONTEND_INDEX_PATH to the SPA index.html path."
            )

        try:
            html = inject_meta_into_html(html, meta, canonical_url, default_image_absolute)
        except Exception as e:
            logger.exception("OG preview: inject_meta_into_html failed, serving index without injection: %s", e)

        return HttpResponse(html, content_type="text/html; charset=utf-8")
