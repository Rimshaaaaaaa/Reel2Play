"""Blur for bystanders' faces (feature 55): SAM 3.1 finds faces, code blurs every one that is
not part of the product, and without SAM the game never shows a frame of the video.

The pictures here are synthetic: flat shapes standing in for a product and for faces."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from numpy.typing import NDArray
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.builder.assets import plain_photo_data_url
from reel2play.cutout.faces import FaceState, check_faces
from reel2play.cutout.segmenter import (
    FACE_MASKS,
    MaskCandidate,
    Sam3Client,
    build_face_finder,
)
from reel2play.deps import get_storage
from reel2play.jobs.queue import run_due
from reel2play.models import Sprite
from reel2play.net import ExternalServiceError
from reel2play.pipeline import cutout as cutout_step
from reel2play.pipeline.build import game_assets
from reel2play.pipeline.runner import _context
from reel2play.pipeline.state import latest_brief
from reel2play.settings import AIMode, Settings
from tests.helpers import ad_for, trail, upload

W, H = 360, 640


def synthetic_frame() -> NDArray[np.uint8]:
    """A textured synthetic frame: stripes, so blurring is easy to measure."""
    frame = np.zeros((H, W, 3), np.uint8)
    frame[:, :, 0] = (np.arange(W) * 7 % 255)[None, :]
    frame[:, :, 1] = (np.arange(H) * 5 % 255)[:, None]
    frame[::4, :, 2] = 255
    return frame


def jpeg(frame: NDArray[np.uint8]) -> bytes:
    ok, data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    return data.tobytes()


def box_mask(x0: int, y0: int, x1: int, y1: int) -> NDArray[np.bool_]:
    mask = np.zeros((H, W), bool)
    mask[y0:y1, x0:x1] = True
    return mask


BYSTANDER = box_mask(20, 30, 90, 110)  # in the corner, away from the product
ON_PRODUCT = box_mask(150, 300, 210, 360)  # well inside the product
PRODUCT = box_mask(120, 260, 260, 460)


class FakeFaces:
    name = "sam3.1"

    def __init__(self, faces: list[NDArray[np.bool_]], fail: bool = False) -> None:
        self.faces = faces
        self.fail = fail
        self.prompts: list[str] = []

    def segment(self, image_jpeg: bytes, prompt: str) -> list[MaskCandidate]:
        self.prompts.append(prompt)
        if self.fail:
            raise ExternalServiceError("SAM 3.1 on Modal", "HTTP 503", status=503)
        return [MaskCandidate(face, 0.9) for face in self.faces]


def resaved(data: bytes) -> bytes:
    ok, again = cv2.imencode(".jpg", decode(data), [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return again.tobytes()


def roughness(image: NDArray[np.uint8], mask: NDArray[np.bool_]) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    edges = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
    return float(edges[mask].mean())


def decode(data: bytes) -> NDArray[np.uint8]:
    return np.asarray(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), np.uint8)


def test_bystanders_are_blurred_and_the_rest_of_the_frame_is_kept() -> None:
    frame = synthetic_frame()
    finder = FakeFaces([BYSTANDER, ON_PRODUCT, np.zeros((H, W), bool)])
    check = check_faces(jpeg(frame), PRODUCT, finder, keep_product_faces=False)
    assert finder.prompts == ["face"]
    assert (check.found, check.blurred, check.kept, check.touches_product) == (2, 2, 0, True)
    after = decode(check.frame_jpeg)
    # The same frame saved the same way, without the blur: only the faces differ.
    before = decode(resaved(jpeg(frame)))
    assert roughness(after, BYSTANDER) < roughness(before, BYSTANDER) * 0.25
    far = box_mask(250, 20, 350, 120)  # nowhere near a face
    assert np.abs(after[far].astype(int) - before[far].astype(int)).mean() < 1


def test_a_face_that_shows_a_cosmetic_is_kept() -> None:
    frame = synthetic_frame()
    check = check_faces(jpeg(frame), PRODUCT, FakeFaces([BYSTANDER, ON_PRODUCT]), True)
    assert (check.blurred, check.kept, check.touches_product) == (1, 1, False)
    after, before = decode(check.frame_jpeg), decode(jpeg(frame))
    assert roughness(after, ON_PRODUCT) > roughness(before, ON_PRODUCT) * 0.8


def test_a_frame_without_faces_is_left_as_it_is() -> None:
    original = jpeg(synthetic_frame())
    check = check_faces(original, None, FakeFaces([]), keep_product_faces=False)
    assert check.frame_jpeg == original
    assert (check.found, check.blurred) == (0, 0)
    small = MaskCandidate(np.ones((H // 2, W // 2), bool), 0.9)

    class Small(FakeFaces):
        def segment(self, image_jpeg: bytes, prompt: str) -> list[MaskCandidate]:
            return [small]

    resized = check_faces(original, PRODUCT[::2, ::2], Small([]), keep_product_faces=False)
    assert resized.blurred == 1
    with pytest.raises(ValueError, match="could not be read"):
        check_faces(b"not a picture", None, FakeFaces([]), keep_product_faces=False)


def test_without_sam_the_photo_is_the_cut_out_on_the_shop_colour() -> None:
    sprite = np.zeros((100, 60, 4), np.uint8)
    sprite[:, :, 2] = 200
    sprite[:, :, 3] = 255
    ok, png = cv2.imencode(".png", sprite)
    assert ok
    url = plain_photo_data_url(png.tobytes(), "#1c5bd9")
    assert url.startswith("data:image/jpeg;base64,")
    image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")
    assert image.size == (480, 480)
    corner = image.getpixel((5, 5))
    assert isinstance(corner, tuple)
    assert all(abs(a - b) <= 3 for a, b in zip(corner, (214, 225, 247), strict=True))


def test_the_face_finder_is_sam_with_room_for_a_crowd() -> None:
    token = SecretStr("a.b")
    assert build_face_finder(Settings(ai_mode=AIMode.MOCK)) is None
    live = Settings(ai_mode=AIMode.LIVE, sam_url="https://x.modal.run", modal_proxy_token=token)
    finder = build_face_finder(live)
    assert isinstance(finder, Sam3Client)
    assert finder._max_masks == FACE_MASKS


# --- through the cut-out step ---------------------------------------------------------------


@pytest.fixture
def faces(monkeypatch: pytest.MonkeyPatch) -> FakeFaces:
    # One face in the corner, one at the edge of the product (a passer-by behind the shoe).
    finder = FakeFaces([BYSTANDER, box_mask(90, 240, 130, 300)])
    monkeypatch.setattr(cutout_step.FACES, "build", lambda _: finder)
    return finder


def test_key_frames_are_blurred_before_the_game_uses_them(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    stop_after_build: None,
    faces: FakeFaces,
) -> None:
    video_id = upload(client, sample_media["product_video"], whatsapp_number="923001234567")
    run_due("test", max_jobs=10)
    ad = ad_for(session, video_id)
    assert "faces.checked" in trail(session, ad)
    entry = next(e for e in audit.entries_for(session, "ad", ad.id) if e.action == "faces.checked")
    assert entry.data["blurred"] >= 2
    assert "cutout.recut" in trail(session, ad)
    sprites = list(session.scalars(select(Sprite).where(Sprite.ad_id == ad.id)))
    assert {s.face_check for s in sprites} == {FaceState.BLURRED}
    ctx = _context(session, ad)
    photo = game_assets(ctx, latest_brief(ctx)).product_photo
    assert photo is not None
    assert photo.startswith("data:image/jpeg")
    # The stored frame is the blurred one.
    stored = decode(get_storage().get(sprites[0].source_frame_key))
    assert stored.shape[:2] == (H, W)


def test_without_sam_or_when_it_fails_no_frame_is_shown(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    stop_after_build: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_id = upload(client, sample_media["product_video"], whatsapp_number="923001234567")
    run_due("test", max_jobs=10)
    ad = ad_for(session, video_id)
    assert "faces.unchecked" in trail(session, ad)
    sprite = session.scalars(select(Sprite).where(Sprite.ad_id == ad.id)).first()
    assert sprite is not None
    assert sprite.face_check == FaceState.UNCHECKED
    ctx = _context(session, ad)
    brief = latest_brief(ctx)
    plain = plain_photo_data_url(get_storage().get(sprite.sprite_key), brief.palette[0])
    assert game_assets(ctx, brief).product_photo == plain

    monkeypatch.setattr(cutout_step.FACES, "build", lambda _: FakeFaces([], fail=True))
    again = upload(client, sample_media["product_video"], whatsapp_number="923001234567")
    run_due("test", max_jobs=10)
    failed = ad_for(session, again)
    entry = next(
        e for e in audit.entries_for(session, "ad", failed.id) if e.action == "faces.checked"
    )
    assert "could not be checked" in entry.data["message"]
    states = set(session.scalars(select(Sprite.face_check).where(Sprite.ad_id == failed.id)))
    assert states == {FaceState.UNCHECKED}
