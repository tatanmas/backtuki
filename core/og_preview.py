"""
Open Graph (and Twitter Card) meta tags for shareable frontend routes.

When nginx proxies requests for /erasmus/actividades/entry/<id>, /alojamientos/<id>,
/events/<id>, /experiences/<id> to Django, this view returns the SPA index.html with
dynamic og:title, og:description, og:image (and twitter:*) so WhatsApp/Facebook show
rich link previews. Crawlers do not execute JavaScript, so meta must be server-rendered.
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


def get_og_data_for_path(request):
    """
    Resolve request.path to OG data dict: title, description, image (absolute URL).
    Returns None if path does not match or resource not found.
    """
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
    return None


def inject_meta_into_html(html, meta, canonical_url, default_image_absolute=""):
    """
    Inject or replace Open Graph and Twitter Card meta tags in HTML string.
    meta: dict with title, description, image (optional).
    """
    title = (meta.get("title") or DEFAULT_OG_TITLE).replace("<", "&lt;").replace(">", "&gt;")
    description = (meta.get("description") or DEFAULT_OG_DESCRIPTION).replace("<", "&lt;").replace(">", "&gt;")
    image = meta.get("image") or default_image_absolute or ""

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
    /alojamientos/*, /events/*, /experiences/* to this view.
    """

    def get(self, request, *args, **kwargs):
        path = (request.path or "").strip()
        canonical_url = request.build_absolute_uri(path)
        default_image_absolute = request.build_absolute_uri(DEFAULT_OG_IMAGE_RELATIVE)

        meta = get_og_data_for_path(request)
        if not meta:
            # Fallback to default meta so the page still loads (SPA will show 404 if needed)
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

        html = inject_meta_into_html(html, meta, canonical_url, default_image_absolute)
        return HttpResponse(html, content_type="text/html; charset=utf-8")
