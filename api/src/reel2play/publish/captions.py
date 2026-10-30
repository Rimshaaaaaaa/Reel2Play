"""Captions and hashtags for Instagram, Facebook and WhatsApp Status (feature 34).

Spark Open writes them in the shop's language. Code then checks every number against the
owner's own price and offer, cleans the hashtags and adds the game link; models never
write links. If the words make a claim the owner never made, the shop gets plain captions
written by code instead, and the audit trail says why.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from reel2play.ai.client import AIClient, Subject
from reel2play.analysis import LANGUAGE_NAMES, CreativeBrief
from reel2play.claims import only_owner_numbers, unprovable_in
from reel2play.safety import as_data

PROMPT = "publisher_captions"
MAX_HASHTAGS = 6
_NOT_WORD = re.compile(r"[\W\d_]+", re.UNICODE)

WORDS = {
    "en": {
        "bio": "Play the game: link in bio.",
        "play": "Play: {link}",
        "intro": "{product}: play our 20-second game.",
        "offer": "Win and get {offer}.",
        "price": "Price: {price}.",
    },
    "ur": {
        "bio": "گیم کھیلیں: لنک بائیو میں ہے\u06d4",
        "play": "کھیلیں: {link}",
        "intro": "{product}: ہماری 20 سیکنڈ کی گیم کھیلیں\u06d4",
        "offer": "جیتیں اور پائیں {offer}\u06d4",
        "price": "قیمت: {price}\u06d4",
    },
}


class CaptionDraft(BaseModel):
    instagram: str = Field(min_length=1, max_length=400)
    facebook: str = Field(min_length=1, max_length=400)
    whatsapp_status: str = Field(min_length=1, max_length=200)
    hashtags: list[str] = Field(default_factory=list, max_length=10)


@dataclass(frozen=True)
class Captions:
    instagram: str
    facebook: str
    whatsapp_status: str
    hashtags: list[str]
    language: str
    written_by: str  # "model" or "code"

    def as_json(self) -> dict[str, Any]:
        return {
            "instagram": self.instagram,
            "facebook": self.facebook,
            "whatsapp_status": self.whatsapp_status,
            "hashtags": self.hashtags,
            "language": self.language,
            "written_by": self.written_by,
        }


def clean_hashtags(tags: list[str]) -> list[str]:
    """Letters only (any script), no numbers or spaces, no repeats, at most six."""
    kept: list[str] = []
    for tag in tags:
        word = _NOT_WORD.sub("", tag)
        if 2 <= len(word) <= 30 and word.lower() not in {k.lower() for k in kept}:
            kept.append(word)
    return kept[:MAX_HASHTAGS]


def code_draft(brief: CreativeBrief) -> CaptionDraft:
    """Plain captions from the owner's own facts, used when the model's words overreach."""
    words = WORDS[brief.language]
    lines = [words["intro"].format(product=brief.product.name)]
    if brief.offer_text:
        lines.append(words["offer"].format(offer=brief.offer_text))
    if brief.price:
        lines.append(words["price"].format(price=brief.price))
    text = " ".join(lines)
    return CaptionDraft(instagram=text, facebook=text, whatsapp_status=lines[0], hashtags=[])


def honest(draft: CaptionDraft, facts: Sequence[str | None]) -> bool:
    """Every number must come from the facts: the owner's price and offer, the names, and
    the game's own words (like "catch 10")."""
    text = " ".join([draft.instagram, draft.facebook, draft.whatsapp_status, *draft.hashtags])
    owner = " ".join(f for f in facts if f).casefold()
    claims = [c for c in unprovable_in(text) if c.casefold() not in owner]  # feature 31
    return only_owner_numbers(text, *facts) and not claims


def finish(draft: CaptionDraft, brief: CreativeBrief, link: str, written_by: str) -> Captions:
    words = WORDS[brief.language]
    tags = clean_hashtags(draft.hashtags)
    tag_line = " ".join(f"#{tag}" for tag in tags)
    play = words["play"].format(link=link)
    return Captions(
        instagram="\n\n".join(part for part in (draft.instagram, words["bio"], tag_line) if part),
        facebook=f"{draft.facebook}\n\n{play}",
        whatsapp_status=f"{draft.whatsapp_status}\n{link}",
        hashtags=tags,
        language=brief.language,
        written_by=written_by,
    )


def write_captions(
    ai: AIClient,
    subject: Subject,
    *,
    shop_name: str,
    brief: CreativeBrief,
    game_text: dict[str, Any],
    link: str,
) -> Captions:
    draft = ai.ask_json(
        PROMPT,
        {
            "language_name": LANGUAGE_NAMES[brief.language],
            "shop_name": as_data(shop_name),
            "product": as_data(brief.product.name),
            "category": brief.product.category.replace("_", " "),
            "price": as_data(brief.price),
            "offer": as_data(brief.offer_text),
            "game_title": as_data(str(game_text.get("title", ""))),
            "instruction": as_data(str(game_text.get("instruction", ""))),
            "tone": as_data(brief.tone_of_voice),
        },
        CaptionDraft,
        subject=subject,
    )
    facts = [
        brief.price,
        brief.offer_text,
        brief.product.name,
        shop_name,
        str(game_text.get("title", "")),
        str(game_text.get("instruction", "")),
        "20",  # the game's length, as the captions may say "a 20-second game"
    ]
    if honest(draft, facts):
        return finish(draft, brief, link, "model")
    return finish(code_draft(brief), brief, link, "code")
