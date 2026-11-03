"""Product cut-out (feature 6): pick the best mask, clean its edges, and render a sprite.

SAM 3.1 gives masks from a text prompt. Without it (no Modal credits, or the mock model),
the fallback cuts the product out of the director's box with GrabCut and marks the sprite
as lower quality, as the spec allows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from reel2play.analysis import Box
from reel2play.cutout.segmenter import Mask, MaskCandidate, Segmenter
from reel2play.net import ExternalServiceError

log = logging.getLogger(__name__)

SPRITE_MAX_SIDE = 512
MIN_AREA = 0.01
MAX_AREA = 0.92
FEATHER_PX = 2
DEFAULT_BOX = Box(x0=0.15, y0=0.15, x1=0.85, y1=0.85)

Image = NDArray[np.uint8]


class CutoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class CutResult:
    sprite_png: bytes
    mask_png: bytes
    method: str  # sam3.1 | grabcut
    quality: str  # good | lower
    score: float
    width: int
    height: int
    area_fraction: float


def decode_image(data: bytes) -> Image:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise CutoutError("the key frame could not be read")
    return np.asarray(image, dtype=np.uint8)


def box_overlap(mask: Mask, box: Box | None) -> float:
    """Share of the mask that lies inside the director's box (1.0 when there is no box)."""
    if box is None or not mask.any():
        return 1.0
    height, width = mask.shape
    x, y, w, h = box.to_pixels(width, height)
    inside = int(mask[y : y + h, x : x + w].sum())
    return inside / int(mask.sum())


def choose_mask(candidates: list[MaskCandidate], box: Box | None) -> MaskCandidate | None:
    """Highest score, weighted by agreement with the box, among plausibly sized masks."""
    usable = [c for c in candidates if MIN_AREA <= float(c.mask.mean()) <= MAX_AREA]
    if not usable:
        return None
    return max(usable, key=lambda c: c.score * (0.5 + 0.5 * box_overlap(c.mask, box)))


def clean_mask(mask: Mask) -> Mask:
    """Keep the largest region, fill small holes and smooth the edge."""
    binary = mask.astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if count <= 1:
        return np.zeros_like(mask, dtype=bool)
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    region = (labels == largest).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    closed = cv2.morphologyEx(region, cv2.MORPH_CLOSE, kernel, iterations=2)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel, iterations=1)
    return np.asarray(opened > 0)


def grabcut_mask(image: Image, box: Box | None) -> Mask:
    height, width = image.shape[:2]
    rect = (box or DEFAULT_BOX).to_pixels(width, height)
    mask = np.zeros((height, width), np.uint8)
    background = np.zeros((1, 65), np.float64)
    foreground = np.zeros((1, 65), np.float64)
    cv2.grabCut(image, mask, rect, background, foreground, 4, cv2.GC_INIT_WITH_RECT)
    return np.asarray((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD))


def render_sprite(image: Image, mask: Mask) -> tuple[bytes, bytes, int, int]:
    """RGBA PNG cropped to the mask with a feathered edge, at most SPRITE_MAX_SIDE pixels."""
    ys, xs = np.nonzero(mask)
    pad = 4
    y0, y1 = max(0, int(ys.min()) - pad), min(mask.shape[0], int(ys.max()) + pad + 1)
    x0, x1 = max(0, int(xs.min()) - pad), min(mask.shape[1], int(xs.max()) + pad + 1)
    hard = mask[y0:y1, x0:x1].astype(np.uint8) * 255
    alpha = cv2.GaussianBlur(hard, (2 * FEATHER_PX + 1, 2 * FEATHER_PX + 1), 0)
    sprite = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_BGR2BGRA)
    sprite[:, :, 3] = alpha
    scale = min(1.0, SPRITE_MAX_SIDE / max(sprite.shape[:2]))
    if scale < 1.0:
        size = (max(1, int(sprite.shape[1] * scale)), max(1, int(sprite.shape[0] * scale)))
        sprite = cv2.resize(sprite, size, interpolation=cv2.INTER_AREA)
    ok_sprite, sprite_png = cv2.imencode(".png", sprite)
    ok_mask, mask_png = cv2.imencode(".png", mask.astype(np.uint8) * 255)
    if not (ok_sprite and ok_mask):  # pragma: no cover - encoding a valid array cannot fail
        raise CutoutError("the sprite could not be encoded")
    return sprite_png.tobytes(), mask_png.tobytes(), sprite.shape[1], sprite.shape[0]


def cut_product(
    frame_jpeg: bytes, prompt: str, box: Box | None, segmenter: Segmenter | None
) -> CutResult:
    image = decode_image(frame_jpeg)
    method, quality, score = "grabcut", "lower", 0.0
    chosen: Mask | None = None
    if segmenter is not None:
        try:
            found = segmenter.segment(frame_jpeg, prompt)
        except ExternalServiceError as exc:
            log.warning("SAM 3.1 did not answer, cutting out in code: %s", exc)
            found = []
        candidate = choose_mask(found, box)
        if candidate is not None:
            chosen, method, quality, score = candidate.mask, segmenter.name, "good", candidate.score
    if chosen is None:
        chosen = grabcut_mask(image, box)
    mask = clean_mask(chosen)
    area = float(mask.mean())
    if area < MIN_AREA:
        raise CutoutError("the product could not be separated from the background")
    if area > MAX_AREA:
        quality = "lower"
    sprite_png, mask_png, width, height = render_sprite(image, mask)
    return CutResult(sprite_png, mask_png, method, quality, round(score, 3), width, height, area)
