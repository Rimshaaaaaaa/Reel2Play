"""Embed code for the shop's own website (feature 37).

A short ``<iframe>`` snippet the shop pastes into its site builder: the tall game for a side
column or a phone layout, or the wide page (the game beside the offer) for a full-width
section. The game keeps its sandbox; plays are marked ``from=embed`` so the shop can see how
many came from its site, and nothing about the visitor is sent.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Literal

Shape = Literal["tall", "wide"]
SIZES: dict[Shape, tuple[str, str, int]] = {
    # query, aspect ratio, max width in CSS pixels
    "tall": ("from=embed", "9 / 16", 400),
    "wide": ("layout=landscape&from=embed", "16 / 9", 960),
}


@dataclass(frozen=True)
class Embed:
    shape: Shape
    src: str
    code: str


def embed_code(link: str, title: str, shape: Shape) -> Embed:
    query, ratio, width = SIZES[shape]
    src = f"{link}?{query}"
    style = (
        f"display:block;width:100%;max-width:{width}px;aspect-ratio:{ratio};"
        "border:0;border-radius:16px;margin:0 auto"
    )
    code = (
        f'<iframe src="{html.escape(src, quote=True)}" title="{html.escape(title, quote=True)}" '
        f'style="{style}" loading="lazy" allow="fullscreen" '
        'referrerpolicy="no-referrer"></iframe>'
    )
    return Embed(shape, src, code)


def embeds(link: str, title: str) -> list[Embed]:
    return [embed_code(link, title, shape) for shape in SIZES]
