"""Meta playable export for app developers (feature 35).

The same tested game, compiled for Meta's playable format: the button calls
``FbPlayableAd.onCTAClick()`` and nothing else, there are no links, redirects or network
calls, and the file stays within Meta's limits (one HTML file up to 2 MB, or a ZIP up to
5 MB with at most 100 files). Code checks the file, and the harness plays it once to see
the call happen.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from reel2play.builder.config import GameConfig
from reel2play.builder.html import compile_game
from reel2play.gates.thresholds import (
    META_HTML_MAX_BYTES,
    META_ZIP_MAX_BYTES,
    META_ZIP_MAX_FILES,
    SCREENS,
)
from reel2play.playtest.session import Harness
from reel2play.settings import Settings

# What Meta's review rejects as "JavaScript redirect code".
REDIRECT_CODE = re.compile(
    r"\b(?:window|document|top|self|parent)\.location\b|\blocation\.(?:href|assign|replace)\b"
    r"|\bwindow\.open\s*\("
)


class MetaExportError(ValueError):
    pass


@dataclass(frozen=True)
class MetaCheck:
    cta_calls: int
    requests: list[str] = field(default_factory=list)
    navigations: list[str] = field(default_factory=list)
    popups: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[str]:
        found: list[str] = []
        if self.cta_calls < 1:
            found.append("the button did not call FbPlayableAd.onCTAClick()")
        if self.requests:
            found.append(f"the game made {len(self.requests)} network request(s)")
        if self.navigations or self.popups:
            found.append("the game tried to open another page")
        return found


def meta_config(config: GameConfig) -> GameConfig:
    """The tested game's config, switched to the Meta platform and without analytics."""
    return config.model_copy(update={"platform": "meta", "analytics": None})


def build_meta_html(config: GameConfig, settings: Settings) -> bytes:
    html = compile_game(config, settings.engine_dist_dir, META_HTML_MAX_BYTES).html
    found = REDIRECT_CODE.findall(html.decode("utf-8"))
    if found:
        raise MetaExportError(f"the playable contains redirect code: {sorted(set(found))}")
    return html


def zip_playable(html: bytes) -> bytes:
    """The playable as a ZIP with index.html, for ad accounts that upload ZIPs."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", html)
    data = out.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = len(archive.namelist())
    if len(data) > META_ZIP_MAX_BYTES or files > META_ZIP_MAX_FILES:
        raise MetaExportError(f"the ZIP is {len(data)} bytes with {files} files")
    return data


def check_playable(harness: Harness, html_b64: str) -> MetaCheck:
    """Open the playable, let the clock run out, tap the button, and read what happened.

    The harness log covers its whole session, so only entries added here count."""
    before = harness.call("log")
    width, height = SCREENS["phone"]
    harness.call("open", html_b64=html_b64, width=width, height=height)
    harness.call("start")
    harness.call("advance", seconds=31.0)
    cta = harness.call("click_cta")
    after = harness.call("log")

    def added(name: str) -> list[str]:
        return list(after.get(name, []))[len(before.get(name, [])) :]

    return MetaCheck(
        cta_calls=int(cta.get("fb_calls", 0)),
        requests=added("requests"),
        navigations=added("navigations"),
        popups=list(cta.get("popups", [])),
    )
