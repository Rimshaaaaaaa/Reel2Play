"""Fits the screen: nothing cut off at 360 by 640 or 768 by 1024, nor on the square and
landscape pages (feature 18), where the offer panel must show beside the game too."""

from typing import Any

from reel2play.gates.base import Evidence, GateResult
from reel2play.gates.thresholds import SHAPED

NAME = "fits_screen"
MUST_FIT = ("result", "offer", "price", "cta")


def _inside(box: dict[str, float] | None, area: dict[str, float]) -> bool:
    if not box:
        return False
    return (
        box["x"] >= area["x"] - 1
        and box["y"] >= area["y"] - 1
        and box["x"] + box["width"] <= area["x"] + area["width"] + 1
        and box["y"] + box["height"] <= area["y"] + area["height"] + 1
    )


def screen_problems(name: str, end_card: dict[str, Any]) -> list[str]:
    viewport = end_card.get("viewport", {})
    stage = end_card.get("stage")
    if not stage:
        return [f"{name}: the game did not show"]
    whole = {"x": 0, "y": 0, "width": viewport.get("width", 0), "height": viewport.get("height", 0)}
    problems = [] if _inside(stage, whole) else [f"{name}: the game is larger than the screen"]
    if name in SHAPED:
        if end_card.get("layout") != name:
            problems.append(f"{name}: the page did not take the {name} shape")
        elif not _inside(end_card.get("side"), whole):
            problems.append(f"{name}: the offer panel is outside the screen")
    for part_name in MUST_FIT:
        part = end_card.get("parts", {}).get(part_name)
        if part is None:
            continue
        if not _inside(part.get("box"), stage):
            problems.append(f"{name}: the {part_name} is outside the game area")
        elif part.get("clipped"):
            problems.append(f"{name}: the {part_name} text is cut off")
    return problems


def check(evidence: Evidence) -> GateResult:
    problems: list[str] = []
    for name, screen in evidence.screens.items():
        problems.extend(screen_problems(name, screen.end_card))
    sizes = {name: f"{s.width}x{s.height}" for name, s in evidence.screens.items()}
    if problems:
        worst = next((s for n, s in evidence.screens.items() if problems[0].startswith(n)), None)
        return GateResult(
            NAME,
            False,
            "; ".join(problems).capitalize() + ".",
            {"screens": sizes, "problems": problems},
            worst.screenshot_key if worst else None,
        )
    return GateResult(
        NAME,
        True,
        "Everything fits on a small phone, a tablet, and square and landscape pages.",
        {"screens": sizes},
    )
