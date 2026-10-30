"""Director and cut-out steps (features 4, 5, 6, 8, 9) on the mock model and real ffmpeg."""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from reel2play import audit, brand
from reel2play.ai.media import MAX_INLINE_BYTES, media_part
from reel2play.ai.messages import MediaKind
from reel2play.analysis import Box, CreativeBrief, VideoAnalysis
from reel2play.cutout.cut import (
    CutoutError,
    box_overlap,
    choose_mask,
    clean_mask,
    cut_product,
)
from reel2play.cutout.segmenter import MaskCandidate, Sam3Client, build_segmenter
from reel2play.deps import get_storage
from reel2play.jobs import enqueue
from reel2play.jobs.queue import run_due
from reel2play.media.frames import candidate_times, dominant_colors, scene_changes
from reel2play.models import Ad, AdStatus, Analysis, BrandKit, Shop, Sprite, Video
from reel2play.net import ExternalServiceError
from reel2play.pipeline import cutout as cutout_step
from reel2play.pipeline.analyze import merge_palette
from reel2play.pipeline.runner import PIPELINE, STEP_JOB
from reel2play.settings import AIMode, MediaForModels, Settings
from tests.helpers import ad_for, trail, upload

FIXTURES = Path(__file__).resolve().parents[1] / "src/reel2play/ai/fixtures"
pytestmark = pytest.mark.usefixtures("stop_after_build")


# --- frames -------------------------------------------------------------------------------


def test_candidate_times_mix_scenes_and_even_samples() -> None:
    times = candidate_times(10.0, [2.0, 2.2, 7.5])
    assert len(times) == 6
    assert times == sorted(times)
    assert 2.15 in times
    assert all(b - a >= 0.6 for a, b in pairwise(times))
    assert candidate_times(0, []) == [0.0]
    assert len(candidate_times(1.0, [])) <= 6


def test_scene_detection_finds_the_cut(sample_media: dict[str, Path]) -> None:
    scenes = scene_changes(sample_media["product_video"])
    assert any(1.8 <= t <= 2.2 for t in scenes)


def test_dominant_colors(tmp_path: Path) -> None:
    image = np.full((50, 50, 3), (240, 240, 240), np.uint8)
    image[10:40, 10:40] = (58, 36, 200)  # BGR of #c8243a
    path = tmp_path / "x.png"
    cv2.imwrite(str(path), image)
    colors = dominant_colors(path, count=2)
    assert colors[0] == "#f0f0f0"
    assert colors[1] == "#c8243a"
    assert dominant_colors(tmp_path / "missing.png") == []


# --- whole steps on the mock --------------------------------------------------------------


