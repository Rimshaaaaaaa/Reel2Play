from __future__ import annotations

import base64
import io

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from sam_core import (
    MAX_SIDE,
    FrameObjects,
    SegmentRequest,
    TrackRequest,
    decode_image,
    encode_mask,
    overlap,
    pick_object,
    to_response,
    track_response,
)


def _b64_image(size: tuple[int, int], mode: str = "RGBA") -> str:
    buffer = io.BytesIO()
    Image.new(mode, size, (200, 30, 60, 255) if mode == "RGBA" else 128).save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_decode_converts_and_bounds_size() -> None:
    small = decode_image(_b64_image((300, 200)))
    assert small.mode == "RGB"
    assert small.size == (300, 200)
    big = decode_image(_b64_image((4000, 1000), mode="L"))
    assert max(big.size) == MAX_SIDE


def test_mask_round_trip() -> None:
    mask = np.zeros((4, 6), bool)
    mask[1:3, 2:5] = True
    decoded = np.asarray(Image.open(io.BytesIO(base64.b64decode(encode_mask(mask))))) > 127
    assert (decoded == mask).all()


def test_response_sorts_and_limits() -> None:
    masks = [np.ones((2, 2), bool), np.zeros((2, 2), bool), np.eye(2, dtype=bool)]
    response = to_response(
        2, 2, masks, [[0, 0, 1.6, 2], [0, 0, 1, 1], [0.4, 0, 2, 2]], [0.2, 0.9, 0.5], max_masks=2
    )
    assert [m.score for m in response.masks] == [0.9, 0.5]
    assert response.masks[1].box == [0, 0, 2, 2]
    assert response.width == 2


def test_request_validation() -> None:
    assert SegmentRequest(image="x" * 10, prompt="shoe").max_masks == 5
    with pytest.raises(ValidationError):
        SegmentRequest(image="x" * 10, prompt="")
    with pytest.raises(ValidationError):
        SegmentRequest(image="x" * 10, prompt="shoe", threshold=2)


def _square(x0: int, x1: int) -> np.ndarray:
    mask = np.zeros((10, 10), bool)
    mask[2:8, x0:x1] = True
    return mask


def test_tracking_follows_the_product_object() -> None:
    product, other = _square(1, 5), _square(6, 10)
    frames = {
        0: FrameObjects(ids=[7, 9], scores=[0.6, 0.9], masks=[product, other]),
        1: FrameObjects(ids=[9], scores=[0.8], masks=[other]),  # the product is hidden
        2: FrameObjects(ids=[7, 9], scores=[0.7, 0.9], masks=[product, other]),
    }
    box = [0.0, 0.1, 0.5, 0.9]  # the director's box is around the left square
    assert overlap(product, box) == 1.0
    assert overlap(other, box) == 0.0
    assert overlap(product, None) == 1.0
    assert pick_object(frames, 0, box) == 7
    assert pick_object(frames, 0, None) == 9
    response = track_response(10, 10, frames, 4, 0, box)
    assert [f.index for f in response.frames] == [0, 1, 2, 3]
    assert [f.score for f in response.frames] == [0.6, None, 0.7, None]
    assert response.frames[1].mask_png is None
    decoded = Image.open(io.BytesIO(base64.b64decode(response.frames[2].mask_png or "")))
    assert (np.asarray(decoded) > 127).sum() == product.sum()


def test_tracking_with_nothing_found() -> None:
    empty = {0: FrameObjects(ids=[], scores=[], masks=[])}
    assert pick_object(empty, 0, None) is None
    later = {1: FrameObjects(ids=[3], scores=[0.5], masks=[_square(1, 5)])}
    assert pick_object(later, 0, None) == 3
    assert all(f.mask_png is None for f in track_response(10, 10, empty, 2, 0, None).frames)


def test_track_request_limits() -> None:
    frame = _b64_image((8, 8))
    assert TrackRequest(frames=[frame, frame], prompt="cake", key_index=1).box is None
    with pytest.raises(ValidationError):
        TrackRequest(frames=[frame], prompt="cake", key_index=0)
    with pytest.raises(ValidationError):
        TrackRequest(frames=[frame] * 17, prompt="cake", key_index=0)
    with pytest.raises(ValidationError):
        TrackRequest(frames=[frame, frame], prompt="cake", key_index=0, box=[0.1, 0.2])
