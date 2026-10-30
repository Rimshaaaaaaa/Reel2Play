"""Director step (features 4, 5, 8, 9, 10): read the video, pick key frames, save the brand kit.

Code takes the frame candidates and checks every answer; the director (Muse Spark Open)
reads the video, the speech, the owner's voice note and the candidates. What the owner typed
always wins, then what they said in their voice note, then what the video shows.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import cv2

from reel2play import brand
from reel2play.ai.media import media_part
from reel2play.ai.messages import Media, MediaKind
from reel2play.analysis import (
    OCCASION_NAMES,
    Box,
    CreativeBrief,
    Cta,
    KeyFrame,
    MoreProduct,
    VideoAnalysis,
    VoiceRead,
)
from reel2play.claims import only_owner_numbers
from reel2play.media.frames import (
    Candidate,
    dominant_colors,
    photo_candidates,
    video_candidates,
)
from reel2play.models import AdStatus, Analysis, VideoKind
from reel2play.pipeline.runner import PIPELINE, StepContext, StepFailedError
from reel2play.safety import (
    BLOCKED_MESSAGE,
    as_data,
    cash_prize_in,
    check_category,
    injection_in,
)

PROMPT = "director_analyze"
MAX_PALETTE = 5
SAFE_PRODUCT_NAME = "Our product"
GUARD_MESSAGE = "Text in the video tried to give instructions; it was treated as text and left out."
CASH_PRIZE_MESSAGE = (
    "The offer promises a cash prize; games give coupons only, so the offer was left out."
)


def frame_key(ctx: StepContext, index: int) -> str:
    return f"ads/{ctx.ad.id}/frames/candidate-{index}.jpg"


def _download(ctx: StepContext, key: str, workdir: Path) -> Path:
    path = workdir / Path(key).name
    path.write_bytes(ctx.storage.get(key))
    return path


def make_candidates(ctx: StepContext, workdir: Path) -> list[Candidate]:
    video = ctx.video
    if video.kind == VideoKind.PHOTOS:
        photos = [_download(ctx, key, workdir) for key in video.photo_keys]
        candidates = photo_candidates(photos, workdir)
    else:
        if not video.muted_key or video.duration_s is None:
            raise StepFailedError("the video was not prepared")
        source = _download(ctx, video.muted_key, workdir)
        candidates = video_candidates(source, video.duration_s, workdir)
    if not candidates:
        raise StepFailedError("no usable frames were found in the upload")
    for candidate in candidates:
        ctx.storage.put(frame_key(ctx, candidate.index), candidate.path.read_bytes(), "image/jpeg")
    return candidates


def director_media(ctx: StepContext, candidates: list[Candidate]) -> tuple[list[Media], str]:
    """The muted video, the speech track and the candidate frames, as model media parts."""
    parts: list[Media] = []
    names: list[str] = []
    video = ctx.video
    if video.muted_key:
        clip = media_part(ctx.storage, ctx.settings, video.muted_key, MediaKind.VIDEO, "video/mp4")
        if clip is not None:
            parts.append(clip)
            names.append("the video without sound")
    if video.audio_key:
        speech = media_part(
            ctx.storage, ctx.settings, video.audio_key, MediaKind.AUDIO, "audio/mpeg"
        )
        if speech is not None:
            parts.append(speech)
            names.append("the shop's speech track")
    if video.voice_key:
        voice = media_part(
            ctx.storage, ctx.settings, video.voice_key, MediaKind.AUDIO, "audio/mpeg"
        )
        if voice is not None:
            parts.append(voice)
            names.append("the owner's voice note")
    for candidate in candidates:
        key = frame_key(ctx, candidate.index)
        image = media_part(ctx.storage, ctx.settings, key, MediaKind.IMAGE, "image/jpeg")
        if image is not None:
            parts.append(image)
    names.append(f"{len(candidates)} candidate frames, in index order")
    return parts, "; ".join(names)


def _candidates_text(candidates: list[Candidate]) -> str:
    return "\n".join(
        f"- frame {c.index}: {c.time_s:.1f}s, sharpness {c.sharpness:.0f}" for c in candidates
    )


def pick_key_frames(
    ctx: StepContext, reading: VideoAnalysis, candidates: list[Candidate]
) -> list[KeyFrame]:
    """The director's valid picks, in order; the sharpest frame when none is usable."""
    by_index = {c.index: c for c in candidates}
    picks: list[KeyFrame] = []
    for pick in reading.key_frames:
        candidate = by_index.get(pick.index)
        if candidate is None or any(k.index == pick.index for k in picks):
            continue
        picks.append(
            KeyFrame(
                index=pick.index,
                time_s=candidate.time_s,
                key=frame_key(ctx, pick.index),
                reason=pick.reason,
                product_box=pick.product_box,
            )
        )
    if picks:
        return picks
    sharpest = max(candidates, key=lambda c: c.sharpness)
    return [
        KeyFrame(
            index=sharpest.index,
            time_s=sharpest.time_s,
            key=frame_key(ctx, sharpest.index),
            reason="The sharpest frame (the director's picks were not usable).",
        )
    ]