def test_video_goes_through_director_and_cutout(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = upload(
        client, sample_media["product_video"], price="Rs 3,200", whatsapp_number="923001234567"
    )
    assert run_due("test") == 4
    ad = ad_for(session, video_id)
    assert ad.step == "build"
    assert ad.language == "en"
    assert trail(session, ad) == [
        "ad.created",
        "analyze.started",
        "analysis.done",
        "cutout.started",
        "cutout.done",
        "faces.unchecked",
        "track.skipped",
        "build.started",
        "game.designed",
        "build.done",
        "pipeline.stopped",
    ]

    analysis = session.scalars(select(Analysis).where(Analysis.ad_id == ad.id)).one()
    brief = CreativeBrief.model_validate(analysis.brief)
    assert brief.price == "Rs 3,200"
    assert brief.offer_text == "20% off this week"
    assert brief.offer_source == "caption"
    assert brief.cta.kind == "whatsapp"
    assert brief.palette[:3] == ["#c8243a", "#ffffff", "#1c1a36"]
    assert len(analysis.candidates) >= 2
    assert brief.key_frames[0].product_box is not None

    sprite = session.scalars(select(Sprite).where(Sprite.ad_id == ad.id)).one()
    assert sprite.method == "grabcut"
    assert sprite.quality == "lower"
    png = get_storage().get(sprite.sprite_key)
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    assert image is not None
    assert image.shape[2] == 4  # has an alpha channel
    assert image[:, :, 3].max() == 255
    assert image[0, 0, 3] == 0  # corner is transparent

    shop = session.get(Shop, ad.shop_id)
    assert shop is not None
    kit = session.get(BrandKit, shop.brand_kit_id)
    assert kit is not None
    assert kit.tone == "friendly and quick"
    message = audit.entries_for(session, "ad", ad.id)[2].data["message"]
    assert message.startswith("Found Canvas sneaker (shoes)")


def test_owner_offer_and_language_win(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = upload(
        client,
        sample_media["product_video"],
        offer="Buy 2 get 1 free",
        language="ur",
        shop_url="https://shop.example",
    )
    run_due("test")
    ad = ad_for(session, video_id)
    brief = CreativeBrief.model_validate(
        session.scalars(select(Analysis.brief).where(Analysis.ad_id == ad.id)).one()
    )
    assert brief.offer_text == "Buy 2 get 1 free"
    assert brief.offer_source == "owner"
    assert brief.language == "ur"
    assert brief.price is None
    assert brief.cta.kind == "link"


def test_photos_go_through_the_pipeline(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    response = client.post(
        "/api/uploads",
        data={"shop_name": "Photo Shop", "rights_confirmed": "true", "shop_url": "https://x.pk"},
        files=[
            ("files", ("a.jpg", sample_media["photo_jpg"].read_bytes())),
            ("files", ("b.png", sample_media["photo_png"].read_bytes())),
        ],
    )
    run_due("test")
    ad = ad_for(session, uuid.UUID(response.json()["id"]))
    assert "cutout.done" in trail(session, ad)


class FixtureEditor:
    """A writable copy of the mock director fixture."""

    def __init__(self, directory: Path) -> None:
        self.path = directory / "director_analyze.json"
        self.data: dict[str, Any] = json.loads((FIXTURES / "director_analyze.json").read_text())

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data))


@pytest.fixture
def director_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FixtureEditor]:
    from reel2play.ai import client as ai_client

    for name in ("director_analyze", "model_check"):
        (tmp_path / f"{name}.json").write_text((FIXTURES / f"{name}.json").read_text())
    monkeypatch.setattr("reel2play.ai.providers.FIXTURES_DIR", tmp_path)
    ai_client.get_ai.cache_clear()
    yield FixtureEditor(tmp_path)
    ai_client.get_ai.cache_clear()


def test_bad_key_frame_picks_fall_back_to_the_sharpest(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    director_fixture: FixtureEditor,
) -> None:
    answer = director_fixture.data["default"]["text"]
    answer["key_frames"] = [{"index": 40, "reason": "not a real frame"}]
    answer["logo"] = {
        "present": True,
        "frame_index": 0,
        "box": {"x0": 0.2, "y0": 0.3, "x1": 0.8, "y1": 0.7},
    }
    director_fixture.save()
    video_id = upload(client, sample_media["product_video"], shop_url="https://s.pk")
    run_due("test")
    ad = ad_for(session, video_id)
    brief = CreativeBrief.model_validate(
        session.scalars(select(Analysis.brief).where(Analysis.ad_id == ad.id)).one()
    )
    assert brief.key_frames[0].reason.startswith("The sharpest frame")
    assert brief.logo_key is not None
    assert get_storage().exists(brief.logo_key)
    assert "cutout.done" in trail(session, ad)


def test_unreadable_director_answer_fails_the_ad(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    director_fixture: FixtureEditor,
) -> None:
    director_fixture.data["default"] = {"text": "I cannot help with that."}
    director_fixture.save()
    video_id = upload(client, sample_media["product_video"], shop_url="https://s.pk")
    for _ in range(4):
        run_due("test")
        session.execute(text("UPDATE jobs SET run_after = now() - interval '1s'"))
        session.commit()
    ad = ad_for(session, video_id)
    assert ad.status == AdStatus.FAILED
    assert "JSON" in (ad.error or "")
    assert trail(session, ad)[-1] == "ad.failed"


