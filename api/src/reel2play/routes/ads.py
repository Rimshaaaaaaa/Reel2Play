"""Ad status for the web app: the current step, what the director found, and progress lines."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from reel2play import audit
from reel2play.analysis import CreativeBrief
from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.models import Ad, AdStatus, Analysis, Build, Export, ExportKind, Sprite
from reel2play.publish.embed import embeds
from reel2play.publish.hosted import page_link

router = APIRouter(prefix="/api/ads", tags=["ads"])


class ProgressLine(BaseModel):
    at: datetime
    actor: str
    action: str
    message: str


class SpriteOut(BaseModel):
    url: str
    method: str
    quality: str
    # Feature 11: 0 is the main product, 1 to 3 the other products.
    product_index: int = 0
    # Feature 7: the moving product, square frames side by side.
    strip_url: str | None = None
    strip_frames: int = 0


class BriefOut(BaseModel):
    product: str
    category: str
    palette: list[str]
    language: str
    price: str | None
    offer_text: str | None
    offer_source: str
    occasion: str = "none"
    more_products: list[str] = []


class GateOut(BaseModel):
    gate: str
    label: str
    passed: bool
    message: str
    screenshot_url: str | None


class ReportOut(BaseModel):
    passed: bool
    language: str
    rounds: int
    summary: str
    next_step: str
    gates: list[GateOut]
    screenshots: dict[str, str]
    # Feature 31: things the shop should look at (claims it cannot prove, a missing price).
    warnings: list[str] = []


class EmbedOut(BaseModel):
    shape: str
    src: str
    code: str


class ShareOut(BaseModel):
    """Everything a published ad leaves with (features 32 to 35)."""

    link: str
    preview_url: str | None
    reel_url: str | None
    reel_seconds: float | None
    lead_in_url: str | None
    meta_html_url: str | None
    meta_zip_url: str | None
    captions: dict[str, object] | None
    published_at: datetime | None
    # Feature 18: the same game as a square or landscape page, and Reels in those shapes.
    square_link: str | None = None
    landscape_link: str | None = None
    square_reel_url: str | None = None
    wide_reel_url: str | None = None
    # Feature 36: the counter poster (A4 PDF) and a small picture of it.
    poster_url: str | None = None
    poster_preview_url: str | None = None
    # Feature 37: snippets for the shop's own website.
    embeds: list[EmbedOut] = []


class AdOut(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    status: str
    step: str | None
    error: str | None
    is_synthetic: bool
    brief: BriefOut | None
    sprites: list[SpriteOut]
    template: str | None
    build_url: str | None
    report: ReportOut | None
    share: ShareOut | None
    progress: list[ProgressLine]
    # Feature 19: which shop made it (for the A/B button) and which version it is.
    shop_id: uuid.UUID | None = None
    variant: str = "A"
    # Feature 44: an easier version of another game, and where it stands with the owner.
    easier_for: uuid.UUID | None = None
    suggestion: str | None = None


def _brief(session: SessionDep, ad: Ad) -> BriefOut | None:
    raw = session.scalars(
        select(Analysis.brief).where(Analysis.ad_id == ad.id).order_by(Analysis.created_at.desc())
    ).first()
    if raw is None:
        return None
    brief = CreativeBrief.model_validate(raw)
    return BriefOut(
        product=brief.product.name,
        category=brief.product.category,
        palette=brief.palette,
        language=brief.language,
        price=brief.price,
        offer_text=brief.offer_text,
        offer_source=brief.offer_source,
        occasion=brief.occasion,
        more_products=[p.name for p in brief.more_products],
    )


def _report(ad: Ad, storage: StorageDep) -> ReportOut | None:
    if not ad.report:
        return None
    raw = ad.report

    def url(key: str | None) -> str | None:
        return storage.signed_url(key) if key else None

    return ReportOut(
        passed=raw["passed"],
        language=raw["language"],
        rounds=raw["rounds"],
        summary=raw["summary"],
        next_step=raw["next_step"],
        warnings=raw.get("warnings", []),
        gates=[
            GateOut(
                gate=g["gate"],
                label=g["label"],
                passed=g["passed"],
                message=g["message"],
                screenshot_url=url(g.get("screenshot_key")),
            )
            for g in raw["gates"]
        ],
        screenshots={name: storage.signed_url(key) for name, key in raw["screenshots"].items()},
    )


def _share(
    session: SessionDep, ad: Ad, storage: StorageDep, share_base: str, title: str
) -> ShareOut | None:
    if ad.status != AdStatus.PUBLISHED or not ad.slug:
        return None
    exports = {e.kind: e for e in session.scalars(select(Export).where(Export.ad_id == ad.id))}

    def url(kind: ExportKind) -> str | None:
        export = exports.get(kind)
        if export is None:
            return None
        return storage.public_url(export.key) if export.public else storage.signed_url(export.key)

    reel = exports.get(ExportKind.REEL)
    link = page_link(share_base, ad.slug)
    return ShareOut(
        link=link,
        square_link=f"{link}?layout=square",
        landscape_link=f"{link}?layout=landscape",
        square_reel_url=url(ExportKind.REEL_SQUARE),
        wide_reel_url=url(ExportKind.REEL_WIDE),
        preview_url=url(ExportKind.PREVIEW),
        reel_url=url(ExportKind.REEL),
        reel_seconds=float(reel.details.get("seconds", 0)) if reel else None,
        lead_in_url=url(ExportKind.LEAD_IN),
        meta_html_url=url(ExportKind.META_HTML),
        meta_zip_url=url(ExportKind.META_ZIP),
        poster_url=url(ExportKind.POSTER),
        poster_preview_url=url(ExportKind.POSTER_PREVIEW),
        embeds=[EmbedOut(shape=e.shape, src=e.src, code=e.code) for e in embeds(link, title)],
        captions=ad.captions,
        published_at=ad.published_at,
    )


def game_title(build: Build | None) -> str:
    """What a screen reader says for an embedded game: "Play: <product>"."""
    if build is None:
        return "Play the game"
    return f"Play: {build.config['text']['productName']}"


@router.get("/{ad_id}")
def get_ad(
    ad_id: uuid.UUID, session: SessionDep, storage: StorageDep, settings: SettingsDep
) -> AdOut:
    ad = session.get(Ad, ad_id)
    if ad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ad not found")
    sprites = session.scalars(
        select(Sprite).where(Sprite.ad_id == ad.id).order_by(Sprite.product_index, Sprite.rank)
    )
    latest = session.scalars(
        select(Build).where(Build.ad_id == ad.id).order_by(Build.number.desc())
    ).first()
    return AdOut(
        id=ad.id,
        shop_id=ad.shop_id,
        variant=ad.variant,
        easier_for=ad.easier_for,
        suggestion=ad.suggestion,
        video_id=ad.video_id,
        status=ad.status,
        step=ad.step,
        error=ad.error,
        is_synthetic=ad.is_synthetic,
        brief=_brief(session, ad),
        sprites=[
            SpriteOut(
                url=storage.signed_url(s.sprite_key),
                method=s.method,
                quality=s.quality,
                product_index=s.product_index,
                strip_url=storage.signed_url(s.track_key) if s.track_key else None,
                strip_frames=s.track_frames,
            )
            for s in sprites
        ],
        template=ad.template,
        build_url=storage.signed_url(latest.html_key) if latest else None,
        report=_report(ad, storage),
        share=_share(session, ad, storage, settings.share_base, game_title(latest)),
        progress=[
            ProgressLine(
                at=e.created_at, actor=e.actor, action=e.action, message=str(e.data["message"])
            )
            for e in audit.entries_for(session, "ad", ad.id)
            if "message" in e.data
        ],
    )
