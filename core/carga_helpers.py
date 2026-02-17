"""
Helpers for the carga flow: Tuki organizer (superadmin-managed experiences)
and operator slug. Used when the real operator (e.g. Molantur) has no organizer
account yet; experiences are created under "Tuki" organizer with managed_operator_slug.
"""

import logging
from django.conf import settings
from django.utils.text import slugify

logger = logging.getLogger(__name__)

# Slug used for the platform organizer that holds managed-operator experiences
TUKI_ORGANIZER_SLUG = "tuki"
TUKI_ORGANIZER_NAME = "Tuki"


def get_or_create_tuki_organizer():
    """
    Get or create the organizer used for experiences managed by Tuki (superadmin)
    when the real operator (e.g. Molantur) does not have an organizer account yet.
    """
    from apps.organizers.models import Organizer

    contact_email = getattr(
        settings,
        "CARGA_TUKI_ORGANIZER_EMAIL",
        "carga@tuki.live",
    )
    organizer, created = Organizer.objects.get_or_create(
        slug=TUKI_ORGANIZER_SLUG,
        defaults={
            "name": TUKI_ORGANIZER_NAME,
            "description": "Cuenta Tuki para experiencias gestionadas por la plataforma (operadores sin cuenta propia).",
            "contact_email": contact_email,
            "status": "active",
            "has_experience_module": True,
            "onboarding_completed": True,
        },
    )
    if not organizer.has_experience_module:
        organizer.has_experience_module = True
        organizer.save(update_fields=["has_experience_module"])
    if created:
        logger.info(f"Organizador Tuki creado: {organizer.id}")
    return organizer


def normalize_operator_slug(value: str) -> str:
    """Normalize --organizer arg to a slug for managed_operator_slug (e.g. 'Molantur' -> 'molantur')."""
    if not value or not value.strip():
        return ""
    return slugify(value.strip()).replace("-", "") or value.strip().lower()[:100]
