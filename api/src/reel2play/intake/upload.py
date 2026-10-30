"""Upload (feature 1): a Reel, a product video, or product photos, with the owner's brief."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.analysis import Occasion
from reel2play.jobs import enqueue
from reel2play.media.storage import MediaStorage
from reel2play.models import CtaKind, Shop, Video, VideoKind, VideoStatus

PREPARE_JOB = "video.prepare"


class UploadRejectedError(ValueError):
    """The upload cannot be accepted; the message is safe to show to the shop."""


class MediaType(StrEnum):
    MP4 = "video/mp4"
    QUICKTIME = "video/quicktime"
    WEBM = "video/webm"
    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"

    @property
    def is_video(self) -> bool:
        return self.value.startswith("video/")

    @property
    def extension(self) -> str:
        return {
            "video/mp4": "mp4",
            "video/quicktime": "mov",
            "video/webm": "webm",
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }[self.value]


def sniff(head: bytes) -> MediaType | None:
    """Identify the file from its first bytes; the browser's declared type is not trusted."""
    if head[4:8] == b"ftyp":
        return MediaType.QUICKTIME if head[8:10] == b"qt" else MediaType.MP4
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return MediaType.WEBM
    if head.startswith(b"\xff\xd8\xff"):
        return MediaType.JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return MediaType.PNG
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return MediaType.WEBP
    return None


_PHONE = re.compile(r"^\+?[0-9]{10,15}$")