def test_cutout_without_an_analysis_fails_at_once(session: Session, client: TestClient) -> None:
    shop = Shop(name="S")
    session.add(shop)
    session.flush()
    video = Video(shop_id=shop.id, rights_confirmed=True)
    session.add(video)
    session.flush()
    ad = Ad(shop_id=shop.id, video_id=video.id)
    session.add(ad)
    session.flush()
    enqueue(session, STEP_JOB, {"ad_id": str(ad.id), "step": "cutout"})
    session.commit()
    run_due("test")
    ad = session.get(Ad, ad.id)  # type: ignore[assignment]
    session.refresh(ad)
    assert ad.status == AdStatus.FAILED
    assert "has not read this video" in (ad.error or "")


def test_unprepared_video_cannot_be_analyzed(session: Session) -> None:
    shop = Shop(name="S")
    session.add(shop)
    session.flush()
    video = Video(shop_id=shop.id, rights_confirmed=True)
    session.add(video)
    session.flush()
    ad = Ad(shop_id=shop.id, video_id=video.id)
    session.add(ad)
    session.flush()
    enqueue(session, STEP_JOB, {"ad_id": str(ad.id), "step": "analyze"})
    session.commit()
    run_due("test")
    session.refresh(ad)
    assert ad.status == AdStatus.FAILED
    assert ad.error == "the video was not prepared"


def test_finished_ads_are_left_alone(session: Session) -> None:
    shop = Shop(name="S")
    session.add(shop)
    session.flush()
    video = Video(shop_id=shop.id)
    session.add(video)
    session.flush()
    ad = Ad(shop_id=shop.id, video_id=video.id, status=AdStatus.PUBLISHED)
    session.add(ad)
    session.flush()
    enqueue(session, STEP_JOB, {"ad_id": str(ad.id), "step": "analyze"})
    enqueue(session, STEP_JOB, {"ad_id": str(uuid.uuid4()), "step": "analyze"})
    session.commit()
    assert run_due("test") == 2
    session.refresh(ad)
    assert ad.status == AdStatus.PUBLISHED


def test_pipeline_order() -> None:
    assert PIPELINE.order[:2] == ["analyze", "cutout"]
    assert PIPELINE.after("analyze") == "cutout"


# --- cut-out pieces -----------------------------------------------------------------------


def _product_frame() -> bytes:
    image = np.full((320, 240, 3), (235, 235, 235), np.uint8)
    cv2.ellipse(image, (120, 170), (70, 45), 0, 0, 360, (40, 60, 190), -1)
    ok, jpeg = cv2.imencode(".jpg", image)
    assert ok
    return jpeg.tobytes()


class FakeSegmenter:
    name = "sam3.1"

    def __init__(self, masks: list[MaskCandidate]) -> None:
        self.masks = masks
        self.prompts: list[str] = []

    def segment(self, image_jpeg: bytes, prompt: str) -> list[MaskCandidate]:
        self.prompts.append(prompt)
        return self.masks


def _ellipse_mask() -> np.ndarray:
    mask = np.zeros((320, 240), np.uint8)
    cv2.ellipse(mask, (120, 170), (70, 45), 0, 0, 360, 1, -1)
    return mask.astype(bool)


def test_cut_with_sam_masks_is_good_quality() -> None:
    whole = np.ones((320, 240), bool)
    tiny = np.zeros((320, 240), bool)
    tiny[0, 0] = True
    segmenter = FakeSegmenter(
        [
            MaskCandidate(whole, 0.99),  # covers everything: rejected
            MaskCandidate(tiny, 0.95),  # too small: rejected
            MaskCandidate(_ellipse_mask(), 0.8),
        ]
    )
    result = cut_product(_product_frame(), "shoe", None, segmenter)
    assert result.method == "sam3.1"
    assert result.quality == "good"
    assert result.score == 0.8
    assert 0.1 < result.area_fraction < 0.2
    assert segmenter.prompts == ["shoe"]


