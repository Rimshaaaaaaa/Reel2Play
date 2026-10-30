"""Product tracking across frames (feature 7): the clip, the code tracker, SAM 3.1's tracker,
and the moving sprite reaching the game."""

from __future__ import annotations

import base64
import json
import math
import subprocess
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from numpy.typing import NDArray
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.analysis import Box
from reel2play.cutout.cut import cut_product
from reel2play.cutout.segmenter import Mask, Sam3Tracker, build_tracker
from reel2play.cutout.track import (
    CELL,
    TRACK_FRAMES,
    TrackSkippedError,
    as_fractions,
    clip_window,
    decode_mask_png,
    extract_clip,
    track_product,
)
from reel2play.deps import get_storage
from reel2play.jobs.queue import run_due
from reel2play.models import Build, Sprite
from reel2play.net import ExternalServiceError
from reel2play.pipeline import cutout as cutout_step
from reel2play.settings import AIMode, Settings
from tests.helpers import ad_for, trail, upload

ROOT = Path(__file__).resolve().parents[2]
BOX = Box(x0=0.15, y0=0.42, x1=0.85, y1=0.7)


def turning_video(folder: Path, seconds: float = 4.0) -> Path:
    """Synthetic: a blue box with a white band, turning (its width swings) on a grey floor."""
    frames = folder / "frames"
    frames.mkdir()
    for i in range(int(seconds * 15)):
        image = np.full((640, 360, 3), (220, 228, 233), np.uint8)
        image[430:] = (194, 206, 213)
        half = int(25 + 75 * abs(math.cos(i / 15 * 1.6)))
        cv2.rectangle(image, (180 - half, 280), (180 + half, 430), (219, 111, 42), -1)
        cv2.rectangle(image, (180 - half, 320), (180 + half, 345), (255, 255, 255), -1)
        cv2.imwrite(str(frames / f"f{i:03d}.png"), image)
    target = folder / "synthetic-turning.mp4"
    subprocess.run(  # noqa: S603 - fixed arguments
        [  # noqa: S607
            "ffmpeg", "-loglevel", "error", "-y", "-framerate", "15",
            "-i", str(frames / "f%03d.png"), "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "26", "-pix_fmt", "yuv420p", str(target),
        ],
        check=True,
    )  # fmt: skip
    return target


@pytest.fixture(scope="module")
def turning(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return turning_video(tmp_path_factory.mktemp("turning"))


def image_of(data: bytes, flags: int) -> NDArray[np.uint8]:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), flags)
    assert image is not None
    return np.asarray(image, np.uint8)


def clip_of(video: Path, center: float, folder: Path) -> tuple[list[bytes], int, float]:
    start, length = clip_window(center, 4.0)
    clip = extract_clip(video, start, length, folder)
    return clip, min(len(clip) - 1, round((center - start) / length * TRACK_FRAMES)), length


def key_mask(clip: list[bytes], key: int) -> Mask:
    return decode_mask_png(cut_product(clip[key], "box", BOX, None).mask_png)


def blue_masks(clip: list[bytes]) -> list[Mask]:
    """What a perfect tracker would find: the blue and white box on every frame."""
    out = []
    for frame in clip:
        image = image_of(frame, cv2.IMREAD_COLOR)
        out.append(
            np.asarray((image[:, :, 0] > 150) & (image[:, :, 2] < 150) | (image.min(axis=2) > 245))
        )
    return out


class FakeTracker:
    name = "sam3.1-video"

    def __init__(self, masks: list[Mask | None]) -> None:
        self.masks = masks
        self.calls: list[tuple[int, Box | None]] = []

    def track(
        self, frames_jpeg: list[bytes], prompt: str, key_index: int, box: Box | None
    ) -> list[Mask | None]:
        self.calls.append((key_index, box))
        return self.masks


# --- the clip and the code tracker -------------------------------------------------------------


def test_clip_window_stays_inside_the_video() -> None:
    assert clip_window(2.0, 6.0) == (1.4, 1.2)
    assert clip_window(0.1, 6.0) == (0.0, 1.2)
    assert clip_window(5.9, 6.0) == pytest.approx((4.8, 1.2))
    assert clip_window(0.3, 0.8) == (0.0, 0.8)


