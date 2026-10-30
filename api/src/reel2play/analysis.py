"""What the director reads from a video (features 4, 5, 8, 9), and the brief code derives from it.

``VideoAnalysis`` is the contract for the director's JSON answer. ``CreativeBrief`` is what
the rest of the pipeline uses: code merges the model's reading with the owner's own words,
and the owner always wins on price and offer.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class ProductCategory(StrEnum):
    CLOTHING = "clothing"
    BAKERY_FOOD = "bakery_food"
    SHOES = "shoes"
    COSMETICS = "cosmetics"
    PHONE_ACCESSORIES = "phone_accessories"
    HOME_DECOR = "home_decor"
    OTHER = "other"


class Box(BaseModel):
    """A box in a frame, as fractions of its width and height (0 to 1)."""

    x0: float = Field(ge=0, le=1)
    y0: float = Field(ge=0, le=1)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("box needs x1 > x0 and y1 > y0")
        return self

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        """(x, y, w, h) in pixels, at least 1 pixel each way."""
        x, y = int(self.x0 * width), int(self.y0 * height)
        return x, y, max(1, int(self.x1 * width) - x), max(1, int(self.y1 * height) - y)


class ProductRead(BaseModel):
    name: str = Field(min_length=1, max_length=60, description="Short product name")
    category: ProductCategory
    description: str = Field(max_length=200)
    segment_prompt: str = Field(
        min_length=1,
        max_length=40,
        description="One or two plain English nouns for the cut-out model, like 'shoe'",
    )


class OfferRead(BaseModel):
    text: str | None = Field(default=None, max_length=80, description="Offer as shown or said")
    source: Literal["caption", "speech", "none"] = "none"
    discount_percent: int | None = Field(default=None, ge=1, le=90)
    cod_available: bool = False
    free_delivery: bool = False
    seen_price: str | None = Field(
        default=None, max_length=40, description="A price seen or heard; never used as the price"
    )


Occasion = Literal["none", "ramzan", "eid", "independence_day", "wedding_season", "winter_sale"]
OCCASION_NAMES: dict[str, str] = {
    "ramzan": "Ramzan",
    "eid": "Eid",
    "independence_day": "14 August",
    "wedding_season": "wedding season",
    "winter_sale": "winter sale",
}


class VoiceRead(BaseModel):
    """What the owner said in their voice note (feature 10)."""

    transcript: str = Field(default="", max_length=400, description="Their words, as said")
    offer: str | None = Field(default=None, max_length=80, description="The offer they said")
    occasion: Occasion = "none"
    more_products: list[MoreProduct] = Field(default_factory=list, max_length=3)
    audience: str | None = Field(
        default=None, max_length=100, description="Who they said the product is for"
    )


class KeyFramePick(BaseModel):
    index: int = Field(ge=0)
    reason: str = Field(max_length=160)
    product_box: Box | None = None


class LogoRead(BaseModel):
    present: bool = False
    frame_index: int | None = Field(default=None, ge=0)
    box: Box | None = None


Lang = Literal["ur", "en"]
LANGUAGE_NAMES: dict[str, str] = {"ur": "Urdu", "en": "English"}


class LanguageRead(BaseModel):
    spoken: Literal["ur", "en", "mixed", "none"] = "none"
    on_screen: Literal["ur", "en", "mixed", "none"] = "none"
    recommended: Lang = "en"


class MoreProductPick(BaseModel):
    """Another product the shop shows (feature 11): a rack, a catalog, a set of flavours."""

    name: str = Field(min_length=1, max_length=40)
    segment_prompt: str = Field(min_length=1, max_length=40)
    frame_index: int = Field(ge=0, description="The candidate frame that shows it best")
    product_box: Box | None = None


class VideoAnalysis(BaseModel):
    """The director's answer after watching the video."""

    product: ProductRead
    brand_colors: list[str] = Field(min_length=1, max_length=5)
    mood: str = Field(max_length=60)
    audience: str = Field(max_length=100)
    tone_of_voice: str = Field(max_length=100)
    language: LanguageRead
    offer: OfferRead
    key_frames: list[KeyFramePick] = Field(min_length=1, max_length=3)
    logo: LogoRead = LogoRead()
    on_screen_text: list[str] = Field(default_factory=list, max_length=10)
    restricted: Literal["none", "alcohol", "tobacco", "weapons", "adult"] = Field(
        default="none", description="Set when the product is one Reel2Play never advertises"
    )
    voice_note: VoiceRead | None = Field(
        default=None, description="Only when the owner sent a voice note"
    )
    more_products: list[MoreProductPick] = Field(
        default_factory=list,
        max_length=3,
        description="Up to three other products shown clearly; empty for a single product",
    )
    occasion: Occasion = Field(
        default="none", description="An occasion the video itself is made for, like Eid"
    )

    @field_validator("brand_colors")
    @classmethod
    def _hex(cls, colors: list[str]) -> list[str]:
        valid = [c.lower() for c in colors if re.match(HEX_COLOR, c)]
        if not valid:
            raise ValueError("brand_colors needs #rrggbb values")
        return valid

    @field_validator("on_screen_text")
    @classmethod
    def _trim(cls, lines: list[str]) -> list[str]:
        return [line.strip()[:100] for line in lines if line.strip()]


class KeyFrame(BaseModel):
    index: int
    time_s: float
    key: str
    reason: str
    product_box: Box | None = None


class MoreProduct(BaseModel):
    """Another product for multi-item games, with the frame it is cut out of."""

    name: str
    segment_prompt: str
    key: str
    product_box: Box | None = None


class Cta(BaseModel):
    kind: Literal["whatsapp", "link"]
    target: str | None


class CreativeBrief(BaseModel):
    """Everything later steps need, with the owner's facts taking priority."""

    product: ProductRead
    palette: list[str]
    mood: str
    audience: str
    tone_of_voice: str
    language: Lang
    price: str | None = Field(description="Exactly as the owner typed it; never from the video")
    offer_text: str | None
    offer_source: Literal["owner", "voice", "caption", "speech", "none"]
    cod_available: bool
    free_delivery: bool
    seen_price: str | None
    cta: Cta
    key_frames: list[KeyFrame]
    logo_key: str | None = None
    occasion: Occasion = "none"
    more_products: list[MoreProduct] = Field(default_factory=list, max_length=3)
