"""
Servicio modular para código público de alojamientos (formato tuqui{N}-{random}).
Se genera automáticamente al publicar; no es obligatorio en JSON ni en creación.
"""

import secrets
from typing import List

from django.db.models import Max

from .models import Accommodation


# Configuración centralizada (fácil de cambiar sin tocar lógica)
PUBLIC_CODE_PREFIX = "tuqui"
RANDOM_SUFFIX_LENGTH = 6
RANDOM_CHARSET = "abcdefghjkmnpqrstuvwxyz23456789"  # sin i,l,1,0 para evitar confusiones


def get_next_display_order() -> int:
    """
    Devuelve el siguiente número de orden disponible (1-based).
    Si no hay alojamientos con display_order, devuelve 1.
    """
    result = Accommodation.objects.aggregate(max_order=Max("display_order"))
    max_order = result.get("max_order")
    if max_order is None:
        return 1
    return max_order + 1


def _random_suffix() -> str:
    """Genera una cadena aleatoria de longitud RANDOM_SUFFIX_LENGTH con charset seguro."""
    return "".join(secrets.choice(RANDOM_CHARSET) for _ in range(RANDOM_SUFFIX_LENGTH))


def generate_public_code(display_order: int, prefix: str | None = None) -> str:
    """
    Genera un código público único.
    - Si prefix está definido (ej. "Tuki-PV"): devuelve "{prefix}-{número de 3 dígitos}", ej. Tuki-PV-001.
    - Si no: formato por defecto tuqui{N}-{suffix} aleatorio, ej. tuqui1-a2b3c4.
    El número (display_order) es único globalmente.
    """
    if display_order is None or display_order < 1:
        display_order = get_next_display_order()
    custom_prefix = (prefix or "").strip()
    if custom_prefix:
        return f"{custom_prefix}-{display_order:03d}"
    suffix = _random_suffix()
    code = f"{PUBLIC_CODE_PREFIX}{display_order}-{suffix}"
    while Accommodation.objects.filter(public_code=code).exists():
        suffix = _random_suffix()
        code = f"{PUBLIC_CODE_PREFIX}{display_order}-{suffix}"
    return code


def ensure_public_code_on_publish(accommodation: Accommodation) -> List[str]:
    """
    Si el alojamiento está (o queda) publicado y no tiene public_code,
    asigna display_order (si no tiene) y genera public_code.
    Usa public_code_prefix si está definido (ej. Tuki-PV-001); si no, tuqui{N}-{random}.
    Modifica el objeto en memoria; no hace save().
    Retorna la lista de nombres de campos a añadir a update_fields.
    """
    if accommodation.status != "published":
        return []
    updated: List[str] = []
    if accommodation.display_order is None or accommodation.display_order < 1:
        accommodation.display_order = get_next_display_order()
        updated.append("display_order")
    if not ((accommodation.public_code or "").strip()):
        prefix = (accommodation.public_code_prefix or "").strip() or None
        accommodation.public_code = generate_public_code(accommodation.display_order, prefix=prefix)
        updated.append("public_code")
    return updated
