"""Upload endpoint (feature 1) and upload status."""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from reel2play.agency import brand_for, member_for_key
from reel2play.analysis import Occasion
from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.intake.upload import (
    VOICE_MAX_BYTES,
    Brief,
    UploadLimits,
    UploadRejectedError,
    accept_upload,
    classify,
)
from reel2play.models import Ad, AgencyRole, Shop, Video
from reel2play.shops import issue_key, key_matches

router = APIRouter(prefix="/api", tags=["uploads"])


class VideoOut(BaseModel):
    id: uuid.UUID
    shop_id: uuid.UUID
    kind: str
    status: str
    error: str | None
    duration_s: float | None
    rights_confirmed: bool
    audio_removed: bool
    is_synthetic: bool
    ad_id: uuid.UUID | None = None
    # Given once, when a web upload makes a new shop: the browser keeps it for the studio.
    shop_key: str | None = None


def video_out(video: Video, ad_id: uuid.UUID | None = None) -> VideoOut:
    return VideoOut(
        ad_id=ad_id,
        id=video.id,
        shop_id=video.shop_id,
        kind=video.kind,
        status=video.status,
        error=video.error,
        duration_s=video.duration_s,
        rights_confirmed=video.rights_confirmed,
        audio_removed=video.audio_removed,
        is_synthetic=video.is_synthetic,
    )


async def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadRejectedError(f"Each file must be under {max_bytes // (1024 * 1024)} MB.")
    return data


def check_shop(
    session: SessionDep, shop_id: uuid.UUID | None, key: str | None, agency_key: str | None = None
) -> None:
    """Uploading to an existing shop needs that shop's studio key, or (feature 47) the key of
    an editor in the agency that manages the brand."""
    if shop_id is None:
        return
    shop = session.get(Shop, shop_id)
    if shop is not None and key_matches(shop, key):
        return
    member = member_for_key(session, agency_key)
    if member is not None and brand_for(session, member, shop_id, AgencyRole.EDITOR):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "This browser is not linked to that shop.")


def unprocessable(exc: ValidationError | UploadRejectedError) -> HTTPException:
    if isinstance(exc, ValidationError):
        message = "; ".join(str(e["msg"]).removeprefix("Value error, ") for e in exc.errors())
    else:
        message = str(exc)
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def accept_from_web(
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    brief: Brief,
    contents: list[bytes],
    *,
    source: str = "web",
    voice: bytes | None = None,
) -> VideoOut:
    """Store an upload from the web page (or an import) and hand a new shop its studio key."""
    try:
        limits = UploadLimits(settings.max_upload_bytes, settings.max_photos)
        files = classify(contents, limits)
        video = accept_upload(session, storage, brief, files, source=source, voice=voice)
    except UploadRejectedError as exc:
        raise unprocessable(exc) from exc
    out = video_out(video)
    owner = session.get(Shop, video.shop_id)
    if brief.shop_id is None and owner is not None and owner.access_key_hash is None:
        out.shop_key = issue_key(owner)
    return out


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def create_upload(
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    files: Annotated[list[UploadFile], File(description="One video, or product photos")],
    shop_name: Annotated[str, Form()],
    rights_confirmed: Annotated[bool, Form()] = False,
    shop_id: Annotated[uuid.UUID | None, Form()] = None,
    voice_note: Annotated[
        UploadFile | None, File(description="Optional voice note about the offer")
    ] = None,
    language: Annotated[str, Form()] = "auto",
    whatsapp_number: Annotated[str | None, Form()] = None,
    shop_url: Annotated[str | None, Form()] = None,
    price: Annotated[str | None, Form()] = None,
    offer: Annotated[str | None, Form()] = None,
    catalog: Annotated[bool, Form()] = False,
    occasion: Annotated[str, Form()] = "none",
    lab: Annotated[bool, Form()] = False,
    x_shop_key: Annotated[str | None, Header()] = None,
    x_agency_key: Annotated[str | None, Header()] = None,
) -> VideoOut:
    check_shop(session, shop_id, x_shop_key, x_agency_key)
    try:
        brief = Brief(
            shop_name=shop_name,
            shop_id=shop_id,
            language=language,
            whatsapp_number=whatsapp_number,
            shop_url=shop_url,
            price=price,
            offer=offer,
            rights_confirmed=rights_confirmed,
            catalog=catalog,
            occasion=cast(Occasion, occasion),  # checked by Brief
            lab=lab,
        )
        contents = [await _read_limited(f, settings.max_upload_bytes) for f in files]
        voice = await _read_limited(voice_note, VOICE_MAX_BYTES) if voice_note else None
    except (ValidationError, UploadRejectedError) as exc:
        raise unprocessable(exc) from exc
    return accept_from_web(session, storage, settings, brief, contents, voice=voice)


@router.get("/videos/{video_id}")
def get_video(video_id: uuid.UUID, session: SessionDep) -> VideoOut:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "video not found")
    ad_id = session.scalars(
        select(Ad.id).where(Ad.video_id == video.id).order_by(Ad.created_at.desc())
    ).first()
    return video_out(video, ad_id)
