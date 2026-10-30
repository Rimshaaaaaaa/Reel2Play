"""End-card call to action (features 17 and 38): a WhatsApp chat with the order already
written, or the shop's own link. Links carry the product and a coupon code, never anything
about the player.
"""

from __future__ import annotations

import hashlib
import uuid
from urllib.parse import quote

from reel2play.builder.config import Cta

MESSAGES = {
    "en": "Hi {shop}! I played your game and want to order: {product}.{code}",
    "ur": "السلام علیکم {shop}! میں نے آپ کی گیم کھیلی، مجھے یہ چاہیے: {product}\u06d4{code}",
}
CODE_LINES = {"en": " My code: {coupon}", "ur": " میرا کوڈ: {coupon}"}
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def coupon_code(ad_id: uuid.UUID) -> str:
    """A short, readable code for this ad, like R2P-7KQD (no 0/O or 1/I to confuse)."""
    digest = hashlib.sha256(ad_id.bytes).digest()
    return "R2P-" + "".join(ALPHABET[b % len(ALPHABET)] for b in digest[:4])


def order_message(language: str, shop: str, product: str, coupon: str | None) -> str:
    code = CODE_LINES[language].format(coupon=coupon) if coupon else ""
    return MESSAGES[language].format(shop=shop, product=product, code=code)


def build_cta(kind: str, target: str | None, message: str) -> Cta:
    if kind == "whatsapp" and target:
        return Cta(kind="whatsapp", url=f"https://wa.me/{target}?text={quote(message)}")
    if target and target.startswith("https://"):
        return Cta(kind="link", url=target)
    raise ValueError("the ad needs a WhatsApp number or an https shop link")