def test_cut_falls_back_when_sam_finds_nothing() -> None:
    result = cut_product(
        _product_frame(), "shoe", Box(x0=0.1, y0=0.3, x1=0.9, y1=0.8), FakeSegmenter([])
    )
    assert result.method == "grabcut"
    assert result.quality == "lower"
    assert 0.08 < result.area_fraction < 0.3


def test_cut_errors() -> None:
    with pytest.raises(CutoutError, match="could not be read"):
        cut_product(b"not an image", "shoe", None, None)
    blank = np.full((100, 100, 3), 200, np.uint8)
    ok, jpeg = cv2.imencode(".jpg", blank)
    assert ok
    with pytest.raises(CutoutError, match="could not be separated"):
        cut_product(jpeg.tobytes(), "shoe", None, FakeSegmenter([]))


def test_mask_helpers() -> None:
    mask = _ellipse_mask()
    assert box_overlap(mask, None) == 1.0
    assert box_overlap(mask, Box(x0=0.0, y0=0.0, x1=0.1, y1=0.1)) == 0.0
    noisy = mask.copy()
    noisy[5:8, 5:8] = True
    assert not clean_mask(noisy)[6, 6]
    assert not clean_mask(np.zeros((10, 10), bool)).any()
    inside = MaskCandidate(mask, 0.6)
    elsewhere = np.zeros((320, 240), bool)
    elsewhere[0:60, 0:60] = True
    picked = choose_mask(
        [MaskCandidate(elsewhere, 0.7), inside], Box(x0=0.2, y0=0.35, x1=0.8, y1=0.75)
    )
    assert picked is inside


def test_sam_client_round_trip() -> None:
    mask = _ellipse_mask().astype(np.uint8) * 255
    ok, png = cv2.imencode(".png", cv2.resize(mask, (120, 160)))
    assert ok
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "width": 240,
                "height": 320,
                "masks": [
                    {
                        "score": 0.91,
                        "box": [50, 125, 190, 215],
                        "mask_png": base64.b64encode(png.tobytes()).decode(),
                    }
                ],
            },
        )

    client = Sam3Client(
        "https://ws--sam.modal.run",
        "id.secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    masks = client.segment(_product_frame(), "shoe")
    assert seen[0].headers["authorization"] == "Bearer id.secret"
    assert json.loads(seen[0].content)["prompt"] == "shoe"
    assert masks[0].mask.shape == (320, 240)
    assert masks[0].score == 0.91
    assert masks[0].mask[170, 120]


def test_sam_client_errors() -> None:
    def bad_mask(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"width": 2, "height": 2, "masks": [{"score": 1, "mask_png": "AAAA"}]}
        )

    client = Sam3Client(
        "https://x", "t", client=httpx.Client(transport=httpx.MockTransport(bad_mask))
    )
    with pytest.raises(ExternalServiceError, match="could not be decoded"):
        client.segment(b"x", "shoe")
    no_list = Sam3Client(
        "https://x",
        "t",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"width": 1, "height": 1})
            )
        ),
    )
    with pytest.raises(ExternalServiceError, match="no masks"):
        no_list.segment(b"x", "shoe")


def test_build_segmenter() -> None:
    assert build_segmenter(Settings(ai_mode=AIMode.MOCK)) is None
    assert build_segmenter(Settings(ai_mode=AIMode.LIVE)) is None
    live = build_segmenter(
        Settings(ai_mode=AIMode.LIVE, sam_url="https://s", modal_proxy_token=SecretStr("a.b"))
    )
    assert isinstance(live, Sam3Client)


