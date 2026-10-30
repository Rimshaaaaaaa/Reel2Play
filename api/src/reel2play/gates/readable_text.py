"""Readable text: contrast of at least 4.5 to 1 in code, then Spark Open on the screenshot."""

import re

from reel2play.builder.theme import contrast, palette_problems
from reel2play.gates.base import Evidence, GateResult
from reel2play.gates.thresholds import MIN_CONTRAST

NAME = "readable_text"
_RGB = re.compile(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)")


def css_hex(value: str) -> str | None:
    """#rrggbb for an opaque CSS rgb()/rgba() colour; None for see-through or gradients."""
    match = _RGB.match(value or "")
    if not match or (match.group(4) is not None and float(match.group(4)) < 0.95):
        return None
    return "#" + "".join(f"{int(match.group(i)):02x}" for i in (1, 2, 3))


def page_problems(styles: list[dict[str, object]]) -> list[str]:
    problems = []
    for style in styles:
        fg, bg = css_hex(str(style.get("color"))), css_hex(str(style.get("background")))
        if fg and bg and contrast(fg, bg) < MIN_CONTRAST:
            problems.append(f"'{str(style.get('text'))[:30]}' is {contrast(fg, bg):.1f}:1")
    return problems


def check(evidence: Evidence) -> GateResult:
    problems = palette_problems(evidence.palette)
    problems += page_problems(evidence.screens["phone"].end_card.get("styles", []))
    critic = evidence.critic
    if critic is not None and not critic.text_readable:
        problems.append("the critic found text hard to read")
    if critic is not None and not critic.language_ok:
        problems.append("the critic found text in the wrong language")
    screen = evidence.screens["phone"]
    if problems:
        return GateResult(
            NAME,
            False,
            "Some text is hard to read: " + "; ".join(problems) + ".",
            {"problems": problems},
            screen.screenshot_key,
        )
    return GateResult(
        NAME,
        True,
        "All text is easy to read, in the shop's language.",
        {"min_contrast": MIN_CONTRAST},
    )
