"""The gallery of evaluated ads (feature 61) and the blind preference page (feature 41).

The preference page shows one ad two ways, side by side and unlabelled: the playable game
and a still ad made from the shop's own key frame, offer and price. Which side the game is
on is random, and only the pick and the side are kept.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from reel2play.analysis import CreativeBrief
from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.insights import GameStats, stats_for
from reel2play.models import Ad, AdStatus, Analysis, Export, ExportKind, Preference
from reel2play.publish.hosted import page_link

router = APIRouter(prefix="/api", tags=["gallery"])
_PICK = random.SystemRandom()


class GalleryAd(BaseModel):
    id: uuid.UUID
    product: str
    category: str
    language: str
    template: str | None
    link: str
    preview_url: str | None
    published_at: datetime | None
    stats: dict[str, float | int | None]


class StillAd(BaseModel):
    image_url: str
    product: str
    offer: str | None
    price: str | None
    language: str


class Comparison(BaseModel):
    ad_id: uuid.UUID
    game_url: str
    still: StillAd
    game_side: Literal["left", "right"]


class Vote(BaseModel):
    ad_id: uuid.UUID
    choice: Literal["game", "still"]
    game_side: Literal["left", "right"]


class VoteTotals(BaseModel):
    votes: int
    game: int
    game_share: float | None


def latest_brief(session: SessionDep, ad_id: uuid.UUID) -> CreativeBrief | None:
    raw = session.scalars(
        select(Analysis.brief).where(Analysis.ad_id == ad_id).order_by(Analysis.created_at.desc())
    ).first()
    return CreativeBrief.model_validate(raw) if raw else None


def published_ads(session: SessionDep, *, gallery_only: bool) -> list[Ad]:
    stmt = select(Ad).where(Ad.status == AdStatus.PUBLISHED, Ad.slug.is_not(None))
    if gallery_only:
        stmt = stmt.where(Ad.in_gallery.is_(True))
    return list(session.scalars(stmt.order_by(Ad.published_at.desc()).limit(60)))


@router.get("/gallery")
def gallery(session: SessionDep, storage: StorageDep, settings: SettingsDep) -> list[GalleryAd]:
    ads = published_ads(session, gallery_only=True)
    stats = stats_for(session, [ad.id for ad in ads])
    rows = session.execute(
        select(Export.ad_id, Export.key).where(
            Export.ad_id.in_([ad.id for ad in ads]), Export.kind == ExportKind.PREVIEW
        )
    )
    previews = {row.ad_id: row.key for row in rows}
    items: list[GalleryAd] = []
    for ad in ads:
        brief = latest_brief(session, ad.id)
        if brief is None or ad.slug is None:
            continue
        items.append(
            GalleryAd(
                id=ad.id,
                product=brief.product.name,
                category=brief.product.category,
                language=brief.language,
                template=ad.template,
                link=page_link(settings.share_base, ad.slug),
                preview_url=storage.public_url(previews[ad.id]) if ad.id in previews else None,
                published_at=ad.published_at,
                stats=stats.get(ad.id, GameStats()).as_json(),
            )
        )
    return items


@router.get("/compare")
def compare(session: SessionDep, storage: StorageDep, settings: SettingsDep) -> Comparison:
    """One published ad (from the gallery when there is one), the game on a random side."""
    ads = published_ads(session, gallery_only=True) or published_ads(session, gallery_only=False)
    candidates = [(ad, brief) for ad in ads if (brief := latest_brief(session, ad.id))]
    if not candidates:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no published games to compare yet")
    ad, brief = _PICK.choice(candidates)
    assert ad.slug is not None
    return Comparison(
        ad_id=ad.id,
        game_url=page_link(settings.share_base, ad.slug),
        still=StillAd(
            image_url=storage.signed_url(brief.key_frames[0].key),
            product=brief.product.name,
            offer=brief.offer_text,
            price=brief.price,
            language=brief.language,
        ),
        game_side=_PICK.choice(["left", "right"]),
    )


@router.post("/compare", status_code=status.HTTP_204_NO_CONTENT)
def vote(body: Vote, session: SessionDep) -> None:
    ad = session.get(Ad, body.ad_id)
    if ad is None or ad.status != AdStatus.PUBLISHED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no published game")
    session.add(Preference(ad_id=ad.id, choice=body.choice, game_side=body.game_side))


@router.get("/compare/results")
def results(session: SessionDep) -> VoteTotals:
    votes, game = session.execute(
        select(
            func.count(Preference.id),
            func.count(Preference.id).filter(Preference.choice == "game"),
        )
    ).one()
    return VoteTotals(
        votes=int(votes), game=int(game), game_share=round(game / votes, 3) if votes else None
    )
