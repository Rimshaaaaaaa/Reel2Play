"""Brand kit (feature 9): a shop's palette, logo and tone, saved for its next game."""

from __future__ import annotations

from sqlalchemy.orm import Session

from reel2play.models import BrandKit, Shop


def current_kit(session: Session, shop: Shop) -> BrandKit | None:
    return session.get(BrandKit, shop.brand_kit_id) if shop.brand_kit_id else None


def describe(kit: BrandKit | None) -> str:
    """One line for the director's prompt."""
    if kit is None:
        return "none yet (first game for this shop)"
    logo = "a saved logo" if kit.logo_key else "no saved logo"
    return f"colours {', '.join(kit.palette) or 'none'}; tone '{kit.tone or 'unknown'}'; {logo}"


def save_kit(
    session: Session, shop: Shop, palette: list[str], tone: str, logo_key: str | None
) -> BrandKit:
    """Create or update the shop's kit. A new logo replaces the old one; none keeps it."""
    kit = current_kit(session, shop)
    if kit is None:
        kit = BrandKit(shop_id=shop.id, palette=palette, tone=tone, logo_key=logo_key, fonts=[])
        session.add(kit)
        session.flush()
        shop.brand_kit_id = kit.id
        return kit
    kit.palette = palette
    kit.tone = tone
    if logo_key:
        kit.logo_key = logo_key
    return kit
