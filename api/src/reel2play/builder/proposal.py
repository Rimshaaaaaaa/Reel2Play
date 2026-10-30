"""The director's game proposal (features 14, 16, 20) and how code turns it into a config.

The model proposes; code decides: unknown templates fall back to the one made for the
product, colours must come from the brand palette, the offer may not change its numbers,
and the price is always the owner's.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from reel2play.analysis import HEX_COLOR, CreativeBrief
from reel2play.builder.config import (
    Assets,
    Content,
    GameConfig,
    GameText,
    MoreProductAsset,
    ProductFrames,
    QuizItem,
)
from reel2play.builder.cta import build_cta, coupon_code, order_message
from reel2play.builder.mechanic import check_script
from reel2play.builder.templates import TemplateSpec, Tier, buildable, default_for
from reel2play.builder.theme import build_palette
from reel2play.claims import only_owner_numbers
from reel2play.safety import injection_in

CUSTOM = "custom"
_URDU = re.compile(r"[؀-ۿ]")


class QuizProposal(BaseModel):
    question: str = Field(min_length=1, max_length=90)
    options: list[str] = Field(min_length=3, max_length=3)
    answer: int = Field(ge=0, le=2, description="Index of the right option")


class GameProposal(BaseModel):
    """What the director proposes for the game. All words in the game's language."""

    template: str = Field(max_length=30)
    reason: str = Field(max_length=200)
    difficulty: Tier = Tier.NORMAL
    title: str = Field(min_length=1, max_length=30)
    instruction: str = Field(min_length=1, max_length=80)
    win_text: str = Field(min_length=1, max_length=50)
    lose_text: str = Field(min_length=1, max_length=50)
    cta_label: str = Field(min_length=1, max_length=28)
    product_label: str = Field(min_length=1, max_length=32)
    offer_line: str | None = Field(default=None, max_length=60)
    primary_color: str | None = Field(default=None, pattern=HEX_COLOR)
    accent_color: str | None = Field(default=None, pattern=HEX_COLOR)
    difficulty_overrides: dict[str, float] = Field(
        default_factory=dict, description="Only used by fix rounds; clamped to template ranges"
    )
    facts: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="Tap to reveal: short facts about the product from the video",
    )
    quiz: list[QuizProposal] = Field(
        default_factory=list, max_length=3, description="Quiz: three questions the video answers"
    )
    mechanic: str | None = Field(
        default=None,
        max_length=6000,
        description="Only for an experimental game: the new mechanic's script",
    )


@dataclass
class Assembly:
    config: GameConfig
    template: TemplateSpec
    notes: list[str] = field(default_factory=list)


QUIZ_QUESTIONS = 3
FACT_CHARS = 40


def honest_words(text: str, brief: CreativeBrief) -> bool:
    """Words for the game: no instructions, and no numbers the owner did not give."""
    return not injection_in(text) and only_owner_numbers(text, brief.price, brief.offer_text)


def clean_facts(facts: list[str], brief: CreativeBrief) -> list[str]:
    kept: list[str] = []
    for fact in facts:
        words = fact.strip()
        if words and len(words) <= FACT_CHARS and honest_words(words, brief) and words not in kept:
            kept.append(words)
    return kept


def brief_facts(brief: CreativeBrief, product_label: str) -> list[str]:
    """Facts code can state on its own, from what the owner gave and the video showed."""
    facts = [product_label, brief.offer_text, brief.price]
    if brief.cod_available:
        facts.append("Cash on delivery" if brief.language == "en" else "کیش آن ڈیلیوری")
    if brief.free_delivery:
        facts.append("Free delivery" if brief.language == "en" else "مفت ڈیلیوری")
    return [f[:FACT_CHARS] for f in facts if f]


def clean_quiz(quiz: list[QuizProposal], brief: CreativeBrief) -> list[QuizItem]:
    kept: list[QuizItem] = []
    for item in quiz:
        options = [o.strip()[:28] for o in item.options]
        texts = [item.question, *options]
        if len({o.casefold() for o in options}) < len(options) or not all(options):
            continue
        if all(honest_words(t, brief) for t in texts):
            kept.append(
                QuizItem(question=item.question.strip(), options=options, answer=item.answer)
            )
    return kept


