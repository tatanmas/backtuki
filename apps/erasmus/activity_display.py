"""
Erasmus activity display: effective content when activity is linked to an Experience.

When ErasmusActivity.experience is set, we source title, description, images, etc.
from the Experience so the same content is shown in timeline and activity list/detail
without duplication. Activity-only fields (slug, display_order, detail_layout, instances)
always come from ErasmusActivity.
"""

from typing import Optional

from .models import ErasmusActivity


def _first_image_url(images: list) -> str:
    """Extract first URL from images list (URL string or dict with url/image/src)."""
    if not images:
        return ""
    first = images[0]
    if isinstance(first, str):
        return first
    if isinstance(first, dict):
        return first.get("url") or first.get("image") or first.get("src") or ""
    return ""


def get_activity_display_data(act: ErasmusActivity) -> dict:
    """
    Return effective display data for an ErasmusActivity for public API.

    When act.experience is set (and loaded, e.g. select_related("experience")),
    content is sourced from the Experience. Otherwise uses activity's own fields.
    Activity slug, id, display_order, detail_layout are always from the activity.

    Returns dict with keys suitable for public payloads:
      title_es, title_en, description_es, description_en,
      short_description_es, short_description_en,
      location, location_name, location_address,
      duration_minutes, included, not_included, itinerary, images, image.
    """
    exp = getattr(act, "experience", None)
    if exp is not None:
        # Source from Experience (single-language: Experience has only title, no title_en)
        title = (exp.title or "").strip() or act.title_es or ""
        return {
            "title_es": title,
            "title_en": title,
            "description_es": (exp.description or "").strip() or "",
            "description_en": (exp.description or "").strip() or "",
            "short_description_es": (exp.short_description or "").strip() or "",
            "short_description_en": (exp.short_description or "").strip() or "",
            "location": (exp.location_name or "").strip() or "",
            "location_name": (exp.location_name or "").strip() or "",
            "location_address": (exp.location_address or "").strip() or "",
            "duration_minutes": getattr(exp, "duration_minutes", None),
            "included": list(exp.included) if getattr(exp, "included", None) else [],
            "not_included": list(exp.not_included) if getattr(exp, "not_included", None) else [],
            "itinerary": list(exp.itinerary) if getattr(exp, "itinerary", None) else [],
            "images": list(exp.images) if getattr(exp, "images", None) else [],
            "image": _first_image_url(getattr(exp, "images", None) or []),
        }
    # Native Erasmus activity (no linked experience)
    images = act.images or []
    return {
        "title_es": (act.title_es or "").strip(),
        "title_en": (act.title_en or act.title_es or "").strip(),
        "description_es": (act.description_es or "").strip(),
        "description_en": (act.description_en or act.description_es or "").strip(),
        "short_description_es": (act.short_description_es or "").strip(),
        "short_description_en": (act.short_description_en or act.short_description_es or "").strip(),
        "location": (act.location or "").strip(),
        "location_name": (getattr(act, "location_name", None) or "").strip(),
        "location_address": (getattr(act, "location_address", None) or "").strip(),
        "duration_minutes": getattr(act, "duration_minutes", None),
        "included": list(getattr(act, "included", None) or []),
        "not_included": list(getattr(act, "not_included", None) or []),
        "itinerary": list(getattr(act, "itinerary", None) or []),
        "images": list(images),
        "image": _first_image_url(images),
    }
