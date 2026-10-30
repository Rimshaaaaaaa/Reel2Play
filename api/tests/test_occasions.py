"""Seasonal themes (feature 22): the owner's pick wins, then their voice note, then the video;
the game carries the theme and the director writes for the occasion."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play.analysis import CreativeBrief, VideoAnalysis, VoiceRead
from reel2play.deps import get_storage
from reel2play.jobs.queue import run_due
from reel2play.models import Analysis, Build, Video
from reel2play.pipeline.analyze import choose_occasion
from tests.helpers import OWNER_FIELDS, ad_for

pytestmark = pytest.mark.usefixtures("stop_after_build")


def made(client: TestClient, session: Session, video: Path, key: str = "default",
         **fields: str) -> tuple[Video, CreativeBrief, Build]:  # fmt: skip
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **OWNER_FIELDS, **fields}
    response = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    )
    assert response.status_code == 201, response.text
    video_id = uuid.UUID(response.json()["id"])
    session.execute(update(Video).where(Video.id == video_id).values(sample_key=key))
    session.commit()
    run_due("test", max_jobs=20)
    ad = ad_for(session, video_id)
    brief = CreativeBrief.model_validate(
        session.scalars(select(Analysis.brief).where(Analysis.ad_id == ad.id)).one()
    )
    build = session.scalars(select(Build).where(Build.ad_id == ad.id)).one()
    found = session.get(Video, video_id)
    assert found is not None
    return found, brief, build


def test_the_owners_occasion_themes_the_game(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video, brief, build = made(client, session, sample_media["product_video"], occasion="eid")
    assert video.owner_occasion == "eid"
    assert brief.occasion == "eid"
    assert build.config["theme"] == "eid"
    html = get_storage().get(build.html_key).decode()
    assert '"theme":"eid"' in html.replace(" ", "")


def test_the_video_can_set_the_occasion_and_the_owner_overrides_it(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    _, from_video, build = made(client, session, sample_media["product_video"],
                                "independence_video")  # fmt: skip
    assert from_video.occasion == "independence_day"
    assert build.config["theme"] == "independence_day"
    _, owner_wins, _ = made(client, session, sample_media["product_video"],
                            "independence_video", occasion="winter_sale")  # fmt: skip
    assert owner_wins.occasion == "winter_sale"


def test_unknown_occasions_are_refused(client: TestClient, sample_media: dict[str, Path]) -> None:
    video = sample_media["product_video"]
    data = {"shop_name": "S", "rights_confirmed": "true", "shop_url": "https://s.pk",
            "occasion": "christmas"}  # fmt: skip
    response = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    )
    assert response.status_code == 422
    assert "ramzan" in response.json()["detail"]


def test_who_decides_the_occasion() -> None:
    reading = VideoAnalysis.model_validate(
        {
            "product": {"name": "x", "category": "shoes", "description": "", "segment_prompt": "x"},
            "brand_colors": ["#c8243a"],
            "mood": "m",
            "audience": "a",
            "tone_of_voice": "t",
            "language": {"recommended": "en"},
            "offer": {},
            "key_frames": [{"index": 0, "reason": "r"}],
            "occasion": "ramzan",
        }
    )
    voice = VoiceRead(occasion="eid")
    assert choose_occasion("wedding_season", voice, reading) == "wedding_season"
    assert choose_occasion(None, voice, reading) == "eid"
    assert choose_occasion("none", VoiceRead(), reading) == "ramzan"