def choose_template(
    proposal: GameProposal, brief: CreativeBrief, templates: dict[str, TemplateSpec]
) -> tuple[TemplateSpec, str | None]:
    if proposal.template == CUSTOM and CUSTOM in templates:  # feature 24, only when asked for
        problems = check_script(proposal.mechanic or "")
        if not problems:
            return templates[CUSTOM], None
        fallback = default_for(brief.product.category, templates)
        return fallback, f"the new mechanic may not run ({problems[0]}); used '{fallback.id}'"
    choices = buildable(templates)
    if proposal.template in choices:
        chosen = choices[proposal.template]
        if "quiz" in chosen.needs and len(clean_quiz(proposal.quiz, brief)) < QUIZ_QUESTIONS:
            fallback = default_for(brief.product.category, templates)
            return (
                fallback,
                f"the quiz needs three questions the video answers; used '{fallback.id}'",
            )
        return chosen, None
    fallback = default_for(brief.product.category, templates)
    return fallback, f"template '{proposal.template}' is not available; used '{fallback.id}'"


def game_content(spec: TemplateSpec, proposal: GameProposal, brief: CreativeBrief) -> Content:
    facts: list[str] = []
    if "facts" in spec.needs:
        facts = clean_facts(proposal.facts, brief)
        if len(facts) < 3:
            facts = [
                *facts,
                *(f for f in brief_facts(brief, proposal.product_label) if f not in facts),
            ]
    quiz = clean_quiz(proposal.quiz, brief)[:QUIZ_QUESTIONS] if "quiz" in spec.needs else []
    mechanic = proposal.mechanic if "mechanic" in spec.needs else None
    return Content(facts=facts[:6], quiz=quiz, mechanic=mechanic)


def safe_offer(line: str | None, owner_offer: str | None) -> tuple[str | None, str | None]:
    """The director's wording of the offer, but only if every number in it is the owner's."""
    if owner_offer is None:
        note = "the director wrote an offer the shop never gave; left it out" if line else None
        return None, note
    if line is None:
        return owner_offer, None
    if only_owner_numbers(line, owner_offer):
        return line, None
    return owner_offer, "the offer line changed the numbers; used the offer as given"


def language_note(language: str, text: GameText) -> str | None:
    if language != "ur":
        return None
    if all(_URDU.search(t) for t in (text.title, text.instruction, text.cta_label)):
        return None
    return "some game text is not in Urdu"


@dataclass(frozen=True)
class AssetInputs:
    product: str
    product_photo: str | None
    logo: str | None
    product_frames: ProductFrames | None = None
    more_products: tuple[MoreProductAsset, ...] = ()


def assemble(
    *,
    ad_id: uuid.UUID,
    shop_name: str,
    brief: CreativeBrief,
    proposal: GameProposal,
    templates: dict[str, TemplateSpec],
    assets: AssetInputs,
    seed: int,
) -> Assembly:
    notes: list[str] = []
    spec, note = choose_template(proposal, brief, templates)
    offer, offer_note = safe_offer(proposal.offer_line, brief.offer_text)
    coupon = coupon_code(ad_id)
    message = order_message(brief.language, shop_name, proposal.product_label, coupon)
    text = GameText(
        title=proposal.title.strip(),
        instruction=proposal.instruction.strip(),
        win=proposal.win_text.strip(),
        lose=proposal.lose_text.strip(),
        cta_label=proposal.cta_label.strip(),
        product_name=proposal.product_label.strip(),
        offer=offer,
        price=brief.price,
    )
    notes.extend(n for n in (note, offer_note, language_note(brief.language, text)) if n)
    config = GameConfig(
        template=spec.id,
        language=brief.language,
        direction="rtl" if brief.language == "ur" else "ltr",
        seed=seed,
        palette=build_palette(brief.palette, proposal.primary_color, proposal.accent_color),
        text=text,
        assets=Assets(
            product=assets.product,
            product_photo=assets.product_photo if spec.uses_photo else None,
            logo=assets.logo,
            # The moving sprite is for games that show the cut-out, not the photo puzzle.
            product_frames=None if spec.uses_photo else assets.product_frames,
            more_products=list(assets.more_products) if spec.uses_more_products else [],
        ),
        difficulty=spec.resolve(proposal.difficulty, proposal.difficulty_overrides),
        cta=build_cta(brief.cta.kind, brief.cta.target, message),
        coupon=coupon,
        content=game_content(spec, proposal, brief),
        theme=brief.occasion,
    )
    return Assembly(config=config, template=spec, notes=notes)