def pick_more_products(
    ctx: StepContext, reading: VideoAnalysis, candidates: list[Candidate]
) -> list[MoreProduct]:
    """Feature 11: the other products the director found, on frames that exist. A catalog of
    photos with no names from the director still gives one product per other photo."""
    by_index = {c.index: c for c in candidates}
    found: list[MoreProduct] = []
    for pick in reading.more_products:
        if pick.frame_index not in by_index:
            continue
        if injection_in(pick.name) or injection_in(pick.segment_prompt):
            ctx.say("safety", "guard.flagged", GUARD_MESSAGE, field="more_products")
            continue
        found.append(
            MoreProduct(
                name=pick.name.strip(),
                segment_prompt=pick.segment_prompt.strip(),
                key=frame_key(ctx, pick.frame_index),
                product_box=pick.product_box,
            )
        )
    if not found and ctx.video.catalog:
        main = reading.key_frames[0].index if reading.key_frames else None
        found = [
            MoreProduct(
                name=f"Product {number}",
                segment_prompt=reading.product.segment_prompt,
                key=frame_key(ctx, c.index),
            )
            for number, c in enumerate((c for c in candidates if c.index != main), start=2)
        ]
    return found[:3]


def merge_palette(model_colors: list[str], measured: list[str]) -> list[str]:
    palette: list[str] = []
    for color in [*model_colors, *measured]:
        if color not in palette:
            palette.append(color)
    return palette[:MAX_PALETTE]


VOICE_GUARD_MESSAGE = (
    "The voice note seemed to give instructions; it was treated as speech and left out."
)
VOICE_NUMBERS_MESSAGE = (
    "The offer from the voice note was left out: its numbers were not in what was heard."
)


def screen_voice(ctx: StepContext, reading: VideoAnalysis) -> VideoAnalysis:
    """The voice note follows the same rules as the video: no instructions, no cash prizes,
    and an offer only with numbers that were really said."""
    voice = reading.voice_note
    if voice is None:
        return reading
    if not ctx.video.voice_key:  # the director described a voice note nobody sent
        return reading.model_copy(update={"voice_note": None})
    if any(injection_in(text) for text in (voice.transcript, voice.offer, voice.audience)):
        ctx.say("safety", "guard.flagged", VOICE_GUARD_MESSAGE, field="voice_note")
        return reading.model_copy(update={"voice_note": None})
    if cash_prize_in(voice.offer):
        ctx.say("safety", "safety.offer_removed", CASH_PRIZE_MESSAGE, source="voice")
        voice = voice.model_copy(update={"offer": None})
    elif voice.offer and not only_owner_numbers(voice.offer, voice.transcript):
        ctx.say("director", "voice.offer_dropped", VOICE_NUMBERS_MESSAGE, offer=voice.offer)
        voice = voice.model_copy(update={"offer": None})
    return reading.model_copy(update={"voice_note": voice})


