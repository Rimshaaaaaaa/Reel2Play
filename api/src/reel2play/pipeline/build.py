"""Build step (features 12, 14 to 17, 20, 21): the director designs, the builder compiles.

The director proposes a template, difficulty, colours and the game's words; code checks
the proposal, assembles the config, and compiles one self-contained HTML file within the
size budget. Fix rounds (the tester's step) pass a revised proposal back through here.
"""

from __future__ import annotations

import zlib
from typing import Any

from reel2play.ai.media import media_part
from reel2play.ai.messages import Media, MediaKind
from reel2play.analysis import LANGUAGE_NAMES, OCCASION_NAMES, CreativeBrief
from reel2play.brand_memory import BrandMemory, remember
from reel2play.builder.assets import (
    logo_data_url,
    photo_data_url,
    plain_photo_data_url,
    sprite_data_url,
    strip_data_url,
)
from reel2play.builder.config import GameConfig, MoreProductAsset, ProductFrames
from reel2play.builder.html import BudgetExceededError, compile_game
from reel2play.builder.mechanic import check_script
from reel2play.builder.proposal import CUSTOM, Assembly, AssetInputs, GameProposal, assemble
from reel2play.builder.templates import TemplateSpec, buildable, load_templates
from reel2play.cutout.faces import FaceState
from reel2play.models import AdStatus, Build
from reel2play.pipeline.runner import PIPELINE, StepContext, StepFailedError
from reel2play.pipeline.state import best_sprite, latest_brief, more_sprites, next_build_number
from reel2play.pipeline.variants import batch_note, make_different, sibling_builds, variant_note
from reel2play.safety import as_data

PROMPT = "director_game"
MECHANIC_PROMPT = "director_mechanic"
MORE_SIDE = 240  # other products are drawn smaller than the main one


def proposal_variables(
    ctx: StepContext,
    brief: CreativeBrief,
    templates: dict[str, TemplateSpec],
    version: str = "this is the first version.",
    memory: BrandMemory | None = None,
) -> dict[str, object]:
    return {
        "version": version,
        "shop_name": as_data(ctx.shop.name),
        "product": as_data(brief.product.name),
        "category": brief.product.category.replace("_", " "),
        "description": as_data(brief.product.description),
        "audience": as_data(brief.audience),
        "mood": as_data(brief.mood),
        "tone": as_data(brief.tone_of_voice),
        "palette": ", ".join(brief.palette),
        "offer": as_data(brief.offer_text),
        "price": as_data(brief.price),
        "language_name": LANGUAGE_NAMES[brief.language],
        "occasion": OCCASION_NAMES.get(brief.occasion, "none"),
        "catalog": "\n".join(spec.catalog_line() for spec in buildable(templates).values()),
        "brand_memory": (memory or BrandMemory()).for_director(),
    }


def game_assets(ctx: StepContext, brief: CreativeBrief) -> AssetInputs:
    sprite = best_sprite(ctx)
    frame = next((k for k in brief.key_frames if k.key == sprite.source_frame_key), None)
    return AssetInputs(
        product=sprite_data_url(ctx.storage.get(sprite.sprite_key)),
        product_photo=plain_photo_data_url(ctx.storage.get(sprite.sprite_key), brief.palette[0])
        if sprite.face_check == FaceState.UNCHECKED
        else photo_data_url(
            ctx.storage.get(sprite.source_frame_key), frame.product_box if frame else None
        ),
        logo=logo_data_url(ctx.storage.get(brief.logo_key)) if brief.logo_key else None,
        product_frames=ProductFrames(
            strip=strip_data_url(ctx.storage.get(sprite.track_key)),
            frames=sprite.track_frames,
            fps=sprite.track_fps or 6.0,
        )
        if sprite.track_key and sprite.track_frames >= 2
        else None,
        more_products=tuple(
            MoreProductAsset(
                image=sprite_data_url(ctx.storage.get(more.sprite_key), MORE_SIDE),
                name=brief.more_products[more.product_index - 1].name[:40],
            )
            for more in more_sprites(ctx)
            if more.product_index <= len(brief.more_products)
        ),
    )


def assemble_for(ctx: StepContext, brief: CreativeBrief, proposal: GameProposal) -> Assembly:
    """The game config for this ad and proposal; the same inputs always give the same config."""
    return assemble(
        ad_id=ctx.ad.id,
        shop_name=ctx.shop.name,
        brief=brief,
        proposal=proposal,
        templates=load_templates(ctx.settings.templates_dir),
        assets=game_assets(ctx, brief),
        seed=zlib.crc32(ctx.ad.id.bytes) & 0x7FFFFFFF,
    )


