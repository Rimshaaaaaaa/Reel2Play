"""A/B tests (feature 19): make versions B and C of a published ad, read how each is doing,
and the one link (/v/<code>) that shares visitors between them."""

from __future__ import annotations

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.insights import leader, stats_for
from reel2play.models import Ad, AdStatus, Export, ExportKind, Shop
from reel2play.pipeline.variants import VariantsNotReadyError, group_of, start_variants
from reel2play.publish.hosted import page_link
from reel2play.routes.game_page import SLUG, serve_page, shop_optin
from reel2play.shops import key_matches

router = APIRouter(tags=["a/b tests"])


class VersionOut(BaseModel):
    id: uuid.UUID
    variant: str
    status: str
    template: str | None
    link: str | None
    stats: dict[str, float | int | None]


class AbTestOut(BaseModel):
    link: str | None
    versions: list[VersionOut]
    leader: str | None
    verdict: str


def ab_test_out(session: SessionDep, base: Ad, share_base: str) -> AbTestOut:
    group = group_of(session, base)
    first = next((ad for ad in group if ad.variant == "A"), base)
    stats = stats_for(session, [ad.id for ad in group])
    published = {ad.variant: stats.get(ad.id) for ad in group if ad.status == AdStatus.PUBLISHED}
    best, verdict = leader({v: s for v, s in published.items() if s is not None})
    if len(published) >= 2 and best is None and any(s is None for s in published.values()):
        verdict = "Waiting for the first plays of every version."
    return AbTestOut(
        link=f"{share_base.rstrip('/')}/v/{first.ab_slug}" if first.ab_slug else None,
        versions=[
            VersionOut(
                id=ad.id,
                variant=ad.variant,
                status=ad.status,
                template=ad.template,
                link=page_link(share_base, ad.slug) if ad.slug else None,
                stats=stats[ad.id].as_json() if ad.id in stats else {},
            )
            for ad in group
        ],
        leader=best,
        verdict=verdict,
    )


def ad_or_404(session: SessionDep, ad_id: uuid.UUID) -> Ad:
    ad = session.get(Ad, ad_id)
    if ad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ad not found")
    return ad


@router.get("/api/ads/{ad_id}/variants")
def read_ab_test(ad_id: uuid.UUID, session: SessionDep, settings: SettingsDep) -> AbTestOut:
    return ab_test_out(session, ad_or_404(session, ad_id), settings.share_base)


@router.post("/api/ads/{ad_id}/variants", status_code=status.HTTP_201_CREATED)
def make_versions(
    ad_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    x_shop_key: Annotated[str | None, Header()] = None,
) -> AbTestOut:
    ad = ad_or_404(session, ad_id)
    shop = session.get(Shop, ad.shop_id)
    if shop is None or not key_matches(shop, x_shop_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the shop that made this game can.")
    try:
        start_variants(session, ad)
    except VariantsNotReadyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ab_test_out(session, ad, settings.share_base)


@router.api_route("/v/{slug}", methods=["GET", "HEAD"])
def ab_page(slug: str, session: SessionDep, storage: StorageDep, settings: SettingsDep) -> Response:
    """One of the test's published versions, picked at random for each visit."""
    if not SLUG.fullmatch(slug):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no test at this link")
    first = session.scalar(select(Ad).where(Ad.ab_slug == slug))
    keys = (
        list(
            session.scalars(
                select(Export.key)
                .join(Ad, Ad.id == Export.ad_id)
                .where(
                    Ad.group_id == first.group_id,
                    Ad.status == AdStatus.PUBLISHED,
                    Export.kind == ExportKind.HOSTED,
                )
            )
        )
        if first
        else []
    )
    if not keys:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no test at this link")
    optin = shop_optin(session, settings, first.shop_id) if first else None
    return serve_page(storage, settings, secrets.choice(keys), cache="no-store", optin=optin)
