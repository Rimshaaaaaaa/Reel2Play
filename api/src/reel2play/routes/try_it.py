"""The try-it page for judges (feature 60): pick a sample video and watch every agent work.

Samples are listed in samples/manifest.json. Synthetic ones say so on the page; real ones
come only from shops that agreed. A try-it run is an ordinary upload marked synthetic, and
only a few may run at once.
"""

from __future__ import annotations

import json
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from reel2play.db import utcnow
from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.intake.upload import Brief, UploadLimits, accept_upload, classify
from reel2play.models import Ad, Video
from reel2play.pipeline.runner import TERMINAL
from reel2play.routes.uploads import VideoOut, video_out
from reel2play.settings import AIMode, Settings

router = APIRouter(prefix="/api", tags=["try-it"])
TRY_SOURCE = "try"
DEMO_LINK = "https://example.com/"  # reserved for examples: the samples' order button
RUNNING_WINDOW = timedelta(minutes=10)


class Sample(BaseModel):
    key: str
    title: str
    about: str
    file: str
    mock_key: str
    shop_name: str
    language: str
    price: str
    offer: str
    synthetic: bool
    mock_only: bool
    source: str


class SampleOut(BaseModel):
    key: str
    title: str
    about: str
    language: str
    synthetic: bool
    source: str
    video_url: str


class TryIn(BaseModel):
    sample: str


@lru_cache(maxsize=4)
def load_samples(directory: Path) -> tuple[Sample, ...]:
    data = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return tuple(Sample.model_validate(item) for item in data["samples"])


def offered(settings: Settings) -> list[Sample]:
    """Mock-only samples show recorded answers, so they are hidden when real models run."""
    samples = load_samples(settings.samples_dir)
    return [s for s in samples if settings.ai_mode is AIMode.MOCK or not s.mock_only]


def find(settings: Settings, key: str) -> Sample:
    sample = next((s for s in offered(settings) if s.key == key), None)
    if sample is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such sample")
    return sample


@router.get("/samples")
def samples(settings: SettingsDep) -> list[SampleOut]:
    base = settings.api_base_url.rstrip("/")
    return [
        SampleOut(
            key=s.key,
            title=s.title,
            about=s.about,
            language=s.language,
            synthetic=s.synthetic,
            source=s.source,
            video_url=f"{base}/api/samples/{s.key}/video",
        )
        for s in offered(settings)
    ]


@router.get("/samples/{key}/video")
def sample_video(key: str, settings: SettingsDep) -> FileResponse:
    sample = find(settings, key)
    return FileResponse(settings.samples_dir / sample.file, media_type="video/mp4")


def running(session: SessionDep) -> int:
    since = utcnow() - RUNNING_WINDOW
    count = session.scalar(
        select(func.count(Video.id))
        .outerjoin(Ad, Ad.video_id == Video.id)
        .where(
            Video.source == TRY_SOURCE,
            Video.created_at > since,
            or_(Ad.id.is_(None), Ad.status.not_in([s.value for s in TERMINAL])),
        )
    )
    return int(count or 0)


@router.post("/try", status_code=status.HTTP_201_CREATED)
def try_sample(
    body: TryIn, session: SessionDep, storage: StorageDep, settings: SettingsDep
) -> VideoOut:
    sample = find(settings, body.sample)
    if running(session) >= settings.max_try_running:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "A few games are being made right now. Try again in a minute.",
        )
    data = (settings.samples_dir / sample.file).read_bytes()
    files = classify([data], UploadLimits(settings.max_upload_bytes, settings.max_photos))
    brief = Brief(
        shop_name=sample.shop_name,
        language=sample.language,
        shop_url=DEMO_LINK,
        price=sample.price or None,
        offer=sample.offer or None,
        rights_confirmed=True,  # our own synthetic video, or a shop that agreed
    )
    video = accept_upload(
        session, storage, brief, files, source=TRY_SOURCE, synthetic=sample.synthetic
    )
    video.sample_key = sample.mock_key
    return video_out(video)