def screen(ctx: StepContext, reading: VideoAnalysis) -> VideoAnalysis:
    """Keep instructions hidden in the video, and cash prizes, out of the game (56, 58)."""
    reading = screen_voice(ctx, reading)
    product, offer = reading.product, reading.offer
    words = {k: getattr(reading, k) for k in ("mood", "audience", "tone_of_voice")}
    flagged_words = [k for k, v in words.items() if injection_in(v)]
    if flagged_words:
        reading = reading.model_copy(update=dict.fromkeys(flagged_words, ""))
        ctx.say("safety", "guard.flagged", GUARD_MESSAGE, field=", ".join(flagged_words))
    if injection_in(product.name) or injection_in(product.description):
        product = product.model_copy(update={"name": SAFE_PRODUCT_NAME, "description": ""})
        ctx.say("safety", "guard.flagged", GUARD_MESSAGE, field="product")
    if injection_in(offer.text):
        offer = offer.model_copy(update={"text": None, "source": "none"})
        ctx.say("safety", "guard.flagged", GUARD_MESSAGE, field="offer")
    elif cash_prize_in(offer.text):
        offer = offer.model_copy(update={"text": None, "source": "none"})
        ctx.say("safety", "safety.offer_removed", CASH_PRIZE_MESSAGE, source="video")
    return reading.model_copy(update={"product": product, "offer": offer})


def owner_offer(ctx: StepContext) -> str | None:
    offer = ctx.video.owner_offer
    if offer and cash_prize_in(offer):
        ctx.say("safety", "safety.offer_removed", CASH_PRIZE_MESSAGE, source="owner")
        return None
    return offer


def owner_product(ctx: StepContext) -> str | None:
    """Feature 46: the owner's name for the product, unless it tries to give instructions."""
    name = ctx.video.owner_product
    if name and injection_in(name):
        ctx.say(
            "safety",
            "safety.injection",
            "The product name looked like instructions, so the director's name is used instead.",
            source="owner",
        )
        return None
    return name


def blocked(ctx: StepContext, reading: VideoAnalysis) -> bool:
    """No games for alcohol, tobacco, weapons or adult products: the director or the words."""
    check = check_category(
        reading.restricted,
        [
            reading.product.name,
            reading.product.description,
            *reading.on_screen_text,
            *(p.name for p in reading.more_products),
            ctx.video.owner_offer,
            ctx.video.owner_product,
        ],
    )
    if check.blocked:
        ctx.ad.status = AdStatus.BLOCKED
        ctx.ad.error = BLOCKED_MESSAGE
        ctx.say(
            "safety",
            "safety.blocked",
            f"{BLOCKED_MESSAGE} This looks like {check.restricted.value} ({check.reason}).",
            restricted=check.restricted.value,
            found_by=check.reason,
        )
    return check.blocked


def choose_occasion(owner: str | None, voice: VoiceRead | None, reading: VideoAnalysis) -> str:
    """Feature 22: the owner's pick wins, then what they said, then what the video shows."""
    if owner and owner != "none":
        return owner
    if voice is not None and voice.occasion != "none":
        return voice.occasion
    return reading.occasion


def build_brief(
    ctx: StepContext,
    reading: VideoAnalysis,
    key_frames: list[KeyFrame],
    measured: list[str],
    logo_key: str | None,
    more_products: list[MoreProduct] | None = None,
) -> CreativeBrief:
    video, shop = ctx.video, ctx.shop
    from_owner = owner_offer(ctx)
    voice = reading.voice_note
    if from_owner:
        offer_text, offer_source = from_owner, "owner"
    elif voice is not None and voice.offer:
        offer_text, offer_source = voice.offer, "voice"
    elif reading.offer.source != "none" and reading.offer.text:
        offer_text, offer_source = reading.offer.text, reading.offer.source
    else:
        offer_text, offer_source = None, "none"
    language = shop.language if shop.language in ("ur", "en") else reading.language.recommended
    product = reading.product.model_dump()
    if name := owner_product(ctx):  # feature 46: the owner's own name for the product wins
        product["name"] = name
    return CreativeBrief.model_validate(
        {
            "product": product,
            "palette": merge_palette(reading.brand_colors, measured),
            "mood": reading.mood,
            "audience": (voice.audience if voice and voice.audience else reading.audience),
            "tone_of_voice": reading.tone_of_voice,
            "language": language,
            "price": video.owner_price,
            "offer_text": offer_text,
            "offer_source": offer_source,
            "cod_available": reading.offer.cod_available,
            "free_delivery": reading.offer.free_delivery,
            "seen_price": reading.offer.seen_price,
            "cta": Cta.model_validate({"kind": video.cta_kind, "target": video.cta_target}),
            "key_frames": key_frames,
            "logo_key": logo_key,
            "occasion": choose_occasion(video.owner_occasion, voice, reading),
            "more_products": more_products or [],
        }
    )


def crop_box(image_path: Path, box: Box, target: Path) -> bool:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return False
    x, y, w, h = box.to_pixels(image.shape[1], image.shape[0])
    crop = image[y : y + h, x : x + w]
    return crop.size > 0 and bool(cv2.imwrite(str(target), crop))


def save_logo(
    ctx: StepContext, reading: VideoAnalysis, candidates: list[Candidate], workdir: Path
) -> str | None:
    logo = reading.logo
    if not logo.present or logo.box is None or logo.frame_index is None:
        return None
    candidate = next((c for c in candidates if c.index == logo.frame_index), None)
    target = workdir / "logo.png"
    if candidate is None or not crop_box(candidate.path, logo.box, target):
        return None
    key = f"shops/{ctx.shop.id}/logo.png"
    ctx.storage.put(key, target.read_bytes(), "image/png")
    return key


def summary(brief: CreativeBrief) -> str:
    offer = f"offer '{brief.offer_text}' ({brief.offer_source})" if brief.offer_text else "no offer"
    lang = "Urdu" if brief.language == "ur" else "English"
    occasion = f"; for {OCCASION_NAMES[brief.occasion]}" if brief.occasion != "none" else ""
    more = (
        f" and {len(brief.more_products)} more ({', '.join(p.name for p in brief.more_products)})"
        if brief.more_products
        else ""
    )
    return (
        f"Found {brief.product.name}{more} ({brief.product.category.replace('_', ' ')}); "
        f"colours {', '.join(brief.palette)}; {offer}{occasion}; game in {lang}; "
        f"{len(brief.key_frames)} key frame(s)."
    )


@PIPELINE.add(
    "analyze",
    AdStatus.ANALYZING,
    "director",
    "The director is watching the video and reading its text and speech.",
)
def analyze(ctx: StepContext) -> None:
    kit = brand.current_kit(ctx.session, ctx.shop)
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        candidates = make_candidates(ctx, workdir)
        media, media_list = director_media(ctx, candidates)
        variables: dict[str, object] = {
            "shop_name": as_data(ctx.shop.name),
            "owner_price": as_data(ctx.video.owner_price),
            "owner_offer": as_data(ctx.video.owner_offer),
            "owner_product": as_data(
                None if injection_in(ctx.video.owner_product) else ctx.video.owner_product
            ),
            "owner_language": ctx.shop.language,
            "brand_kit": brand.describe(kit),
            "media_list": media_list,
            "candidates": _candidates_text(candidates),
            "voice_note": (
                f"yes, {ctx.video.voice_seconds or 0:.0f} seconds (the owner's voice note)"
                if ctx.video.voice_key
                else "none"
            ),
            "catalog": (
                "yes: each photo shows a different product; the main one first"
                if ctx.video.catalog
                else "no"
            ),
        }
        reading = ctx.ai.ask_json(
            PROMPT, variables, VideoAnalysis, media=media, subject=ctx.subject
        )
        if blocked(ctx, reading):
            return
        reading = screen(ctx, reading)
        key_frames = pick_key_frames(ctx, reading, candidates)
        first = next(c for c in candidates if c.index == key_frames[0].index)
        logo_key = save_logo(ctx, reading, candidates, workdir) or (kit.logo_key if kit else None)
        more = pick_more_products(ctx, reading, candidates)
        brief = build_brief(ctx, reading, key_frames, dominant_colors(first.path), logo_key, more)
    ctx.session.add(
        Analysis(
            ad_id=ctx.ad.id,
            video_id=ctx.video.id,
            reading=reading.model_dump(mode="json"),
            brief=brief.model_dump(mode="json"),
            candidates=[
                {"index": c.index, "time_s": c.time_s, "sharpness": c.sharpness} for c in candidates
            ],
            prompt_version=ctx.ai.prompt(PROMPT).version,
        )
    )
    brand.save_kit(ctx.session, ctx.shop, brief.palette, brief.tone_of_voice, logo_key)
    ctx.ad.language = brief.language
    ctx.say(
        "director",
        "analysis.done",
        summary(brief),
        product=brief.product.name,
        category=brief.product.category,
        palette=brief.palette,
        offer_source=brief.offer_source,
        key_frames=[k.index for k in key_frames],
        occasion=brief.occasion,
        voice_note_heard=reading.voice_note is not None,
    )
