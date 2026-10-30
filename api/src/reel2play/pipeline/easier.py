"""Self-improving loop (feature 44): when players find a live game hard, an easier version
is made, tested like any game, and suggested to the owner, who decides.

1. Trigger. After enough plays, the anonymous numbers decide: too few players reach the
   end, or too few of those who finish win. Code decides this, not a model.
2. Easier version. The director reads the numbers and proposes new parameter values for
   the same game; code keeps only the changes that really make it easier and stay inside
   the template's ranges, and steps it down itself when the model's answer does not help.
   The template, words and colours stay the same, so it is the same game, kinder.
3. Test. The easier version goes through the play-tester and every gate, and the fix loop
   if needed. It is not published on its own.
4. The owner decides. "Use it" publishes it under the game's existing link, so every
   shared link, poster and website embed opens the easier game; the old one is kept as
   replaced. "Not now" leaves the live game as it is.
"""

from __future__ import annotations

import json
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play.ai.client import AIUnavailableError
from reel2play.ai.jsonout import JSONOutputError
from reel2play.builder.proposal import GameProposal
from reel2play.builder.templates import TemplateSpec, Tier, load_templates
from reel2play.insights import GameStats, stats_for
from reel2play.jobs import enqueue
from reel2play.models import Ad, AdStatus, Build, Suggestion
from reel2play.pipeline.build import compile_and_store
from reel2play.pipeline.runner import PIPELINE, STEP_JOB, StepContext, StepFailedError
from reel2play.pipeline.state import latest_brief
from reel2play.pipeline.variants import copy_ad, group_of
from reel2play.settings import Settings

PROMPT = "director_easier"
STEP_SHARE = 0.5  # code's own step: half the gap between the hard and easy values


class EasierPlan(BaseModel):
    """The director's proposal for an easier tuning of the same game."""

    difficulty: Tier = Tier.EASY
    difficulty_overrides: dict[str, float] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=240)


# --- 1. the trigger ---------------------------------------------------------------------------


def too_hard(stats: GameStats, settings: Settings) -> str | None:
    """Why the numbers say players find the game hard, or None while they do not (yet)."""
    if stats.plays < settings.easier_after_plays:
        return None
    completion = stats.completion or 0.0
    if completion < settings.easier_below_completion:
        return f"only {completion:.0%} of {stats.plays} plays reached the end"
    win_share = stats.wins / stats.finishes if stats.finishes else 0.0
    if win_share < settings.easier_below_wins:
        return f"only {win_share:.0%} of {stats.finishes} finished games were won"
    return None


def latest_build_of(session: Session, ad: Ad) -> Build | None:
    return session.scalars(
        select(Build).where(Build.ad_id == ad.id).order_by(Build.number.desc())
    ).first()


def suggestion_for(session: Session, ad: Ad) -> Ad | None:
    """The latest easier version made for this game, if any."""
    return session.scalars(
        select(Ad).where(Ad.easier_for == ad.id).order_by(Ad.created_at.desc())
    ).first()


def offer_easier(session: Session, ad_id: uuid.UUID, settings: Settings) -> Ad | None:
    """Called after each finished play: start an easier version when the numbers call for
    one. At most one per game; never during an A/B test, which is the owner's own experiment."""
    ad = session.scalars(select(Ad).where(Ad.id == ad_id).with_for_update()).first()
    if ad is None or ad.status != AdStatus.PUBLISHED or not settings.easier_versions:
        return None
    if suggestion_for(session, ad) is not None or len(group_of(session, ad)) > 1:
        return None
    stats = stats_for(session, [ad.id]).get(ad.id, GameStats())
    reason = too_hard(stats, settings)
    if reason is None:
        return None
    easier = copy_ad(
        session,
        ad,
        f"An easier version: players find the live game hard ({reason}).",
        easier_for=ad.id,
        suggestion=Suggestion.MAKING,
    )
    enqueue(session, STEP_JOB, {"ad_id": str(easier.id), "step": "easier"})
    return easier


# --- 2. the easier version ------------------------------------------------------------------


def easier_direction(spec: TemplateSpec, name: str) -> int:
    """+1 when a larger value is easier, -1 when a smaller one is, 0 when the tiers agree."""
    param = spec.params[name]
    if param.easy == param.hard:
        return 0
    return 1 if param.easy > param.hard else -1


def easier_values(
    spec: TemplateSpec, before: dict[str, float], plan: EasierPlan | None
) -> dict[str, float]:
    """The values for the easier version. The model's are kept only where they are easier
    than now and inside the ranges; if none are, code steps every value down itself."""
    after = dict(before)
    if plan is not None:
        proposed = spec.resolve(plan.difficulty, plan.difficulty_overrides)
        for name, value in proposed.items():
            direction = easier_direction(spec, name)
            if direction and (value - before[name]) * direction > 0:
                after[name] = spec.params[name].clamp(value)
    if after == before:
        for name, param in spec.params.items():
            step = (param.easy - param.hard) * STEP_SHARE
            after[name] = param.clamp(before[name] + step)
    return after


