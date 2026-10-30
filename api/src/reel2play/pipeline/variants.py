"""Three versions of an ad for an A/B test (feature 19).

Version A is the ad as first made. Versions B and C reuse its reading of the video and its
cut-outs, and start again at the build step, where the director designs a different game:
another template, other colours and other button words. Code makes sure each version really
differs, and each one is tested and published like any ad. One link (``/v/<code>``) shares
visitors between the published versions; the anonymous events say which version each play
was, so the studio can show which one does best.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.analysis import CreativeBrief
from reel2play.builder.proposal import GameProposal, clean_quiz
from reel2play.builder.templates import TemplateSpec, buildable
from reel2play.jobs import enqueue
from reel2play.models import Ad, AdStatus, Analysis, Batch, Build, Sprite, Video
from reel2play.pipeline.runner import STEP_JOB
from reel2play.publish.hosted import new_slug

VERSIONS = ("B", "C")
SPRITE_FIELDS = (
    "source_frame_key", "mask_key", "sprite_key", "method", "quality", "score", "width",
    "height", "area_fraction", "rank", "product_index", "track_key", "track_frames",
    "track_fps", "track_method", "face_check",
)  # fmt: skip


class VariantsNotReadyError(ValueError):
    """Only a published first version can be split into an A/B test."""


def group_of(session: Session, ad: Ad) -> list[Ad]:
    return list(session.scalars(select(Ad).where(Ad.group_id == ad.group_id).order_by(Ad.variant)))


def unique_ab_slug(session: Session) -> str:
    while True:
        slug = new_slug()
        if session.scalar(select(Ad.id).where(Ad.ab_slug == slug)) is None:
            return slug


def latest_analysis_of(session: Session, ad: Ad) -> Analysis:
    analysis = session.scalars(
        select(Analysis).where(Analysis.ad_id == ad.id).order_by(Analysis.created_at.desc())
    ).first()
    if analysis is None:  # pragma: no cover - a published ad always has its analysis
        raise VariantsNotReadyError("This game has no reading of its video.")
    return analysis


def copy_ad(session: Session, base: Ad, message: str, **fields: object) -> Ad:
    """A new ad that starts from ``base``'s reading of the video and its cut-outs, so only
    the game is made again (features 19 and 44)."""
    analysis = latest_analysis_of(session, base)
    ad = Ad(
        shop_id=base.shop_id,
        video_id=base.video_id,
        language=base.language,
        is_synthetic=base.is_synthetic,
        **fields,
    )
    session.add(ad)
    session.flush()
    session.add(
        Analysis(
            ad_id=ad.id,
            video_id=analysis.video_id,
            reading=analysis.reading,
            brief=analysis.brief,
            candidates=analysis.candidates,
            prompt_version=analysis.prompt_version,
        )
    )
    for sprite in session.scalars(select(Sprite).where(Sprite.ad_id == base.id)):
        session.add(Sprite(ad_id=ad.id, **{f: getattr(sprite, f) for f in SPRITE_FIELDS}))
    audit.record(
        session,
        actor="system",
        action="ad.created",
        subject_type="ad",
        subject_id=ad.id,
        data={"message": message, "video_id": str(base.video_id), "copy_of": str(base.id)},
    )
    return ad


def start_variants(session: Session, base: Ad) -> list[Ad]:
    """Versions B and C of a published ad, queued at the build step; existing ones are kept."""
    if base.variant != "A" or base.status != AdStatus.PUBLISHED:
        raise VariantsNotReadyError("Only a published game can get two more versions.")
    have = {ad.variant: ad for ad in group_of(session, base)}
    for version in VERSIONS:
        if version in have:
            continue
        ad = copy_ad(
            session,
            base,
            f"Version {version} of an A/B test; the director designs another game.",
            group_id=base.group_id,
            variant=version,
        )
        enqueue(session, STEP_JOB, {"ad_id": str(ad.id), "step": "build"})
        have[version] = ad
    base.ab_slug = base.ab_slug or unique_ab_slug(session)
    return [have[v] for v in ("A", *VERSIONS) if v in have]


# --- making sure a version differs (used by the build step) -------------------------------


def sibling_builds(session: Session, ad: Ad) -> list[Build]:
    """The latest build of every other version in this ad's test."""
    builds: list[Build] = []
    for other in group_of(session, ad):
        if other.id == ad.id:
            continue
        latest = session.scalars(
            select(Build).where(Build.ad_id == other.id).order_by(Build.number.desc())
        ).first()
        if latest is not None:
            builds.append(latest)
    return builds


def variant_note(ad: Ad, siblings: list[Build]) -> str:
    """What the director is told about the versions already made."""
    if ad.variant == "A" or not siblings:
        return "this is the first version."
    made = "; ".join(
        f"{b.template} with colours {b.config['palette']['primary']} and "
        f"{b.config['palette']['accent']}, button «{b.config['text']['ctaLabel']}»"
        for b in siblings
    )
    return (
        f"this is version {ad.variant} of an A/B test. Already made: {made}. Make a clearly "
        "different game: another template that suits the product, other colours from the "
        "palette, and other button words."
    )


def make_different(
    proposal: GameProposal,
    siblings: list[Build],
    brief: CreativeBrief,
    templates: dict[str, TemplateSpec],
) -> tuple[GameProposal, list[str]]:
    """Code's check that a version is not a copy: a template no other version uses (one made
    for this product first), and not the same pair of colours."""
    notes: list[str] = []
    used = {b.template for b in siblings}
    if proposal.template in used:
        usable = [
            spec
            for spec in buildable(templates).values()
            if spec.id not in used
            and ("quiz" not in spec.needs or len(clean_quiz(proposal.quiz, brief)) >= 3)
        ]
        usable.sort(key=lambda spec: brief.product.category not in spec.good_for)
        if usable:
            notes.append(
                f"another version already uses {proposal.template}; this one uses {usable[0].id}"
            )
            proposal = proposal.model_copy(update={"template": usable[0].id})

    def pair(primary: str | None, accent: str | None) -> tuple[str, str]:
        palette = brief.palette
        return primary or palette[0], accent or palette[1 % len(palette)]

    used_pairs = {pair(b.proposal.get("primary_color"), b.proposal.get("accent_color"))
                  for b in siblings}  # fmt: skip
    if pair(proposal.primary_color, proposal.accent_color) in used_pairs:
        options = [(a, b) for a in brief.palette for b in brief.palette if a != b]
        fresh = next((o for o in options if o not in used_pairs), None)
        if fresh:
            proposal = proposal.model_copy(
                update={"primary_color": fresh[0], "accent_color": fresh[1]}
            )
            notes.append(
                "the colours matched another version, so others from the palette were used"
            )
    return proposal, notes


def batch_note(session: Session, ad: Ad) -> str | None:
    """Feature 46: for the director, which templates the other games of this batch use, so
    a set of games for one shop feels varied. A note, not a rule."""
    video = session.get(Video, ad.video_id)
    if video is None or video.batch_id is None:
        return None
    used = sorted(
        {
            t
            for t in session.scalars(
                select(Ad.template)
                .join(Video, Video.id == Ad.video_id)
                .where(Video.batch_id == video.batch_id, Video.id != video.id)
            )
            if t
        }
    )
    total = session.scalar(select(Batch.items).where(Batch.id == video.batch_id)) or 0
    return (
        f"this game is one of a set of {total} for the same shop; the other games so far use: "
        f"{', '.join(used) or 'none yet'}. Choose a different template if one suits this "
        "product as well, so the set feels varied."
    )
