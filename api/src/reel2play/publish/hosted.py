"""The hosted game page and its short link (feature 32).

The page is the tested game file itself, with link-preview tags added to its head so a
shared link shows the end card and the offer. The short code is random: nothing about the
shop or a customer is in the link.
"""

from __future__ import annotations

import html
import json
import secrets
import string
from urllib.parse import urlsplit

SLUG_ALPHABET = string.ascii_letters + string.digits
SLUG_LENGTH = 7


def new_slug() -> str:
    return "".join(secrets.choice(SLUG_ALPHABET) for _ in range(SLUG_LENGTH))


def page_link(share_base: str, slug: str) -> str:
    return f"{share_base}/g/{slug}"


def preview_tags(*, title: str, description: str, image_url: str, page_url: str) -> str:
    tags = {
        "og:type": "website",
        "og:title": title,
        "og:description": description,
        "og:image": image_url,
        "og:url": page_url,
        "twitter:card": "summary_large_image",
    }
    lines = [
        f'<meta property="{name}" content="{html.escape(value, quote=True)}">'
        for name, value in tags.items()
    ]
    lines.append(f'<meta name="description" content="{html.escape(description, quote=True)}">')
    return "\n".join(lines)


def analytics_tag(endpoint: str, ad_id: str, variant: str, coupons: str | None = None) -> str:
    """Where the page counts plays, finishes and order taps (feature 39), and where it asks
    for a unique win code (feature 40). Only hosted pages carry it; the tested file has none,
    so play-tests make no requests."""
    found: dict[str, str] = {"endpoint": endpoint, "adId": ad_id, "variant": variant}
    if coupons:
        found["coupons"] = coupons
    value = json.dumps(found)
    return f'<meta name="r2p-analytics" content="{html.escape(value, quote=True)}">'


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def with_preview(page: bytes, tags: str) -> bytes:
    """Insert the tags after the page title, near the top of the head where link-preview
    crawlers look; the game itself is untouched."""
    text = page.decode("utf-8")
    marker = "</title>"
    at = text.find(marker)
    if at < 0:
        raise ValueError("the game page has no <title>")
    at += len(marker)
    return (text[:at] + "\n" + tags + text[at:]).encode("utf-8")


def optin_tag(link: str) -> str:
    """Feature 43: the end card's "Get offers on WhatsApp" link, added when the page is served,
    so turning sign-ups on or off in the studio applies to every live game at once."""
    value = json.dumps({"url": link})
    return f'<meta name="r2p-optin" content="{html.escape(value, quote=True)}">'
