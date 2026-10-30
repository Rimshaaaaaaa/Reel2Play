"""Template marketplace for designers (feature 49).

Designers send a new template: its ``template.json`` and ``game.ts``. Code checks both before
a person looks: the template must fit the registry's schema, use a new id, keep every tier
inside its ranges, stay small, import only the shared engine, and use none of the browser
features a game may not touch (network, storage, cookies, eval, new windows). A submission
that passes waits for review by the Reel2Play team; an approved one is added to
``templates/`` by a maintainer, where it is built, tested in a browser and played by the
play-tester like every template before any shop can get it. Submitted code is never run here.

The public side is the template gallery, each with a live demo built from a synthetic,
code-drawn product, and the designer's credit.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field

from PIL import Image, ImageDraw
from pydantic import ValidationError

from reel2play.builder.assets import photo_data_url, sprite_data_url
from reel2play.builder.config import (
    Assets,
    Content,
    Cta,
    GameConfig,
    GameText,
    Palette,
    QuizItem,
)
from reel2play.builder.templates import TemplateSpec, Tier

MAX_GAME_TS_BYTES = 60 * 1024
MAX_TEMPLATE_JSON_BYTES = 16 * 1024
ENGINE_IMPORT = "../../engine/src/index"
FORBIDDEN = {
    r"\bfetch\s*\(": "network calls (fetch)",
    r"\bXMLHttpRequest\b": "network calls (XMLHttpRequest)",
    r"\bWebSocket\b": "network calls (WebSocket)",
    r"\bEventSource\b": "network calls (EventSource)",
    r"\bsendBeacon\b": "network calls (sendBeacon)",
    r"\beval\s*\(": "eval",
    r"\bnew\s+Function\b|\bFunction\s*\(": "running text as code (Function)",
    r"\bimport\s*\(": "loading code at run time (import())",
    r"\bimportScripts\b|\bnew\s+Worker\b": "workers",
    r"\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b": "browser storage",
    r"document\s*\.\s*cookie": "cookies",
    r"window\s*\.\s*open\b|\blocation\s*\.\s*(href|assign|replace)\b": "leaving the page",
    r"\bpostMessage\b": "messages to other pages",
    r"\binnerHTML\b|\bouterHTML\b|insertAdjacentHTML|document\s*\.\s*write": "writing HTML",
    r"\bnavigator\s*\.\s*(geolocation|mediaDevices|clipboard)": "device access",
}
_IMPORT = re.compile(r"""^\s*import\b[^;]*?from\s+["']([^"']+)["']""", re.M)
OFFICIAL_DESIGNER = "Reel2Play"


@dataclass
class SubmissionCheck:
    template_id: str | None
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def check_submission(template_json: bytes, game_ts: bytes, existing: set[str]) -> SubmissionCheck:
    """What is wrong with a designer's template, in plain words; nothing means it may go to a
    person for review."""
    problems: list[str] = []
    spec: TemplateSpec | None = None
    if len(template_json) > MAX_TEMPLATE_JSON_BYTES:
        problems.append("template.json is larger than 16 KB")
    try:
        raw = json.loads(template_json.decode("utf-8"))
        spec = TemplateSpec.model_validate(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        problems.append("template.json is not valid JSON")
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        problems.append(f"template.json: {where}: {first['msg']}")
    if spec is not None:
        if spec.id in existing:
            problems.append(f"a template called {spec.id!r} already exists")
        if not spec.params:
            problems.append("template.json needs at least one difficulty parameter")
    if len(game_ts) > MAX_GAME_TS_BYTES:
        problems.append("game.ts is larger than 60 KB")
    try:
        source = game_ts.decode("utf-8")
    except UnicodeDecodeError:
        return SubmissionCheck(spec.id if spec else None, [*problems, "game.ts is not text"])
    imports = set(_IMPORT.findall(source))
    if imports - {ENGINE_IMPORT}:
        others = ", ".join(sorted(imports - {ENGINE_IMPORT}))
        problems.append(
            f"game.ts may import only the shared engine ({ENGINE_IMPORT}), not {others}"
        )
    for pattern, what in FORBIDDEN.items():
        if re.search(pattern, source):
            problems.append(f"game.ts uses {what}, which games may not")
    for needed, why in (
        ("startGame(", "start the game with startGame()"),
        ("debugState", "describe its state for the play-tester (debugState)"),
        ("param(", "read its difficulty from template.json with param()"),
    ):
        if needed not in source:
            problems.append(f"game.ts must {why}")
    return SubmissionCheck(spec.id if spec else None, problems)


# --- the live demo of a template ---------------------------------------------------------------

DEMO_PALETTE = Palette(
    background="#eef0f3",
    surface="#ffffff",
    primary="#2f5d8a",
    primary_ink="#ffffff",
    accent="#f2b544",
    accent_ink="#1d2430",
    ink="#1d2430",
    muted="#5a6272",
)


def demo_product() -> bytes:
    """A synthetic product drawn in code: a gift parcel with a ribbon (no photo, no person)."""
    size = 320
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 110, 280, 290), radius=22, fill=(47, 93, 138, 255))
    draw.rounded_rectangle((28, 88, 292, 140), radius=16, fill=(64, 118, 168, 255))
    draw.rectangle((142, 88, 178, 290), fill=(242, 181, 68, 255))
    draw.ellipse((96, 40, 160, 100), outline=(242, 181, 68, 255), width=16)
    draw.ellipse((160, 40, 224, 100), outline=(242, 181, 68, 255), width=16)
    draw.rounded_rectangle((56, 160, 120, 176), radius=8, fill=(255, 255, 255, 90))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def demo_photo(product_png: bytes) -> bytes:
    field_image = Image.new("RGB", (640, 640), (230, 233, 238))
    product = Image.open(io.BytesIO(product_png)).convert("RGBA").resize((420, 420))
    field_image.paste(product, (110, 110), product)
    out = io.BytesIO()
    field_image.save(out, "JPEG", quality=85)
    return out.getvalue()


def demo_config(spec: TemplateSpec) -> GameConfig:
    """A playable demo of one template, with synthetic words and a code-drawn product."""
    product = demo_product()
    needs = set(spec.needs)
    return GameConfig(
        template=spec.id,
        language="en",
        direction="ltr",
        seed=20261028,
        platform="preview",
        palette=DEMO_PALETTE,
        text=GameText(
            title=spec.name[:40],
            instruction=f"{spec.control}."[:90],
            win="You won the demo!",
            lose="Nice try! Play again?",
            cta_label="Make one for your shop",
            product_name="Gift parcel (synthetic)",
            offer="Demo offer: 10% off",
            price="Rs 1,000",
        ),
        assets=Assets(
            product=sprite_data_url(product),
            product_photo=photo_data_url(demo_photo(product), None),
            logo=None,
        ),
        difficulty=spec.resolve(Tier.NORMAL),
        cta=Cta(kind="link", url="https://wa.me/"),
        coupon=None,
        content=Content(
            facts=["Wrapped by hand", "Ships in two days", "Ribbon included"]
            if "facts" in needs
            else [],
            quiz=[
                QuizItem(
                    question="What colour is the ribbon?",
                    options=["Gold", "Green", "Red"],
                    answer=0,
                ),
                QuizItem(
                    question="What is inside the box?",
                    options=["A shoe", "A gift", "A cake"],
                    answer=1,
                ),
                QuizItem(
                    question="How is it wrapped?",
                    options=["Not at all", "In a bag", "By hand"],
                    answer=2,
                ),
            ]
            if "quiz" in needs
            else [],
        ),
    )