def describe(before: dict[str, float], after: dict[str, float]) -> str:
    changes = [
        f"{name.replace('_', ' ')} {before[name]:g} to {after[name]:g}"
        for name in after
        if after[name] != before[name]
    ]
    return ", ".join(changes)


def numbers_line(stats: GameStats) -> str:
    return (
        f"{stats.plays} plays, {stats.finishes} reached the end, {stats.wins} won, "
        f"median time {stats.median_seconds if stats.median_seconds is not None else '-'} s"
    )


@PIPELINE.add(
    "easier",
    AdStatus.BUILDING,
    "director",
    "Players find the game hard; the director is making an easier version.",
)
def easier(ctx: StepContext) -> str:
    base = ctx.session.get(Ad, ctx.ad.easier_for) if ctx.ad.easier_for else None
    base_build = latest_build_of(ctx.session, base) if base else None
    if base is None or base_build is None:
        raise StepFailedError("the game to make easier is gone")
    previous = GameProposal.model_validate(base_build.proposal)
    spec = load_templates(ctx.settings.templates_dir)[previous.template]
    before = {k: float(v) for k, v in base_build.config["difficulty"].items()}
    stats = stats_for(ctx.session, [base.id]).get(base.id, GameStats())
    plan: EasierPlan | None
    try:
        plan = ctx.ai.ask_json(
            PROMPT,
            {
                "template": f"{spec.id} ({spec.description})",
                "ranges": spec.ranges_line(),
                "values": json.dumps(before),
                "numbers": numbers_line(stats),
            },
            EasierPlan,
            subject=ctx.subject,
        )
    except (AIUnavailableError, JSONOutputError):
        plan = None
    after = easier_values(spec, before, plan)
    if after == before:
        ctx.ad.suggestion = Suggestion.DISMISSED
        raise StepFailedError("the game is already as easy as its template allows")
    proposal = previous.model_copy(update={"difficulty_overrides": after})
    change = describe(before, after)
    ctx.say(
        "director",
        "easier.designed",
        f"Easier version of the same game: {change}."
        + (f" Why players struggle: {plan.reason}" if plan and plan.reason else ""),
        change=change,
        by="model" if plan else "code",
        numbers=stats.as_json(),
    )
    compile_and_store(ctx, latest_brief(ctx), proposal)
    return "test"


# --- 4. the owner decides ----------------------------------------------------------------------


def hold_for_owner(ctx: StepContext) -> None:
    """Called by the publish step: an easier version waits for the owner instead."""
    ctx.ad.status = AdStatus.READY
    ctx.ad.suggestion = Suggestion.READY
    ctx.say(
        "publisher",
        "easier.ready",
        "The easier version passed every check. It goes live only when you choose it.",
    )


class SuggestionError(ValueError):
    pass


def use_easier(session: Session, suggestion: Ad) -> None:
    """The owner chose the easier version: publish it under the live game's link."""
    if suggestion.suggestion != Suggestion.READY or suggestion.status != AdStatus.READY:
        raise SuggestionError("This easier version is not ready to use.")
    suggestion.suggestion = Suggestion.USING
    suggestion.status = AdStatus.PUBLISHING
    enqueue(session, STEP_JOB, {"ad_id": str(suggestion.id), "step": "publish"})


def dismiss_easier(suggestion: Ad) -> None:
    if suggestion.suggestion not in (Suggestion.READY, Suggestion.MAKING):
        raise SuggestionError("This easier version cannot be put away now.")
    suggestion.suggestion = Suggestion.DISMISSED


def link_slug(ctx: StepContext) -> str | None:
    """While an easier version is being published, it is published under the live game's
    short link, so every shared link and poster opens it."""
    if ctx.ad.easier_for and ctx.ad.suggestion == Suggestion.USING:
        base = ctx.session.get(Ad, ctx.ad.easier_for)
        return base.slug if base is not None else None
    return None


def take_over_link(ctx: StepContext) -> None:
    """At the end of that publish: the easier version takes the link, the old game steps
    aside (kept, as replaced, with its numbers)."""
    if not (ctx.ad.easier_for and ctx.ad.suggestion == Suggestion.USING):
        return
    base = ctx.session.get(Ad, ctx.ad.easier_for)
    slug = base.slug if base is not None else None
    if base is not None:
        base.slug = None
        base.status = AdStatus.REPLACED
        ctx.session.flush()
    ctx.ad.slug = slug or ctx.ad.slug
    ctx.ad.suggestion = Suggestion.USED
    ctx.say(
        "publisher",
        "easier.used",
        "The easier version is live under the same link; the old version is kept as replaced.",
    )


def is_waiting_suggestion(ad: Ad) -> bool:
    return bool(ad.easier_for) and ad.suggestion in (Suggestion.MAKING, Suggestion.READY)
