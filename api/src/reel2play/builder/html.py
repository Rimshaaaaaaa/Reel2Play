"""Compile a game config into one self-contained HTML file and enforce the size budget.

The engine build (engine/dist) provides the HTML shell, the stylesheet and one script per
template; this module only fills the shell's {{PLACEHOLDERS}}.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from reel2play.builder.config import GameConfig
from reel2play.builder.mechanic import mechanic_head

_PLACEHOLDER = re.compile(r"\{\{([A-Z]+)\}\}")


class EngineMissingError(FileNotFoundError):
    """engine/dist has not been built: run `cd engine && npm run build` (or `make engine`)."""


class BudgetExceededError(ValueError):
    pass


@dataclass(frozen=True)
class BuiltGame:
    html: bytes
    size: int
    sha256: str


@lru_cache(maxsize=16)
def _read(dist: Path, name: str) -> str:
    path = dist / name
    if not path.is_file():
        raise EngineMissingError(f"{path} is missing; build the engine first")
    return path.read_text(encoding="utf-8")


def script_json(value: object) -> str:
    """JSON that cannot close or confuse a <script> element."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def compile_game(config: GameConfig, dist: Path, max_bytes: int, head: str = "") -> BuiltGame:
    if config.content.mechanic:  # feature 24: checked again here, then given its own block
        head = f"{head}\n{mechanic_head(config.content.mechanic)}"
    fill = {
        "LANG": config.language,
        "DIR": config.direction,
        "TITLE": html.escape(config.text.title),
        "HEAD": head,
        "STYLE": _read(dist, "game.css"),
        "CONFIG": script_json(config.wire()),
        "SCRIPT": _read(dist, f"{config.template}.js"),
    }
    page = _PLACEHOLDER.sub(lambda m: fill.get(m.group(1), ""), _read(dist, "shell.html"))
    data = page.encode("utf-8")
    if len(data) > max_bytes:
        raise BudgetExceededError(
            f"the game is {len(data) / 1024 / 1024:.2f} MB; the limit is "
            f"{max_bytes / 1024 / 1024:.0f} MB"
        )
    return BuiltGame(html=data, size=len(data), sha256=hashlib.sha256(data).hexdigest())
