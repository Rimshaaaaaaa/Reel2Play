"""Publish step (features 32 to 36): an ad that passed every check leaves in five forms.

1. The hosted game page, behind a short link with a link preview of the end card.
2. The gameplay Reel, recorded from an exact replay of the tester's winning run.
3. Captions and hashtags for Instagram, Facebook and WhatsApp Status.
4. For app developers, the Meta playable (one HTML file, and the same as a ZIP) with its
   lead-in video.
5. An A4 poster for the shop counter with the game's QR code, read back before it is saved.

Only the tested build is published, never a rebuilt one, and the replay is checked against
the tested run.
"""

from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from reel2play.builder.proposal import CUSTOM, GameProposal
from reel2play.db import utcnow
from reel2play.gates.thresholds import SCREENS
from reel2play.models import Ad, AdStatus, Build, Export, ExportKind, TestRun
from reel2play.pipeline.build import assemble_for, stored_config
from reel2play.pipeline.easier import (
    hold_for_owner,
    is_waiting_suggestion,
    link_slug,
    take_over_link,
)
from reel2play.pipeline.report import latest_test_run
from reel2play.pipeline.runner import PIPELINE, StepContext, StepFailedError
from reel2play.pipeline.state import latest_brief, latest_build
from reel2play.playtest.replay import Recording, record_run
from reel2play.playtest.session import Harness, harness_session
from reel2play.publish.captions import write_captions
from reel2play.publish.hosted import (
    analytics_tag,
    new_slug,
    page_link,
    preview_tags,
    with_preview,
)
from reel2play.publish.meta import (
    MetaCheck,
    MetaExportError,
    build_meta_html,
    check_playable,
    meta_config,
    zip_playable,
)
from reel2play.publish.poster import Poster, PosterFacts, facts_from, make_poster
from reel2play.publish.poster import preview as poster_preview
from reel2play.publish.reel import (
    ShapedPage,
    cut_lead_in,
    encode,
    frame_reel,
    preview_image,
    timeline,
)

FILE_NAMES = {
    ExportKind.HOSTED: ("game.html", "text/html; charset=utf-8"),
    ExportKind.PREVIEW: ("preview.jpg", "image/jpeg"),
    ExportKind.REEL: ("reel.mp4", "video/mp4"),
    ExportKind.LEAD_IN: ("lead-in.mp4", "video/mp4"),
    ExportKind.META_HTML: ("playable.html", "text/html; charset=utf-8"),
    ExportKind.META_ZIP: ("playable.zip", "application/zip"),
    ExportKind.REEL_SQUARE: ("reel-square.mp4", "video/mp4"),
    ExportKind.REEL_WIDE: ("reel-wide.mp4", "video/mp4"),
    ExportKind.POSTER: ("poster.pdf", "application/pdf"),
    ExportKind.POSTER_PREVIEW: ("poster.jpg", "image/jpeg"),
}
# Public files can be fetched by WhatsApp, Instagram and link-preview crawlers.
PUBLIC = {ExportKind.PREVIEW, ExportKind.REEL, ExportKind.REEL_SQUARE, ExportKind.REEL_WIDE}
SHAPED_REELS = {"square": ExportKind.REEL_SQUARE, "landscape": ExportKind.REEL_WIDE}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unique_slug(ctx: StepContext) -> str:
    while True:
        slug = new_slug()
        if ctx.session.scalar(select(Ad.id).where(Ad.slug == slug)) is None:
            return slug


def winning_run(run: TestRun) -> int:
    return next((r["index"] for r in run.runs if r["won"]), 0)


def save_export(ctx: StepContext, kind: ExportKind, data: bytes, **details: object) -> Export:
    """Store one output, replacing an earlier one of the same kind (a retried publish)."""
    name, content_type = FILE_NAMES[kind]
    key = f"ads/{ctx.ad.id}/publish/{name}"
    public = kind in PUBLIC
    ctx.storage.put(key, data, content_type, public=public)
    export = ctx.session.scalars(
        select(Export).where(Export.ad_id == ctx.ad.id, Export.kind == kind)
    ).first() or Export(ad_id=ctx.ad.id, kind=kind)
    export.key = key
    export.public = public
    export.content_type = content_type
    export.size_bytes = len(data)
    export.details = dict(details)
    ctx.session.add(export)
    return export


