"""What every quality gate reads (the evidence) and what it returns (a result)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from reel2play.analysis import CreativeBrief
from reel2play.builder.config import Palette


class CriticReview(BaseModel):
    """Spark Open's look at the real product, a gameplay screen and the end card."""

    product_matches: bool
    product_notes: str = Field(default="", max_length=300)
    offer_visible: bool
    price_matches: bool
    price_seen: str | None = Field(default=None, max_length=40)
    text_readable: bool
    language_ok: bool
    problems: list[str] = Field(default_factory=list, max_length=8)
    # Feature 31: claims in the game the shop could not prove, quoted as they appear.
    claims: list[str] = Field(default_factory=list, max_length=6)


@dataclass(frozen=True)
class ScreenCheck:
    """One screen size: load timing and the end card as the browser laid it out."""

    width: int
    height: int
    first_frame_ms: int
    end_card: dict[str, Any]
    screenshot_key: str


@dataclass(frozen=True)
class RunSummary:
    index: int
    driver: str
    won: bool
    seconds: float
    actions: int


@dataclass(frozen=True)
class Evidence:
    brief: CreativeBrief
    config: dict[str, Any]
    palette: Palette
    size_bytes: int
    rights_confirmed: bool
    audio_removed: bool
    runs: list[RunSummary]
    screens: dict[str, ScreenCheck]
    cta: dict[str, Any]
    log: dict[str, Any]
    critic: CriticReview | None
    gameplay_key: str | None


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    message: str
    measured: dict[str, Any] = field(default_factory=dict)
    screenshot_key: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "passed": self.passed,
            "message": self.message,
            "measured": self.measured,
            "screenshot_key": self.screenshot_key,
        }


def result(gate: str, passed: bool, ok: str, problem: str, **measured: Any) -> GateResult:
    """A result with the plain-words line for whichever way it went."""
    return GateResult(gate, passed, ok if passed else problem, measured)
