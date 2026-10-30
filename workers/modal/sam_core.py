"""Request and response handling for the SAM 3.1 endpoints, kept free of torch for testing.

segment (feature 6)
  Request:  {"image": base64 JPEG/PNG, "prompt": "shoe", "threshold": 0.4, "max_masks": 5}
  Response: {"width": W, "height": H, "masks": [{"score", "box": [x0, y0, x1, y1], "mask_png"}]}

track (feature 7)
  Request:  {"frames": [base64 JPEG, ...], "prompt": "shoe", "key_index": 3,
             "box": [x0, y0, x1, y1] as fractions or null}
  Response: {"width": W, "height": H, "frames": [{"index", "score", "mask_png"}]}, one entry per
            frame for the single object that best matches the product on the key frame;
            "mask_png" is null on frames where that object was lost.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from pydantic import BaseModel, Field

MAX_SIDE = 2048


class SegmentRequest(BaseModel):
    image: str = Field(min_length=8, description="Base64 JPEG or PNG")
    prompt: str = Field(min_length=1, max_length=40)
    threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    mask_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    max_masks: int = Field(default=5, ge=1, le=30)


class MaskOut(BaseModel):
    score: float
    box: list[int]
    mask_png: str


class SegmentResponse(BaseModel):
    width: int
    height: int
    masks: list[MaskOut]


def decode_image(data_b64: str) -> Image.Image:
    """The request image as RGB, scaled down so its longest side is at most MAX_SIDE."""
    image: Image.Image = Image.open(io.BytesIO(base64.b64decode(data_b64)))
    image = image.convert("RGB")
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE))
    return image


def encode_mask(mask: NDArray[np.bool_]) -> str:
    buffer = io.BytesIO()
    Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def to_response(
    width: int,
    height: int,
    masks: Sequence[NDArray[np.bool_]],
    boxes: Sequence[Sequence[float]],
    scores: Sequence[float],
    max_masks: int,
) -> SegmentResponse:
    """Best-scoring masks first, at most ``max_masks``, with integer pixel boxes."""
    order = sorted(range(len(scores)), key=lambda i: float(scores[i]), reverse=True)[:max_masks]
    return SegmentResponse(
        width=width,
        height=height,
        masks=[
            MaskOut(
                score=round(float(scores[i]), 4),
                box=[round(float(v)) for v in boxes[i]],
                mask_png=encode_mask(np.asarray(masks[i], dtype=bool)),
            )
            for i in order
        ],
    )


# --- tracking (feature 7) ---------------------------------------------------------------------

MAX_TRACK_FRAMES = 16


class TrackRequest(BaseModel):
    frames: list[str] = Field(min_length=2, max_length=MAX_TRACK_FRAMES)
    prompt: str = Field(min_length=1, max_length=40)
    key_index: int = Field(ge=0)
    box: list[float] | None = Field(default=None, min_length=4, max_length=4)


class TrackedFrame(BaseModel):
    index: int
    score: float | None
    mask_png: str | None


class TrackResponse(BaseModel):
    width: int
    height: int
    frames: list[TrackedFrame]


@dataclass(frozen=True)
class FrameObjects:
    """What the video model found on one frame: object ids with their scores and masks."""

    ids: list[int]
    scores: list[float]
    masks: list[NDArray[np.bool_]]


def overlap(mask: NDArray[np.bool_], box: Sequence[float] | None) -> float:
    """Share of the mask inside the box (fractions of the frame); 1.0 without a box."""
    if box is None or not mask.any():
        return 1.0
    height, width = mask.shape
    x0, y0 = int(box[0] * width), int(box[1] * height)
    x1, y1 = max(x0 + 1, int(box[2] * width)), max(y0 + 1, int(box[3] * height))
    return float(mask[y0:y1, x0:x1].sum()) / float(mask.sum())


def pick_object(
    frames: Mapping[int, FrameObjects], key_index: int, box: Sequence[float] | None
) -> int | None:
    """The object that is the product: best score times agreement with the director's box on
    the key frame (or the first frame it was seen on)."""
    order = [key_index, *sorted(i for i in frames if i != key_index)]
    for index in order:
        found = frames.get(index)
        if found is None or not found.ids:
            continue
        ranked = [
            (score * (0.5 + 0.5 * overlap(mask, box)), object_id)
            for object_id, score, mask in zip(found.ids, found.scores, found.masks, strict=True)
        ]
        return max(ranked)[1]
    return None


def track_response(
    width: int,
    height: int,
    frames: Mapping[int, FrameObjects],
    count: int,
    key_index: int,
    box: Sequence[float] | None,
) -> TrackResponse:
    chosen = pick_object(frames, key_index, box)
    out: list[TrackedFrame] = []
    for index in range(count):
        found = frames.get(index)
        if chosen is None or found is None or chosen not in found.ids:
            out.append(TrackedFrame(index=index, score=None, mask_png=None))
            continue
        at = found.ids.index(chosen)
        out.append(
            TrackedFrame(
                index=index,
                score=round(float(found.scores[at]), 4),
                mask_png=encode_mask(np.asarray(found.masks[at], dtype=bool)),
            )
        )
    return TrackResponse(width=width, height=height, frames=out)
