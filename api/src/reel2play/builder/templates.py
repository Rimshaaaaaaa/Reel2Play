"""Game templates (features 12 and 14): read from templates/<id>/template.json.

Adding a template means adding a folder with template.json and game.ts; nothing in the
pipeline changes. Difficulty values live only in template.json.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from reel2play.analysis import ProductCategory


class Tier(StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class ParamRange(BaseModel):
    easy: float
    normal: float
    hard: float
    min: float
    max: float

    @model_validator(mode="after")
    def _inside(self) -> ParamRange:
        for value in (self.easy, self.normal, self.hard):
            if not self.min <= value <= self.max:
                raise ValueError("tier values must lie between min and max")
        return self

    def at(self, tier: Tier) -> float:
        return float(getattr(self, tier.value))

    def clamp(self, value: float) -> float:
        return max(self.min, min(self.max, value))


class TemplateSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,29}$")
    name: str
    plan: str
    description: str
    control: str
    product_role: str
    ends_when: str
    good_for: list[ProductCategory]
    uses_photo: bool
    # Feature 11: the game can show the shop's other products as well as the main one.
    uses_more_products: bool = False
    # Words the game needs from the director: facts to reveal, or three quiz questions.
    needs: list[Literal["facts", "quiz", "mechanic"]] = Field(default_factory=list)
    params: dict[str, ParamRange]
    # Feature 49: who made it, credited in the template gallery.
    designer: str = Field(default="Reel2Play", max_length=80)
    # Game seconds that pass for each tap or drag the play-tester makes: a person's pace.
    # Real-time games keep the default; a puzzle needs time to look before each tap.
    tester_pace_seconds: float = Field(default=0.35, gt=0, le=3)

    def resolve(self, tier: Tier, overrides: dict[str, float] | None = None) -> dict[str, float]:
        """Every parameter at ``tier``, with any overrides clamped to the allowed range."""
        values = {name: spec.at(tier) for name, spec in self.params.items()}
        for name, value in (overrides or {}).items():
            if name in self.params:
                values[name] = self.params[name].clamp(value)
        return values

    def ranges_line(self) -> str:
        """Parameter ranges for fix rounds, like "goal 6-14 (normal 10)"."""
        ranges = ", ".join(
            f"{name} {spec.min:g}-{spec.max:g} (normal {spec.normal:g})"
            for name, spec in self.params.items()
        )
        return f"[{ranges}]"

    def catalog_line(self) -> str:
        return (
            f"- {self.id}: {self.description} Control: {self.control}. "
            f"The product is {self.product_role.lower()}. Ends: {self.ends_when}."
            + (
                " Needs: " + ", ".join(NEED_WORDS[need] for need in self.needs) + "."
                if self.needs
                else ""
            )
        )


NEED_WORDS = {
    "facts": "three to six short facts about the product, from the video",
    "quiz": "three quiz questions answered by the video",
    "mechanic": "a new mechanic, written as a small checked script",
}


class UnknownTemplateError(LookupError):
    pass


@lru_cache(maxsize=4)
def load_templates(directory: Path) -> dict[str, TemplateSpec]:
    templates: dict[str, TemplateSpec] = {}
    for path in sorted(directory.glob("*/template.json")):
        spec = TemplateSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if spec.id != path.parent.name:
            raise ValueError(f"{path}: id {spec.id!r} must match its folder name")
        templates[spec.id] = spec
    if not templates:
        raise FileNotFoundError(f"no templates found in {directory}")
    return templates


def buildable(templates: dict[str, TemplateSpec]) -> dict[str, TemplateSpec]:
    """Templates that are built: the demo's three (Build) and the six more (Stretch)."""
    return {key: spec for key, spec in templates.items() if spec.plan in ("Build", "Stretch")}


def default_for(category: ProductCategory, templates: dict[str, TemplateSpec]) -> TemplateSpec:
    """The first buildable template made for this kind of product: the demo's three first,
    since the fallback should be the most played-in game."""
    choices = sorted(buildable(templates).values(), key=lambda spec: spec.plan != "Build")
    for spec in choices:
        if category in spec.good_for:
            return spec
    return choices[0]