def test_cutout_step_uses_sam_when_available(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_sam(_: Settings) -> FakeSegmenter:
        mask = np.zeros((640, 360), bool)
        mask[250:390, 100:260] = True
        return FakeSegmenter([MaskCandidate(mask, 0.88)])

    monkeypatch.setattr(cutout_step.SEGMENTER, "build", fake_sam)
    video_id = upload(client, sample_media["product_video"], shop_url="https://s.pk")
    run_due("test")
    ad = ad_for(session, video_id)
    sprite = session.scalars(select(Sprite).where(Sprite.ad_id == ad.id)).one()
    assert sprite.method == "sam3.1"
    assert sprite.quality == "good"
    assert "SAM 3.1" in audit.entries_for(session, "ad", ad.id)[4].data["message"]


# --- small helpers ------------------------------------------------------------------------


def test_media_part_modes(tmp_path: Path) -> None:
    storage = get_storage()
    storage.put("t/a.jpg", b"jpeg", "image/jpeg")
    inline = media_part(storage, Settings(), "t/a.jpg", MediaKind.IMAGE, "image/jpeg")
    assert inline is not None
    assert inline.url == "data:image/jpeg;base64,anBlZw=="
    signed = media_part(
        storage,
        Settings(media_for_models=MediaForModels.SIGNED_URL),
        "t/a.jpg",
        MediaKind.IMAGE,
        "image/jpeg",
    )
    assert signed is not None
    assert "/media/t/a.jpg?exp=" in signed.url
    storage.put("t/big.mp4", b"0" * (MAX_INLINE_BYTES + 1), "video/mp4")
    assert media_part(storage, Settings(), "t/big.mp4", MediaKind.VIDEO, "video/mp4") is None


def test_brand_kit_describe_and_update(session: Session) -> None:
    shop = Shop(name="Kit Shop")
    session.add(shop)
    session.flush()
    assert brand.describe(None).startswith("none yet")
    kit = brand.save_kit(session, shop, ["#000000"], "calm", "shops/x/logo.png")
    assert shop.brand_kit_id == kit.id
    again = brand.save_kit(session, shop, ["#ffffff"], "loud", None)
    assert again.id == kit.id
    assert again.logo_key == "shops/x/logo.png"
    assert "colours #ffffff" in brand.describe(again)
    assert "a saved logo" in brand.describe(again)


def test_analysis_schema_rules() -> None:
    answer = json.loads((FIXTURES / "director_analyze.json").read_text())["default"]["text"]
    answer["brand_colors"] = ["red", "#ABCDEF"]
    answer["on_screen_text"] = ["  20% OFF  ", " "]
    parsed = VideoAnalysis.model_validate(answer)
    assert parsed.brand_colors == ["#abcdef"]
    assert parsed.on_screen_text == ["20% OFF"]
    with pytest.raises(ValueError, match="#rrggbb"):
        VideoAnalysis.model_validate({**answer, "brand_colors": ["red"]})
    with pytest.raises(ValueError, match="x1 > x0"):
        Box(x0=0.5, y0=0.1, x1=0.4, y1=0.2)
    assert Box(x0=0, y0=0, x1=0.5, y1=0.5).to_pixels(100, 200) == (0, 0, 50, 100)
    assert merge_palette(["#111111", "#222222"], ["#222222", "#333333"]) == [
        "#111111",
        "#222222",
        "#333333",
    ]


def test_ad_status_endpoint(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = upload(
        client, sample_media["video_with_audio"], price="Rs 999", shop_url="https://s.pk"
    )
    run_due("test")
    video = client.get(f"/api/videos/{video_id}").json()
    assert video["ad_id"]
    body = client.get(f"/api/ads/{video['ad_id']}").json()
    assert body["step"] == "build"
    assert body["brief"]["price"] == "Rs 999"
    assert body["brief"]["product"] == "Canvas sneaker"
    assert body["sprites"][0]["url"].startswith("http://testserver/media/")
    assert [p["action"] for p in body["progress"]][:3] == [
        "ad.created",
        "analyze.started",
        "analysis.done",
    ]
    assert client.get(f"/api/ads/{uuid.uuid4()}").status_code == 404


def test_ad_without_analysis_has_no_brief(client: TestClient, session: Session) -> None:
    shop = Shop(name="S")
    session.add(shop)
    session.flush()
    video = Video(shop_id=shop.id)
    session.add(video)
    session.flush()
    ad = Ad(shop_id=shop.id, video_id=video.id)
    session.add(ad)
    session.commit()
    body = client.get(f"/api/ads/{ad.id}").json()
    assert body["brief"] is None
    assert body["sprites"] == []