def tested_build(ctx: StepContext) -> tuple[TestRun, Build]:
    run = latest_test_run(ctx)
    build = latest_build(ctx)
    if run is None or build is None or not run.passed or run.build_id != build.id:
        raise StepFailedError("only a game that passed every check is published")
    if not run.replays:
        raise StepFailedError("the passing test has no replay to record the Reel from")
    return run, build


def shaped_pages(harness: Harness, page: bytes, scale: float) -> list[ShapedPage]:
    """Feature 18: the square and landscape pages, and where the game sits in each."""
    pages: list[ShapedPage] = []
    for shape in SHAPED_REELS:
        width, height = SCREENS[shape]
        harness.call("open", html_b64=b64(page), width=width, height=height, scale=scale,
                     layout=shape)  # fmt: skip
        picture = base64.b64decode(harness.call("screenshot")["png_b64"])
        stage = harness.call("end_card")["stage"]
        pages.append(
            ShapedPage(
                shape,
                picture,
                round(stage["x"] * scale),
                round(stage["y"] * scale),
                round(stage["width"] * scale),
                round(stage["height"] * scale),
            )
        )
    return pages


@dataclass(frozen=True)
class Recorded:
    recording: Recording
    meta: MetaCheck
    pages: list[ShapedPage]
    poster: Poster


def record_and_check(
    ctx: StepContext, run: TestRun, page: bytes, meta_html: bytes, poster: PosterFacts
) -> Recorded:
    with harness_session(ctx.settings) as harness:
        recording = record_run(
            harness,
            b64(page),
            run.replays,
            winning_run(run),
            fps=ctx.settings.reel_fps,
            scale=ctx.settings.reel_scale,
        )
        meta = check_playable(harness, b64(meta_html))
        pages = shaped_pages(harness, page, ctx.settings.reel_scale)
        return Recorded(recording, meta, pages, make_poster(harness, poster))


def publish_reel(
    ctx: StepContext, run: TestRun, recording: Recording, pages: list[ShapedPage] | None = None
) -> float:
    tested = run.runs[winning_run(run)]
    exact = recording.won == tested["won"] and abs(recording.seconds - tested["seconds"]) < 0.05
    shots = timeline(recording)
    seconds = round(sum(shot.seconds for shot in shots), 1)
    with tempfile.TemporaryDirectory(prefix="r2p-publish-") as tmp:
        reel, lead_in = Path(tmp) / "reel.mp4", Path(tmp) / "lead-in.mp4"
        encode(shots, reel)
        cut_lead_in(reel, lead_in)
        save_export(
            ctx,
            ExportKind.REEL,
            reel.read_bytes(),
            seconds=seconds,
            run=tested["index"] + 1,
            exact_replay=exact,
        )
        save_export(ctx, ExportKind.LEAD_IN, lead_in.read_bytes())
        for shaped in pages or []:
            framed = Path(tmp) / f"reel-{shaped.shape}.mp4"
            frame_reel(reel, shaped, framed)
            save_export(ctx, SHAPED_REELS[shaped.shape], framed.read_bytes(), seconds=seconds)
    ctx.say(
        "publisher",
        "publish.reel",
        f"Recorded a {seconds:.0f}-second gameplay Reel from run {tested['index'] + 1}"
        + (" (an exact replay)." if exact else " (the replay differed slightly from the test)."),
        seconds=seconds,
        exact_replay=exact,
    )
    return seconds


def publish_meta(ctx: StepContext, meta_html: bytes, check: MetaCheck) -> None:
    if ctx.ad.template == CUSTOM:  # feature 24: Meta reviews fixed games; this one is new
        ctx.say(
            "publisher",
            "publish.meta_skipped",
            "No Meta playable for an experimental mechanic; the game page, Reel and poster "
            "are ready.",
            problems=["experimental mechanic"],
        )
        return
    if check.problems:
        ctx.say(
            "publisher",
            "publish.meta_skipped",
            "No Meta playable this time: " + "; ".join(check.problems) + ".",
            problems=check.problems,
        )
        return
    save_export(ctx, ExportKind.META_HTML, meta_html, cta_calls=check.cta_calls)
    save_export(ctx, ExportKind.META_ZIP, zip_playable(meta_html))
    ctx.say(
        "publisher",
        "publish.meta",
        f"Meta playable ready for app developers: {len(meta_html) / 1024:.0f} KB, the button "
        "calls FbPlayableAd.onCTAClick(), no links or network calls, with a lead-in video.",
        size_bytes=len(meta_html),
    )