def test_a_turning_product_becomes_a_moving_sprite(turning: Path, tmp_path: Path) -> None:
    clip, key, length = clip_of(turning, 2.0, tmp_path)
    assert len(clip) == TRACK_FRAMES
    track = track_product(clip, key, key_mask(clip, key), "box", None, length)
    assert (track.method, track.quality) == ("match", "lower")
    assert track.frames >= 5
    assert track.fps == pytest.approx(TRACK_FRAMES / length, rel=0.01)
    strip = image_of(track.strip_png, cv2.IMREAD_UNCHANGED)
    assert strip.shape == (CELL, CELL * track.frames, 4)
    widths = [int((strip[:, i * CELL : (i + 1) * CELL, 3] > 127).any(axis=0).sum())
              for i in range(track.frames)]  # fmt: skip
    assert max(widths) - min(widths) > 15  # the box really turns between frames
    assert strip[0, 0, 3] == 0  # corners are see-through


def test_a_product_that_only_sits_there_stays_still(tmp_path: Path) -> None:
    clip, key, length = clip_of(ROOT / "samples/synthetic-sneaker.mp4", 2.0, tmp_path)
    mask = decode_mask_png(cut_product(clip[key], "shoe", BOX, None).mask_png)
    with pytest.raises(TrackSkippedError, match="does not turn or change"):
        track_product(clip, key, mask, "shoe", None, length)


def test_too_short_or_lost_products_are_not_animated(turning: Path, tmp_path: Path) -> None:
    clip, key, length = clip_of(turning, 2.0, tmp_path)
    mask = key_mask(clip, key)
    with pytest.raises(TrackSkippedError, match="too short"):
        track_product(clip[:4], 2, mask, "box", None, length)
    lost: list[Mask | None] = [None] * len(clip)
    lost[key] = blue_masks(clip)[key]
    with pytest.raises(TrackSkippedError, match="only 1 of 8 frames"):
        track_product(clip, key, mask, "box", FakeTracker(lost), length)
    with pytest.raises(TrackSkippedError, match="not found on the key frame"):
        track_product(clip, key, mask, "box", FakeTracker([None] * len(clip)), length)
    with pytest.raises(TrackSkippedError, match="could not be read"):
        decode_mask_png(b"not a png")


def test_sam_tracking_is_good_quality(turning: Path, tmp_path: Path) -> None:
    clip, key, length = clip_of(turning, 2.0, tmp_path)
    masks: list[Mask | None] = list(blue_masks(clip))
    masks[0] = None  # lost on one frame: dropped, the rest still animate
    tracker = FakeTracker(masks)
    small_mask = cv2.resize(key_mask(clip, key).astype(np.uint8), (180, 320)) > 0
    track = track_product(clip, key, small_mask, "box", tracker, length)
    assert (track.method, track.quality, track.frames) == ("sam3.1-video", "good", 7)
    called_key, box = tracker.calls[0]
    assert called_key == key
    assert box is not None
    assert 0.1 < box.x0 < box.x1 < 0.9


def test_as_fractions_stays_in_the_frame() -> None:
    box = as_fractions((-5, 10, 400, 20), 360, 640)
    assert (box.x0, box.x1) == (0.0, 1.0)


# --- SAM 3.1's tracking endpoint -----------------------------------------------------------------


