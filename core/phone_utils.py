"""
Canonical phone number utilities for Tuki platform.
Storage: always use normalized form (E.164/digits) for matching.
Display: use format_phone_display for UI/API responses.
"""

import re


def normalize_phone_e164(raw: str) -> str:
    """
    Normalize phone number to digits-only form for storage and matching.
    Chile: 11 digits (56 + 9 digits) e.g. 56912345678.

    Args:
        raw: Raw phone string (e.g. '+56 9 1234 5678', '9 1234 5678', etc.)

    Returns:
        Digits-only string, empty if invalid/too short
    """
    if not raw or not isinstance(raw, str):
        return ''
    cleaned = re.sub(r'\D', '', str(raw).strip())
    # Chile: normalize 9-digit mobile to 56XXXXXXXXX
    if len(cleaned) == 9 and cleaned.startswith('9'):
        cleaned = '56' + cleaned
    if len(cleaned) >= 10:
        return cleaned
    return ''


def format_phone_display(raw: str) -> str:
    """
    Format phone for display (e.g. '+56 9 1234 5678' for Chile).

    Args:
        raw: Raw or normalized phone string

    Returns:
        Formatted string for display, or original if can't format
    """
    norm = normalize_phone_e164(raw)
    if not norm:
        return raw or ''
    # Chile: +56 9 XXXX XXXX
    if norm.startswith('56') and len(norm) == 11:
        return f"+{norm[:2]} {norm[2:3]} {norm[3:7]} {norm[7:]}"
    return f"+{norm}"
