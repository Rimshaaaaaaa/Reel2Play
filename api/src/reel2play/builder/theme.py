"""Game palette from the shop's brand colours, with readable text guaranteed by code.

A neutral base (tinted a little toward the brand) carries the shop's main colour and one
accent. Text colours are chosen, and brand colours nudged, until every text and background
pair reaches a contrast of at least 4.5 to 1 (the Readable text gate).
"""

from __future__ import annotations

import colorsys

from reel2play.builder.config import Palette

MIN_CONTRAST = 4.5
INK = "#23232e"
MUTED = "#555766"
SURFACE = "#fbfbfd"
NEUTRAL = "#eceef2"
WHITE = "#ffffff"
FALLBACK_PRIMARY = "#3949ab"
FALLBACK_ACCENT = "#f2b705"


def rgb(hex_color: str) -> tuple[float, float, float]:
    value = int(hex_color.lstrip("#"), 16)
    return ((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255


def to_hex(r: float, g: float, b: float) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in (r, g, b))


def mix(a: str, b: str, amount: float) -> str:
    x, y = rgb(a), rgb(b)
    return to_hex(*(p + (q - p) * amount for p, q in zip(x, y, strict=True)))


def luminance(hex_color: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def saturation_and_lightness(hex_color: str) -> tuple[float, float]:
    hue, lightness, saturation = colorsys.rgb_to_hls(*rgb(hex_color))
    del hue
    return saturation, lightness


def hue(hex_color: str) -> float:
    return colorsys.rgb_to_hls(*rgb(hex_color))[0]


def is_brand_colour(hex_color: str) -> bool:
    """Colourful enough to carry a brand: not near white, black or grey."""
    saturation, lightness = saturation_and_lightness(hex_color)
    return saturation >= 0.25 and 0.12 <= lightness <= 0.88


def best_ink(background: str) -> str:
    return WHITE if contrast(background, WHITE) >= contrast(background, INK) else INK


def readable_pair(color: str) -> tuple[str, str]:
    """``color`` (darkened or lightened only as much as needed) and its text colour."""
    ink = best_ink(color)
    target = "#000000" if ink == WHITE else WHITE
    step = 0.0
    adjusted = color
    while contrast(adjusted, ink) < MIN_CONTRAST and step < 1.0:
        step += 0.04
        adjusted = mix(color, target, step)
    return adjusted, ink


def pick_colours(brand: list[str], primary: str | None, accent: str | None) -> tuple[str, str]:
    colourful = [c.lower() for c in brand if is_brand_colour(c)]
    chosen_primary = primary.lower() if primary and primary.lower() in colourful else None
    if chosen_primary is None:
        chosen_primary = max(colourful, key=lambda c: saturation_and_lightness(c)[0], default=None)
    chosen_primary = chosen_primary or FALLBACK_PRIMARY
    others = [c for c in colourful if c != chosen_primary]
    chosen_accent = accent.lower() if accent and accent.lower() in others else None
    if chosen_accent is None:
        distinct = [c for c in others if abs(hue(c) - hue(chosen_primary)) > 0.08]
        chosen_accent = distinct[0] if distinct else FALLBACK_ACCENT
    return chosen_primary, chosen_accent


def build_palette(
    brand: list[str], primary: str | None = None, accent: str | None = None
) -> Palette:
    main, second = pick_colours(brand, primary, accent)
    main, main_ink = readable_pair(main)
    second, second_ink = readable_pair(second)
    return Palette(
        background=mix(NEUTRAL, main, 0.07),
        surface=SURFACE,
        primary=main,
        primary_ink=main_ink,
        accent=second,
        accent_ink=second_ink,
        ink=INK,
        muted=MUTED,
    )


def palette_problems(palette: Palette) -> list[str]:
    """Every text and background pair below 4.5:1, for the Readable text gate."""
    pairs = {
        "ink on background": (palette.ink, palette.background),
        "ink on surface": (palette.ink, palette.surface),
        "muted on surface": (palette.muted, palette.surface),
        "button text": (palette.primary_ink, palette.primary),
        "offer text": (palette.accent_ink, palette.accent),
    }
    return [
        f"{name} is {contrast(fg, bg):.1f}:1"
        for name, (fg, bg) in pairs.items()
        if contrast(fg, bg) < MIN_CONTRAST
    ]
