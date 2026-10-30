"""Cut-out step (features 6 and 7): one clean product sprite per key frame, and for videos a
short animation of the best one, followed through the frames around it."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from reel2play.analysis import CreativeBrief, ProductCategory
from reel2play.cutout.cut import CutoutError, CutResult, cut_product
from reel2play.cutout.faces import FaceState, check_faces
from reel2play.cutout.segmenter import (
    Segmenter,
    Tracker,
    build_face_finder,
    build_segmenter,
    build_tracker,
)
from reel2play.cutout.track import (
    TRACK_FRAMES,
    Track,
    TrackSkippedError,
    clip_window,
    decode_mask_png,
    extract_clip,
    track_product,
)
from reel2play.models import AdStatus, Sprite, VideoKind
from reel2play.net import ExternalServiceError
from reel2play.pipeline.runner import PIPELINE, StepContext, StepFailedError
from reel2play.pipeline.state import latest_brief
from reel2play.settings import Settings


@dataclass
class SegmenterFactory:
    """Builds the segmenter from settings; tests replace ``build``."""

    build: Callable[[Settings], Segmenter | None] = field(default=build_segmenter)


SEGMENTER = SegmenterFactory()


@dataclass
class TrackerFactory:
    """Builds the tracker from settings; tests replace ``build``."""

    build: Callable[[Settings], Tracker | None] = field(default=build_tracker)


TRACKER = TrackerFactory()


@dataclass
class FaceFinderFactory:
    """Builds SAM 3.1's face finder from settings (feature 55); tests replace ``build``."""

    build: Callable[[Settings], Segmenter | None] = field(default=build_face_finder)


FACES = FaceFinderFactory()
log = logging.getLogger(__name__)


def save_sprite(
    ctx: StepContext, result: CutResult, frame_key: str, name: str, rank: int, product_index: int
) -> Sprite:
    base = f"ads/{ctx.ad.id}/sprites/{name}"
    ctx.storage.put(f"{base}-sprite.png", result.sprite_png, "image/png")
    ctx.storage.put(f"{base}-mask.png", result.mask_png, "image/png")
    sprite = Sprite(
        ad_id=ctx.ad.id,
        source_frame_key=frame_key,
        mask_key=f"{base}-mask.png",
        sprite_key=f"{base}-sprite.png",
        method=result.method,
        quality=result.quality,
        score=result.score,
        width=result.width,
        height=result.height,
        area_fraction=round(result.area_fraction, 4),
        rank=rank,
        product_index=product_index,
    )
    ctx.session.add(sprite)
    return sprite


def cut_more_products(
    ctx: StepContext, brief: CreativeBrief, segmenter: Segmenter | None
) -> list[str]:
    """Feature 11: one sprite for each other product; one that will not cut out is skipped."""
    made: list[str] = []
    for number, product in enumerate(brief.more_products, start=1):
        try:
            result = cut_product(
                ctx.storage.get(product.key), product.segment_prompt, product.product_box, segmenter
            )
        except CutoutError:
            continue
        save_sprite(ctx, result, product.key, f"more-{number}", 0, number)
        made.append(product.name)
    return made


@PIPELINE.add(
    "cutout", AdStatus.CUTTING_OUT, "cutout", "Cutting the product out of the key frames."
)
def cutout(ctx: StepContext) -> None:
    brief = latest_brief(ctx)
    segmenter = SEGMENTER.build(ctx.settings)
    made: list[Sprite] = []
    problems: list[str] = []
    for rank, frame in enumerate(brief.key_frames):
        try:
            result = cut_product(
                ctx.storage.get(frame.key),
                brief.product.segment_prompt,
                frame.product_box,
                segmenter,
            )
        except CutoutError as exc:
            problems.append(f"frame {frame.index}: {exc}")
            continue
        made.append(save_sprite(ctx, result, frame.key, str(rank), rank, 0))
    if not made:
        raise StepFailedError("the product could not be cut out: " + "; ".join(problems))
    best = min(made, key=lambda s: (s.quality != "good", s.rank))
    how = "SAM 3.1" if best.method != "grabcut" else "the fallback cut-out (lower quality)"
    more = cut_more_products(ctx, brief, segmenter)
    also = f", and {len(more)} more product(s): {', '.join(more)}" if more else ""
    ctx.say(
        "cutout",
        "cutout.done",
        f"Cut out {len(made)} sprite(s) of the {brief.product.segment_prompt} with {how}{also}.",
        sprites=[s.sprite_key for s in made],
        method=best.method,
        quality=best.quality,
        skipped=problems,
        more_products=len(more),
    )
    blur_bystanders(ctx, brief, segmenter)
    animate(ctx, brief, best)


