"""Instagram and Facebook import (feature 3): sign in with Facebook, pick a post, make a game.

The sign-in session travels in the ``X-Import-Session`` header. The callback hands it to the
web page in the address's fragment, which browsers never send to a server, and the page
removes it from the address bar straight away.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ValidationError

from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.intake.meta_import import (
    IMPORTERS,
    SESSIONS,
    ImportPost,
    ImportSession,
    PostNotImportableError,
    importer_error,
)
from reel2play.intake.upload import Brief, UploadRejectedError
from reel2play.net import ExternalServiceError
from reel2play.routes.uploads import VideoOut, accept_from_web, check_shop, unprocessable
from reel2play.settings import Settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/import/meta", tags=["import"])

SessionHeader = Annotated[str | None, Header(alias="X-Import-Session")]


class ImportStatus(BaseModel):
    enabled: bool


class UsePost(BaseModel):
    post_id: str
    shop_name: str
    shop_id: uuid.UUID | None = None
    language: str = "auto"
    whatsapp_number: str | None = None
    shop_url: str | None = None
    price: str | None = None
    offer: str | None = None
    rights_confirmed: bool = False
    occasion: str = "none"


def _ready(settings: Settings) -> None:
    if not settings.meta_import_ready:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Importing from Instagram or Facebook is not set up on this server.",
        )


def _session(sid: str | None) -> ImportSession:
    found = SESSIONS.get(sid) if sid else None
    if found is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Your Facebook sign-in has ended. Sign in again."
        )
    return found


def _back_to_web(settings: Settings, fragment: dict[str, str]) -> RedirectResponse:
    page = f"{settings.web_base_url.rstrip('/')}/import#{urlencode(fragment)}"
    return RedirectResponse(page, status.HTTP_303_SEE_OTHER)


@router.get("/status")
def import_status(settings: SettingsDep) -> ImportStatus:
    return ImportStatus(enabled=settings.meta_import_ready)


@router.get("/start")
def start(settings: SettingsDep) -> RedirectResponse:
    _ready(settings)
    return RedirectResponse(IMPORTERS().login_url(SESSIONS.new_state()), status.HTTP_303_SEE_OTHER)


@router.get("/callback")
def callback(
    settings: SettingsDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    _ready(settings)
    if error or not code:
        return _back_to_web(settings, {"error": "denied"})
    if not state or not SESSIONS.take_state(state):
        return _back_to_web(settings, {"error": "expired"})
    try:
        token = IMPORTERS().exchange(code)
    except ExternalServiceError as exc:
        log.warning("Facebook sign-in failed with status %s", exc.status)
        return _back_to_web(settings, {"error": "failed"})
    return _back_to_web(settings, {"session": SESSIONS.open(token)})


@router.get("/posts")
def posts(settings: SettingsDep, x_import_session: SessionHeader = None) -> list[ImportPost]:
    _ready(settings)
    found = _session(x_import_session)
    try:
        return IMPORTERS().posts(found)
    except ExternalServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, importer_error(exc)) from exc


@router.post("/use", status_code=status.HTTP_201_CREATED)
def use(
    body: UsePost,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    x_import_session: SessionHeader = None,
    x_shop_key: Annotated[str | None, Header()] = None,
) -> VideoOut:
    _ready(settings)
    found = _session(x_import_session)
    check_shop(session, body.shop_id, x_shop_key)
    try:
        brief = Brief(**body.model_dump(exclude={"post_id"}))
    except ValidationError as exc:
        raise unprocessable(exc) from exc
    if not brief.rights_confirmed:
        raise unprocessable(UploadRejectedError("Please confirm the video is yours to use."))
    importer = IMPORTERS()
    try:
        data = importer.download(importer.file_url(found, body.post_id), settings.max_upload_bytes)
    except PostNotImportableError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ExternalServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, importer_error(exc)) from exc
    source = "instagram" if body.post_id.startswith("ig:") else "facebook"
    return accept_from_web(session, storage, settings, brief, [data], source=source)