def publish_poster(ctx: StepContext, poster: Poster) -> None:
    """Feature 36: the counter poster, only when its QR code reads back as the game link."""
    if poster.problems:
        ctx.say(
            "publisher",
            "publish.poster_skipped",
            "No counter poster this time: " + "; ".join(poster.problems) + ".",
            problems=poster.problems,
        )
        return
    save_export(ctx, ExportKind.POSTER, poster.pdf, pages=poster.pages, qr=poster.read_back)
    save_export(ctx, ExportKind.POSTER_PREVIEW, poster_preview(poster.png))
    ctx.say(
        "publisher",
        "publish.poster",
        "Counter poster ready: an A4 PDF whose QR code was scanned back and opens the game.",
        size_bytes=len(poster.pdf),
    )


@PIPELINE.add(
    "publish",
    AdStatus.PUBLISHING,
    "publisher",
    "The publisher is making the game page, the gameplay Reel and the captions.",
)
def publish(ctx: StepContext) -> None:
    run, build = tested_build(ctx)
    ad = ctx.ad
    if is_waiting_suggestion(ad):  # feature 44: the owner decides first
        hold_for_owner(ctx)
        return
    brief = latest_brief(ctx)
    taking_over = link_slug(ctx)
    if taking_over is None:
        ad.slug = ad.slug or unique_slug(ctx)
    link = page_link(ctx.settings.share_base, taking_over or ad.slug or "")
    page = ctx.storage.get(build.html_key)
    config = assemble_for(ctx, brief, GameProposal.model_validate(build.proposal)).config
    if stored_config(config) != build.config:
        raise StepFailedError("the game could not be rebuilt exactly as tested for Meta")
    try:
        meta_html = build_meta_html(meta_config(config), ctx.settings)
    except MetaExportError as exc:
        raise StepFailedError(str(exc)) from exc
    poster = facts_from(
        build.config,
        shop_name=ctx.shop.name,
        link=link,
        product_image=config.assets.product,
        synthetic=ad.is_synthetic,
    )
    recorded = record_and_check(ctx, run, page, meta_html, poster)
    recording = recorded.recording

    text = build.config["text"]
    preview = save_export(ctx, ExportKind.PREVIEW, preview_image(recording.end.jpeg))
    api = ctx.settings.api_base_url.rstrip("/")
    events = f"{api}/api/events"
    coupons = f"{api}/api/coupons" if ctx.settings.unique_coupons else None
    tags = preview_tags(
        title=f"{ctx.shop.name}: {text['title']}",
        description=". ".join(p for p in (brief.offer_text, brief.price) if p)
        or text["instruction"],
        image_url=ctx.storage.public_url(preview.key),
        page_url=link,
    )
    tags += "\n" + analytics_tag(events, str(ad.id), ad.variant, coupons)
    save_export(ctx, ExportKind.HOSTED, with_preview(page, tags), build=build.number)
    ctx.say("publisher", "publish.page", f"Game page ready: {link}", link=link)

    publish_reel(ctx, run, recording, recorded.pages)
    publish_meta(ctx, meta_html, recorded.meta)
    publish_poster(ctx, recorded.poster)

    captions = write_captions(
        ctx.ai, ctx.subject, shop_name=ctx.shop.name, brief=brief, game_text=text, link=link
    )
    ad.captions = captions.as_json()
    ctx.say(
        "publisher",
        "publish.captions",
        "Captions written for Instagram, Facebook and WhatsApp Status"
        + ("." if captions.written_by == "model" else ", from your own facts only."),
        written_by=captions.written_by,
    )
    take_over_link(ctx)
    ad.status = AdStatus.PUBLISHED
    ad.published_at = utcnow()
    ctx.say("publisher", "publish.done", f"Published. Share {link} with your customers.")