class Brief(BaseModel):
    """What the owner tells us. The price is kept exactly as typed; the game shows it as-is."""

    shop_name: str = Field(min_length=1, max_length=120)
    shop_id: uuid.UUID | None = None
    language: str = Field(default="auto", pattern=r"^(auto|ur|en)$")
    whatsapp_number: str | None = None
    shop_url: str | None = Field(default=None, max_length=500)
    price: str | None = Field(default=None, max_length=40)
    offer: str | None = Field(default=None, max_length=200)
    rights_confirmed: bool = False
    # Feature 11: several photos of different products, not several views of one.
    catalog: bool = False
    # Feature 22: a seasonal theme for the game.
    occasion: Occasion = "none"
    # Feature 46: in a batch, the owner may name each product.
    product_name: str | None = Field(default=None, max_length=60)
    # Feature 24: an experimental game with a mechanic the director invents.
    lab: bool = False

    @field_validator("whatsapp_number")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        digits = re.sub(r"[\s\-()]", "", value)
        if not _PHONE.match(digits):
            raise ValueError("WhatsApp number must have 10 to 15 digits, like 923001234567")
        return digits.lstrip("+")

    @field_validator("shop_url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        if not value.startswith("https://"):
            raise ValueError("shop link must start with https://")
        return value.strip()

    @field_validator("price", "offer", "product_name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


@dataclass(frozen=True)
class IncomingFile:
    data: bytes
    media_type: MediaType


@dataclass(frozen=True)
class UploadLimits:
    max_bytes: int
    max_photos: int


def classify(files: list[bytes], limits: UploadLimits) -> list[IncomingFile]:
    if not files:
        raise UploadRejectedError("Please choose a video or some product photos.")
    incoming: list[IncomingFile] = []
    for data in files:
        if len(data) > limits.max_bytes:
            raise UploadRejectedError(
                f"Each file must be under {limits.max_bytes // (1024 * 1024)} MB."
            )
        media_type = sniff(data[:16])
        if media_type is None:
            raise UploadRejectedError(
                "Only MP4, MOV or WebM videos and JPG, PNG or WebP photos can be used."
            )
        incoming.append(IncomingFile(data, media_type))
    videos = [f for f in incoming if f.media_type.is_video]
    if videos and len(incoming) > 1:
        raise UploadRejectedError("Send one video, or photos only, not both.")
    if not videos and len(incoming) > limits.max_photos:
        raise UploadRejectedError(f"Send at most {limits.max_photos} photos.")
    return incoming


# --- the owner's voice note (feature 10) ---------------------------------------------------

VOICE_MAX_BYTES = 10 * 1024 * 1024
VOICE_PROBLEM = "The voice note must be an audio file (MP3, M4A, OGG, WebM or WAV) under 10 MB."


def sniff_voice(head: bytes) -> str | None:
    """The voice note's file extension from its first bytes, or None when it is not audio
    we can read. Containers that can also hold video are checked again when it is prepared."""
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "mp3"
    if head.startswith(b"OggS"):
        return "ogg"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "wav"
    if head[4:8] == b"ftyp":
        return "m4a"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    return None


def check_voice(data: bytes) -> str:
    """The voice note's extension, or why it cannot be used."""
    kind = sniff_voice(data[:16])
    if not data or len(data) > VOICE_MAX_BYTES or kind is None:
        raise UploadRejectedError(VOICE_PROBLEM)
    return kind


def _shop_for(session: Session, brief: Brief, synthetic: bool) -> Shop:
    if brief.shop_id is not None:
        shop = session.get(Shop, brief.shop_id)
        if shop is None:
            raise UploadRejectedError("That shop was not found.")
        return shop
    shop = Shop(
        name=brief.shop_name,
        language=brief.language,
        whatsapp_number=brief.whatsapp_number,
        shop_url=brief.shop_url,
        is_synthetic=synthetic,
    )
    session.add(shop)
    session.flush()
    return shop


def accept_upload(
    session: Session,
    storage: MediaStorage,
    brief: Brief,
    files: list[IncomingFile],
    *,
    source: str = "web",
    synthetic: bool = False,
    voice: bytes | None = None,
    batch_id: uuid.UUID | None = None,
) -> Video:
    """Store the files privately, record the upload, and queue its preparation."""
    if not brief.rights_confirmed:
        raise UploadRejectedError("Please confirm the video is yours to use before we start.")
    voice_kind = check_voice(voice) if voice is not None else None
    shop = _shop_for(session, brief, synthetic)
    video_id = uuid.uuid4()
    is_video = files[0].media_type.is_video
    keys = [
        f"videos/{video_id}/{'original' if is_video else f'photo-{i}'}.{f.media_type.extension}"
        for i, f in enumerate(files)
    ]
    for key, item in zip(keys, files, strict=True):
        storage.put(key, item.data, item.media_type.value)
    voice_key = f"videos/{video_id}/voice-original.{voice_kind}" if voice_kind else None
    if voice is not None and voice_key is not None:
        storage.put(voice_key, voice, "application/octet-stream")
    cta_target = brief.whatsapp_number or brief.shop_url
    video = Video(
        id=video_id,
        shop_id=shop.id,
        kind=VideoKind.VIDEO if is_video else VideoKind.PHOTOS,
        status=VideoStatus.UPLOADED,
        original_key=keys[0] if is_video else None,
        photo_keys=[] if is_video else keys,
        rights_confirmed=True,
        audio_removed=not is_video,
        owner_price=brief.price,
        owner_offer=brief.offer,
        cta_kind=CtaKind.WHATSAPP if brief.whatsapp_number else CtaKind.LINK,
        cta_target=cta_target,
        source=source,
        is_synthetic=synthetic,
        voice_original_key=voice_key,
        catalog=brief.catalog and not is_video and len(files) > 1,
        owner_occasion=None if brief.occasion == "none" else brief.occasion,
        owner_product=brief.product_name,
        batch_id=batch_id,
        lab=brief.lab,
    )
    session.add(video)
    session.flush()
    audit.record(
        session,
        actor="shop",
        action="upload.received",
        subject_type="video",
        subject_id=video.id,
        data={
            "kind": video.kind,
            "files": len(files),
            "source": source,
            "rights_confirmed": True,
            "voice_note": voice_key is not None,
        },
    )
    enqueue(session, PREPARE_JOB, {"video_id": str(video.id)})
    return video
