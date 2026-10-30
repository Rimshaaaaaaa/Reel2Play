"""Studio keys: how a shop's browser finds its ads again (feature 45) without accounts.

The first web upload makes a shop and hands back a random key once; the browser keeps it.
Only the key's SHA-256 is stored, so a database copy cannot open anyone's studio.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play.models import Shop

KEY_BYTES = 24


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def issue_key(shop: Shop) -> str:
    key = secrets.token_urlsafe(KEY_BYTES)
    shop.access_key_hash = key_hash(key)
    return key


def key_matches(shop: Shop, key: str | None) -> bool:
    if not key or not shop.access_key_hash:
        return False
    return hmac.compare_digest(shop.access_key_hash, key_hash(key))


def shop_for_key(session: Session, key: str | None) -> Shop | None:
    if not key:
        return None
    return session.scalars(select(Shop).where(Shop.access_key_hash == key_hash(key))).first()