def blur_bystanders(ctx: StepContext, brief: CreativeBrief, segmenter: Segmenter | None) -> None:
    """Feature 55: find faces in every frame a sprite came from, and blur the bystanders'."""
    sprites = list(ctx.session.scalars(select(Sprite).where(Sprite.ad_id == ctx.ad.id)))
    finder = FACES.build(ctx.settings)
    if finder is None:
        for sprite in sprites:
            sprite.face_check = FaceState.UNCHECKED
        ctx.say(
            "safety",
            "faces.unchecked",
            "Faces could not be checked here (SAM 3.1 is not connected), so the game shows the "
            "product cut-out on a plain background, never a frame of the video.",
        )
        return
    keep = brief.product.category == ProductCategory.COSMETICS
    blurred = kept = 0
    by_frame: dict[str, list[Sprite]] = {}
    for sprite in sprites:
        by_frame.setdefault(sprite.source_frame_key, []).append(sprite)
    for frame_key, group in by_frame.items():
        mask = decode_mask_png(ctx.storage.get(group[0].mask_key))
        try:
            check = check_faces(ctx.storage.get(frame_key), mask, finder, keep)
        except (ExternalServiceError, ValueError) as exc:
            log.warning("faces could not be checked in %s: %s", frame_key, exc)
            for sprite in group:
                sprite.face_check = FaceState.UNCHECKED
            continue
        blurred, kept = blurred + check.blurred, kept + check.kept
        if check.blurred:
            ctx.storage.put(frame_key, check.frame_jpeg, "image/jpeg")
            if check.touches_product:
                recut(ctx, brief, group, check.frame_jpeg, segmenter)
        for sprite in group:
            sprite.face_check = FaceState.BLURRED if check.blurred else FaceState.CLEAR
    unchecked = sum(1 for s in sprites if s.face_check == FaceState.UNCHECKED)
    ctx.say(
        "safety",
        "faces.checked",
        (f"Blurred {blurred} bystander face(s) in the key frames." if blurred
         else "No bystanders' faces in the key frames.")
        + (f" Kept {kept} face(s) that show the product." if kept else "")
        + (" Some frames could not be checked; the game will not show them." if unchecked else ""),
        blurred=blurred,
        kept=kept,
        unchecked=unchecked,
    )  # fmt: skip


def recut(
    ctx: StepContext,
    brief: CreativeBrief,
    group: list[Sprite],
    frame_jpeg: bytes,
    segmenter: Segmenter | None,
) -> None:
    """A blurred face overlapped the cut-out: cut the product again from the blurred frame."""
    for sprite in group:
        prompt = brief.product.segment_prompt
        box = next(
            (k.product_box for k in brief.key_frames if k.key == sprite.source_frame_key), None
        )
        try:
            result = cut_product(frame_jpeg, prompt, box, segmenter)
        except CutoutError:
            continue
        ctx.storage.put(sprite.sprite_key, result.sprite_png, "image/png")
        ctx.storage.put(sprite.mask_key, result.mask_png, "image/png")
    ctx.say(
        "cutout",
        "cutout.recut",
        "A blurred face touched the product, so it was cut out again from the blurred frame.",
    )


def follow_product(ctx: StepContext, brief: CreativeBrief, best: Sprite) -> tuple[Track, int]:
    """Cut the clip around the best key frame and follow the product through it."""
    video = ctx.video
    frame = next(k for k in brief.key_frames if k.key == best.source_frame_key)
    key_mask = decode_mask_png(ctx.storage.get(best.mask_key))
    prompt = brief.product.segment_prompt
    with tempfile.TemporaryDirectory(prefix="r2p-track-") as tmp:
        workdir = Path(tmp)
        source = workdir / "video.mp4"
        source.write_bytes(ctx.storage.get(str(video.muted_key)))
        start, length = clip_window(frame.time_s, float(video.duration_s or 0))
        clip = extract_clip(source, start, length, workdir)
    key_index = min(len(clip) - 1, round((frame.time_s - start) / length * TRACK_FRAMES))
    tracker = TRACKER.build(ctx.settings)
    try:
        return track_product(clip, key_index, key_mask, prompt, tracker, length), len(clip)
    except ExternalServiceError as exc:
        log.warning("SAM 3.1 tracking failed, following the product in code: %s", exc)
        return track_product(clip, key_index, key_mask, prompt, None, length), len(clip)


def animate(ctx: StepContext, brief: CreativeBrief, best: Sprite) -> None:
    """Feature 7: an animated sprite when the video shows the product turning or changing."""
    video = ctx.video
    has_frame = any(k.key == best.source_frame_key for k in brief.key_frames)
    if (
        video.kind != VideoKind.VIDEO
        or not video.muted_key
        or not video.duration_s
        or not has_frame
    ):
        return
    try:
        track, clip_frames = follow_product(ctx, brief, best)
    except (TrackSkippedError, subprocess.SubprocessError, OSError) as exc:
        reason = str(exc) if isinstance(exc, TrackSkippedError) else "the clip could not be read"
        ctx.say("cutout", "track.skipped", f"The sprite stays still: {reason}.", reason=reason)
        return
    key = f"ads/{ctx.ad.id}/sprites/track-strip.png"
    ctx.storage.put(key, track.strip_png, "image/png")
    best.track_key, best.track_frames = key, track.frames
    best.track_fps, best.track_method = track.fps, track.method
    how = "SAM 3.1" if track.quality == "good" else "code (lower quality)"
    ctx.say(
        "cutout",
        "track.done",
        f"Followed the {brief.product.segment_prompt} through {track.frames} of {clip_frames} "
        f"frames with {how}, so it moves in the game.",
        frames=track.frames,
        fps=track.fps,
        method=track.method,
        quality=track.quality,
    )
