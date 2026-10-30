"""Reading an ad's shared state: its latest analysis, best sprite and latest build."""

from __future__ import annotations

from sqlalchemy import func, select

from reel2play.analysis import CreativeBrief
from reel2play.models import Analysis, Build, Sprite
from reel2play.pipeline.runner import StepContext, StepFailedError


def latest_analysis(ctx: StepContext) -> Analysis:
    analysis = ctx.session.scalars(
        select(Analysis).where(Analysis.ad_id == ctx.ad.id).order_by(Analysis.created_at.desc())
    ).first()
    if analysis is None:
        raise StepFailedError("the director has not read this video yet")
    return analysis


def latest_brief(ctx: StepContext) -> CreativeBrief:
    return CreativeBrief.model_validate(latest_analysis(ctx).brief)


def best_sprite(ctx: StepContext) -> Sprite:
    """The main product's top-ranked cut-out, preferring good quality over the fallback's."""
    sprites = list(
        ctx.session.scalars(
            select(Sprite).where(Sprite.ad_id == ctx.ad.id, Sprite.product_index == 0)
        )
    )
    if not sprites:
        raise StepFailedError("the product has not been cut out yet")
    return min(sprites, key=lambda s: (s.quality != "good", s.rank))


def more_sprites(ctx: StepContext) -> list[Sprite]:
    """Feature 11: the other products' cut-outs, in the brief's order."""
    return list(
        ctx.session.scalars(
            select(Sprite)
            .where(Sprite.ad_id == ctx.ad.id, Sprite.product_index > 0)
            .order_by(Sprite.product_index)
        )
    )


def latest_build(ctx: StepContext) -> Build | None:
    return ctx.session.scalars(
        select(Build).where(Build.ad_id == ctx.ad.id).order_by(Build.number.desc())
    ).first()


def next_build_number(ctx: StepContext) -> int:
    count = ctx.session.scalar(select(func.count(Build.id)).where(Build.ad_id == ctx.ad.id))
    return int(count or 0) + 1