def test_sam_tracker_round_trip() -> None:
    mask = np.zeros((32, 18), np.uint8)
    mask[10:20, 4:14] = 255
    ok, png = cv2.imencode(".png", mask)
    assert ok
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer id.secret"
        frames = [
            {"index": 0, "score": 0.9, "mask_png": base64.b64encode(png.tobytes()).decode()},
            {"index": 1, "score": None, "mask_png": None},
        ]
        return httpx.Response(200, json={"width": 36, "height": 64, "frames": frames})

    tracker = Sam3Tracker(
        "https://ws--reel2play-sam-sam-track.modal.run",
        "id.secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    found = tracker.track([b"a", b"b"], "cake", 0, BOX)
    assert seen[0]["box"] == [0.15, 0.42, 0.85, 0.7]
    assert seen[0]["key_index"] == 0
    assert found[1] is None
    assert found[0] is not None
    assert found[0].shape == (64, 36)
    with pytest.raises(ExternalServiceError, match="wrong frames"):
        tracker.track([b"a"], "cake", 0, None)


def test_the_tracker_is_built_only_when_sam_is_deployed() -> None:
    token = SecretStr("a.b")
    assert build_tracker(Settings(ai_mode=AIMode.MOCK)) is None
    assert build_tracker(Settings(ai_mode=AIMode.LIVE, modal_proxy_token=token)) is None
    derived = Settings(
        ai_mode=AIMode.LIVE,
        sam_url="https://ws--reel2play-sam-sam-segment.modal.run",
        modal_proxy_token=token,
    )
    assert derived.sam_track_endpoint == "https://ws--reel2play-sam-sam-track.modal.run"
    assert isinstance(build_tracker(derived), Sam3Tracker)
    own = Settings(sam_url="https://other.example/segment", sam_track_url="https://t.example")
    assert own.sam_track_endpoint == "https://t.example"
    assert Settings(sam_url="https://other.example/segment").sam_track_endpoint == ""


# --- through the pipeline ------------------------------------------------------------------------


def test_the_moving_sprite_reaches_the_game(
    client: TestClient, session: Session, turning: Path, stop_after_build: None
) -> None:
    video_id = upload(client, turning, whatsapp_number="923001234567")
    run_due("test")
    ad = ad_for(session, video_id)
    assert "track.done" in trail(session, ad)
    sprite = session.scalars(select(Sprite).where(Sprite.ad_id == ad.id)).one()
    assert sprite.track_frames >= 5
    assert sprite.track_method == "match"
    assert sprite.track_key is not None
    assert get_storage().get(sprite.track_key).startswith(b"\x89PNG")
    done = next(e for e in audit.entries_for(session, "ad", ad.id) if e.action == "track.done")
    assert "with code (lower quality), so it moves in the game" in done.data["message"]

    build = session.scalars(select(Build).where(Build.ad_id == ad.id)).one()
    html = get_storage().get(build.html_key).decode()
    if build.template == "puzzle":  # the photo puzzle has no use for the moving sprite
        assert '"productFrames":null' in html
    else:
        assert '"productFrames":{"strip":"data:image/webp;base64,' in html
        assert f'"frames":{sprite.track_frames},' in html


def test_still_products_and_sam_failures_are_explained(
    client: TestClient,
    session: Session,
    turning: Path,
    stop_after_build: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sneaker = upload(client, ROOT / "samples/synthetic-sneaker.mp4", shop_url="https://s.pk")
    run_due("test")
    still = ad_for(session, sneaker)
    skipped = [e for e in audit.entries_for(session, "ad", still.id) if e.action == "track.skipped"]
    assert skipped[0].data["message"] == (
        "The sprite stays still: the product does not turn or change in the video."
    )

    class BrokenTracker(FakeTracker):
        def track(self, *args: object, **kwargs: object) -> list[Mask | None]:
            raise ExternalServiceError("SAM 3.1 on Modal", "HTTP 503", status=503)

    monkeypatch.setattr(cutout_step.TRACKER, "build", lambda _: BrokenTracker([]))
    turned = upload(client, turning, shop_url="https://s.pk")
    run_due("test")
    sprite = session.scalars(select(Sprite).where(Sprite.ad_id == ad_for(session, turned).id)).one()
    assert sprite.track_method == "match"  # SAM failed, code followed the product instead


def test_photos_and_unreadable_clips_have_no_animation(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    stop_after_build: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    photos = upload(client, sample_media["photo_jpg"], shop_url="https://s.pk")
    run_due("test")
    actions = trail(session, ad_for(session, photos))
    assert "track.done" not in actions
    assert "track.skipped" not in actions

    def broken_clip(*_: object) -> list[bytes]:
        raise subprocess.CalledProcessError(1, "ffmpeg")

    monkeypatch.setattr(cutout_step, "extract_clip", broken_clip)
    video = upload(client, sample_media["product_video"], shop_url="https://s.pk")
    run_due("test")
    ad = ad_for(session, video)
    skipped = [e for e in audit.entries_for(session, "ad", ad.id) if e.action == "track.skipped"]
    assert skipped[0].data["reason"] == "the clip could not be read"
