"""The hosted game page behind each short link (feature 32): /g/<code>.

Served by the API because free storage tiers send HTML as plain text. The page is the
tested game with link-preview tags, sandboxed like every game the API serves.
"""

from __future__ import annotations

import re
import uuid
from collections import OrderedDict
from threading import Lock

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.media.storage import MediaStorage
from reel2play.models import Ad, AdStatus, Export, ExportKind, Shop
from reel2play.publish.hosted import (
    SLUG_ALPHABET,
    SLUG_LENGTH,
    optin_tag,
    origin_of,
    with_preview,
)
from reel2play.routes.leads import optin_link
from reel2play.routes.media import GAME_CSP
from reel2play.settings import Settings

router = APIRouter(tags=["game page"])

SLUG = re.compile(f"^[{re.escape(SLUG_ALPHABET)}]{{{SLUG_LENGTH}}}$")
CACHE_SIZE = 64


class PageCache:
    """The most recently opened game pages, so a shared link does not hit storage each time."""

    def __init__(self, size: int = CACHE_SIZE) -> None:
        self._pages: OrderedDict[str, bytes] = OrderedDict()
        self._size = size
        self._lock = Lock()

    def get(self, storage: MediaStorage, key: str) -> bytes:
        with self._lock:
            if key in self._pages:
                self._pages.move_to_end(key)
                return self._pages[key]
        page = storage.get(key)
        with self._lock:
            self._pages[key] = page
            while len(self._pages) > self._size:
                self._pages.popitem(last=False)
        return page

    def clear(self) -> None:
        with self._lock:
            self._pages.clear()


PAGES = PageCache()


@router.api_route("/g/{slug}", methods=["GET", "HEAD"])
def game_page(
    slug: str, session: SessionDep, storage: StorageDep, settings: SettingsDep
) -> Response:
    if not SLUG.fullmatch(slug):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no game at this link")
    found = session.execute(
        select(Export.key, Ad.shop_id)
        .join(Ad, Ad.id == Export.ad_id)
        .where(Ad.slug == slug, Ad.status == AdStatus.PUBLISHED, Export.kind == ExportKind.HOSTED)
    ).first()
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no game at this link")
    key, shop_id = found
    return serve_page(storage, settings, key, optin=shop_optin(session, settings, shop_id))


def shop_optin(session: SessionDep, settings: Settings, shop_id: uuid.UUID) -> str | None:
    shop = session.get(Shop, shop_id)
    return optin_link(settings, shop) if shop is not None else None


def serve_page(
    storage: MediaStorage,
    settings: Settings,
    key: str,
    cache: str = "public, max-age=300",
    optin: str | None = None,
) -> Response:
    """A stored game page, sandboxed; the one place it may send to is the API's anonymous
    event counter."""
    csp = f"{GAME_CSP}; connect-src {origin_of(settings.api_base_url)}"
    page = PAGES.get(storage, key)
    if optin:
        page = with_preview(page, optin_tag(optin))
    return Response(
        page,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": csp,
            "Cache-Control": cache,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )
