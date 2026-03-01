"""
Fetch Open Graph image (and optionally title) from a WhatsApp group invite page.

When you share a chat.whatsapp.com/CODE link, the preview shows the group photo because
WhatsApp serves that image in the page's og:image meta tag. We fetch the HTML and extract it.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

# Browser-like User-Agent so the server returns the same HTML as when shared
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Match <meta property="og:image" content="URL" /> or content='URL'
OG_IMAGE_RE = re.compile(
    r'<meta\s+[^>]*property\s*=\s*["\']og:image["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE | re.DOTALL,
)
# Alternative order: content before property
OG_IMAGE_RE_2 = re.compile(
    r'<meta\s+[^>]*content\s*=\s*["\']([^"\']+)["\'][^>]*property\s*=\s*["\']og:image["\']',
    re.IGNORECASE | re.DOTALL,
)

OG_TITLE_RE = re.compile(
    r'<meta\s+[^>]*property\s*=\s*["\']og:title["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE | re.DOTALL,
)
OG_TITLE_RE_2 = re.compile(
    r'<meta\s+[^>]*content\s*=\s*["\']([^"\']+)["\'][^>]*property\s*=\s*["\']og:title["\']',
    re.IGNORECASE | re.DOTALL,
)


def normalize_whatsapp_group_url(link: str) -> str | None:
    """
    Normalize a WhatsApp group invite URL to the form https://chat.whatsapp.com/<code>.
    Returns None if the link doesn't look like a WhatsApp group invite.
    """
    if not link or not isinstance(link, str):
        return None
    link = link.strip()
    if not link.startswith(("http://", "https://")):
        return None
    parsed = urlparse(link)
    netloc = (parsed.netloc or "").lower()
    if "chat.whatsapp.com" not in netloc:
        return None
    path = (parsed.path or "").strip("/")
    if not path:
        return None
    # path can be "CODE" or "invite/CODE"
    parts = path.split("/")
    code = parts[-1] if parts else None
    if not code or len(code) < 10:
        return None
    return f"https://chat.whatsapp.com/{code}"


def fetch_og_from_url(url: str, timeout: int = 10) -> dict:
    """
    Fetch HTML from url and extract og:image and og:title.
    Returns {"image": str|None, "title": str|None}.
    """
    result = {"image": None, "title": None}
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return result

    # Prefer first 300KB (WhatsApp docs say meta should be in first 300KB)
    html_chunk = html[: 300 * 1024]

    for pattern in (OG_IMAGE_RE, OG_IMAGE_RE_2):
        m = pattern.search(html_chunk)
        if m:
            result["image"] = m.group(1).strip()
            break
    for pattern in (OG_TITLE_RE, OG_TITLE_RE_2):
        m = pattern.search(html_chunk)
        if m:
            result["title"] = m.group(1).strip()
            break

    if result["image"] and not result["image"].startswith(("http://", "https://")):
        result["image"] = urljoin(url, result["image"])

    return result


def fetch_whatsapp_group_image(link: str, timeout: int = 10) -> dict:
    """
    Given a WhatsApp group invite link, fetch the group page and return og:image and og:title.
    Returns {"image": str|None, "title": str|None}. image is the full URL to use as image_url.
    """
    url = normalize_whatsapp_group_url(link)
    if not url:
        return {"image": None, "title": None}
    return fetch_og_from_url(url, timeout=timeout)
