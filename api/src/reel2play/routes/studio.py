"""The shop's studio (features 45 and 48): its ads, how each one is doing, what it cost,
and the brand kit kept for the next game. The browser proves which shop it is with the key
it was given at its first upload (header ``X-Shop-Key``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select

from reel2play import brand
from reel2play.ai import cost
from reel2play.brand_memory import remember
from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.insights import GameStats, stats_for
from reel2play.models import Ad, AdStatus, Analysis, Export, ExportKind, Shop, Suggestion
from reel2play.publish.hosted import page_link
from reel2play.settings import Settings
from reel2play.shops import shop_for_key

router = APIRouter(prefix="/api", tags=["studio"])
MAX_ADS = 50


class CostOut(BaseModel):
    calls: int
    usd: float
    pkr: float


class BrandKitOut(BaseModel):
    palette: list[str]
    tone: str
    logo_url: str | None


class AdSummary(BaseModel):
    id: uuid.UUID
    status: str
    # Feature 19: versions of one A/B test share a group; A is the first version.
    group_id: uuid.UUID | None = None
    variant: str = "A"
    template: str | None
    product: str | None
    created_at: datetime
    published_at: datetime | None
    link: str | None
    preview_url: str | None
    stats: dict[str, float | int | None]
    cost: CostOut


class ShopOut(BaseModel):
    id: uuid.UUID
    name: str
    language: str
    brand_kit: BrandKitOut | None
    ads: list[AdSummary]
    totals: dict[str, float | int]
    # Feature 53: what worked for this shop, one plain line per game type, the best first.
    memory: list[str] = []


def current_shop(session: SessionDep, key: str | None) -> Shop:
    shop = shop_for_key(session, key)
    if shop is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This browser is not linked to a shop.")
    return shop


def cost_out(summary: cost.CostSummary | None) -> CostOut:
    if summary is None:
        return CostOut(calls=0, usd=0.0, pkr=0.0)
    return CostOut(calls=summary.calls, usd=float(summary.usd), pkr=float(summary.pkr))


SHOWN_SUGGESTIONS = (Suggestion.USING, Suggestion.USED)


@router.get("/shop")
def my_shop(
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    x_shop_key: Annotated[str | None, Header()] = None,
) -> ShopOut:
    return shop_out(session, storage, settings, current_shop(session, x_shop_key))


def shop_out(session: SessionDep, storage: StorageDep, settings: Settings, shop: Shop) -> ShopOut:
    """A shop's studio: also what an agency member sees for one brand (feature 47)."""
    ads = list(
        session.scalars(
            select(Ad)
            .where(
                Ad.shop_id == shop.id,
                # Feature 44: an easier version shows once the owner has chosen it.
                or_(Ad.easier_for.is_(None), Ad.suggestion.in_(SHOWN_SUGGESTIONS)),
            )
            .order_by(Ad.created_at.desc())
            .limit(MAX_ADS)
        )
    )
    ids = [ad.id for ad in ads]
    products = {
        ad_id: str(brief["product"]["name"])
        for ad_id, brief in session.execute(
            select(Analysis.ad_id, Analysis.brief)
            .where(Analysis.ad_id.in_(ids))
            .order_by(Analysis.created_at)
        )
    }
    previews = {
        ad_id: storage.public_url(key)
        for ad_id, key in session.execute(
            select(Export.ad_id, Export.key).where(
                Export.ad_id.in_(ids), Export.kind == ExportKind.PREVIEW
            )
        )
    }
    stats, costs = stats_for(session, ids), cost.by_ad(session, ids)
    summaries = [
        AdSummary(
            id=ad.id,
            status=ad.status,
            group_id=ad.group_id,
            variant=ad.variant,
            template=ad.template,
            product=products.get(ad.id),
            created_at=ad.created_at,
            published_at=ad.published_at,
            link=page_link(settings.share_base, ad.slug)
            if ad.slug and ad.status == AdStatus.PUBLISHED
            else None,
            preview_url=previews.get(ad.id),
            stats=stats.get(ad.id, GameStats()).as_json(),
            cost=cost_out(costs.get(ad.id)),
        )
        for ad in ads
    ]
    kit = brand.current_kit(session, shop)
    return ShopOut(
        id=shop.id,
        name=shop.name,
        language=shop.language,
        brand_kit=BrandKitOut(
            palette=kit.palette,
            tone=kit.tone,
            logo_url=storage.signed_url(kit.logo_key) if kit.logo_key else None,
        )
        if kit
        else None,
        ads=summaries,
        memory=remember(session, shop).lines(),
        totals={
            "ads": len(ads),
            "published": sum(1 for ad in ads if ad.status == AdStatus.PUBLISHED),
            "plays": sum(s.plays for s in stats.values()),
            "cta_taps": sum(s.cta_taps for s in stats.values()),
            "pkr": round(sum(float(c.pkr) for c in costs.values()), 2),
        },
    )
