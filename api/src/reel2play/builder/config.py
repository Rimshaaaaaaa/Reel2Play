"""The game config (feature 15): one JSON object, checked here, compiled by the builder.

Field names serialize in camelCase to match engine/src/config.ts exactly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from reel2play.analysis import HEX_COLOR

Hex = str


class Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class Palette(Camel):
    background: Hex = Field(pattern=HEX_COLOR)
    surface: Hex = Field(pattern=HEX_COLOR)
    primary: Hex = Field(pattern=HEX_COLOR)
    primary_ink: Hex = Field(pattern=HEX_COLOR)
    accent: Hex = Field(pattern=HEX_COLOR)
    accent_ink: Hex = Field(pattern=HEX_COLOR)
    ink: Hex = Field(pattern=HEX_COLOR)
    muted: Hex = Field(pattern=HEX_COLOR)


class GameText(Camel):
    title: str = Field(min_length=1, max_length=40)
    instruction: str = Field(min_length=1, max_length=90)
    win: str = Field(min_length=1, max_length=60)
    lose: str = Field(min_length=1, max_length=60)
    cta_label: str = Field(min_length=1, max_length=32)
    product_name: str = Field(min_length=1, max_length=40)
    offer: str | None = Field(default=None, max_length=80)
    price: str | None = Field(default=None, max_length=40)


class ProductFrames(Camel):
    """Feature 7: the product's animation, square frames side by side in one image."""

    strip: str = Field(pattern=r"^data:image/(png|webp);base64,")
    frames: int = Field(ge=2, le=16)
    fps: float = Field(gt=0, le=30)


class MoreProductAsset(Camel):
    """Feature 11: another of the shop's products, for multi-item games."""

    image: str = Field(pattern=r"^data:image/(png|webp);base64,")
    name: str = Field(min_length=1, max_length=40)


class Assets(Camel):
    product: str = Field(pattern=r"^data:image/(png|webp);base64,")
    product_photo: str | None = Field(default=None, pattern=r"^data:image/(jpeg|webp);base64,")
    logo: str | None = Field(default=None, pattern=r"^data:image/(png|webp);base64,")
    product_frames: ProductFrames | None = None
    more_products: list[MoreProductAsset] = Field(default_factory=list, max_length=3)


class Cta(Camel):
    kind: Literal["whatsapp", "link"]
    url: str = Field(pattern=r"^https://")


class Analytics(Camel):
    endpoint: str
    ad_id: str
    variant: str


class QuizItem(Camel):
    question: str = Field(min_length=1, max_length=90)
    options: list[str] = Field(min_length=2, max_length=3)
    answer: int = Field(ge=0, le=2)


class Content(Camel):
    """Words some templates need (feature 13), checked by code before they reach a game."""

    facts: list[str] = Field(default_factory=list, max_length=6)
    quiz: list[QuizItem] = Field(default_factory=list, max_length=3)
    # Feature 24: a new mechanic the director wrote, checked by builder/mechanic.py.
    mechanic: str | None = Field(default=None, max_length=6000)


class GameConfig(Camel):
    version: Literal[1] = 1
    template: str
    language: Literal["ur", "en"]
    direction: Literal["rtl", "ltr"]
    seed: int = Field(ge=0, le=2**31 - 1)
    platform: Literal["hosted", "meta", "preview"] = "hosted"
    palette: Palette
    text: GameText
    assets: Assets
    difficulty: dict[str, float]
    cta: Cta
    coupon: str | None = Field(default=None, max_length=16)
    max_seconds: int = Field(default=30, ge=10, le=30)
    time_scale: float = Field(default=1.0, gt=0, le=10)
    analytics: Analytics | None = None
    content: Content = Field(default_factory=Content)
    # Feature 22: a seasonal theme; the engine draws it and words the greeting itself.
    theme: Literal["none", "ramzan", "eid", "independence_day", "wedding_season", "winter_sale"] = (
        "none"
    )

    def wire(self) -> dict[str, object]:
        """The config exactly as the engine reads it."""
        return self.model_dump(by_alias=True, mode="json")