def stored_config(config: GameConfig) -> dict[str, Any]:
    """The config as kept in the database: everything but the inlined images."""
    return config.model_dump(by_alias=True, mode="json", exclude={"assets"})


def compile_and_store(ctx: StepContext, brief: CreativeBrief, proposal: GameProposal) -> Build:
    """Assemble, compile and save one build. Shared by the first build and every fix round."""
    assembly = assemble_for(ctx, brief, proposal)
    try:
        built = compile_game(
            assembly.config, ctx.settings.engine_dist_dir, ctx.settings.max_game_bytes
        )
    except BudgetExceededError as exc:
        raise StepFailedError(str(exc)) from exc
    number = next_build_number(ctx)
    key = f"ads/{ctx.ad.id}/builds/{number}.html"
    ctx.storage.put(key, built.html, "text/html; charset=utf-8")
    kept = stored_config(assembly.config)
    build = Build(
        ad_id=ctx.ad.id,
        number=number,
        template=assembly.template.id,
        proposal=proposal.model_dump(mode="json"),
        config=kept,
        html_key=key,
        size_bytes=built.size,
        sha256=built.sha256,
    )
    ctx.session.add(build)
    ctx.ad.template = assembly.template.id
    ctx.ad.config = kept
    for note in assembly.notes:
        ctx.say("builder", "build.corrected", f"Code corrected the proposal: {note}.", note=note)
    ctx.say(
        "builder",
        "build.done",
        f"Built the {assembly.template.name.lower()} game (build {number}, "
        f"{built.size / 1024:.0f} KB of the 2 MB budget).",
        build=number,
        template=assembly.template.id,
        size_bytes=built.size,
        sha256=built.sha256,
    )
    return build


def invent_mechanic(
    ctx: StepContext,
    brief: CreativeBrief,
    templates: dict[str, TemplateSpec],
    image: Media | None,
) -> GameProposal | None:
    """Feature 24: the director writes a new mechanic; code checks the script. A script that
    may not run is set aside, and the director designs from the fixed templates instead."""
    if CUSTOM not in templates or ctx.ad.variant != "A":
        return None
    proposal = ctx.ai.ask_json(
        MECHANIC_PROMPT,
        {**proposal_variables(ctx, brief, templates), "template": CUSTOM},
        GameProposal,
        media=[image] if image else [],
        subject=ctx.subject,
    )
    problems = check_script(proposal.mechanic or "")
    if problems:
        ctx.say(
            "builder",
            "mechanic.refused",
            "The new mechanic's script may not run (" + "; ".join(problems[:3]) + "), so the "
            "director designs from the tested templates instead.",
            problems=problems,
        )
        return None
    ctx.say(
        "builder",
        "mechanic.checked",
        "The director wrote a new mechanic; code checked its script (no globals, network or "
        "eval). The play-tester plays it next, in the sandbox.",
        characters=len(proposal.mechanic or ""),
    )
    return proposal.model_copy(update={"template": CUSTOM})


@PIPELINE.add("build", AdStatus.BUILDING, "director", "The director is designing the game.")
def build(ctx: StepContext) -> None:
    brief = latest_brief(ctx)
    templates = load_templates(ctx.settings.templates_dir)
    sprite = best_sprite(ctx)
    image = media_part(ctx.storage, ctx.settings, sprite.sprite_key, MediaKind.IMAGE, "image/png")
    siblings = sibling_builds(ctx.session, ctx.ad) if ctx.ad.variant != "A" else []
    note = variant_note(ctx.ad, siblings)
    if ctx.ad.variant == "A" and (in_set := batch_note(ctx.session, ctx.ad)):
        note = in_set
    memory = remember(ctx.session, ctx.shop, exclude=ctx.ad.id)
    proposal = (ctx.video.lab and invent_mechanic(ctx, brief, templates, image)) or None
    if proposal is None:
        proposal = ctx.ai.ask_json(
            PROMPT,
            proposal_variables(ctx, brief, templates, note, memory),
            GameProposal,
            media=[image] if image else [],
            subject=ctx.subject,
        )
    # Feature 19: a later version of an A/B test must be a different game, which code checks.
    proposal, differences = make_different(proposal, siblings, brief, templates)
    for note in differences:
        ctx.say("builder", "variant.changed", f"Code made this version different: {note}.")
    if memory.records:
        ctx.say(
            "director",
            "memory.used",
            "Looked at what worked for this shop before: " + "; ".join(memory.lines()) + ".",
            best=memory.best.template if memory.best else None,
        )
    ctx.say(
        "director",
        "game.designed",
        f"Chose the {proposal.template} template at {proposal.difficulty} difficulty: "
        f"{proposal.reason}",
        template=proposal.template,
        difficulty=proposal.difficulty,
    )
    compile_and_store(ctx, brief, proposal)
