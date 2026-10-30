"""Blur for bystanders' faces (feature 55).

SAM 3.1 finds every face in a key frame from the text prompt "face". Code decides which to
blur: every face, except one that is part of the product itself (a cosmetics video showing
the product on a face), judged by how much of the face lies inside the product's own
cut-out mask. Blurred faces are smoothed and coarsened past recognition, and the frame is
saved over the original, so the game, its Reel, the poster and the report never show them.

Without SAM 3.1 the faces cannot be checked, so the game never shows a video frame: the
product cut-out on a plain background of the shop's colour takes its place.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from reel2play.cutout.segmenter import Mask, Segmenter

FACE_PROMPT = "face"
KEEP_OVERLAP = 0.5  # a face at least half inside the product mask is part of the product
JPEG_QUALITY = 92


class FaceState:
    CLEAR = "clear"  # checked, no bystander faces
    BLURRED = "blurred"  # checked, bystander faces blurred
    UNCHECKED = "unchecked"  # could not be checked: the frame is never shown


@dataclass(frozen=True)
class FaceCheck:
    frame_jpeg: bytes
    found: int
    blurred: int
    kept: int
    touches_product: bool


def _decode(jpeg: bytes) -> NDArray[np.uint8]:
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("the key frame could not be read")
    return np.asarray(image, dtype=np.uint8)


def fit(mask: Mask, width: int, height: int) -> Mask:
    """A mask at the frame's size (SAM answers at the size it was sent, but be sure)."""
    resized = cv2.resize(mask.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST)
    return np.asarray(resized > 0)


def blur_region(image: NDArray[np.uint8], region: Mask) -> NDArray[np.uint8]:
    """Smooth and coarsen the region (grown a little past the face's edge) beyond recognition."""
    ys, xs = np.nonzero(region)
    size = max(int(xs.max() - xs.min()), int(ys.max() - ys.min()), 8)
    grow = max(3, size // 6)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow * 2 + 1, grow * 2 + 1))
    grown = cv2.dilate(region.astype(np.uint8), kernel) > 0
    height, width = image.shape[:2]
    cell = max(4, size // 8)
    small = cv2.resize(
        image, (max(1, width // cell), max(1, height // cell)), interpolation=cv2.INTER_AREA
    )
    blocky = cv2.resize(small, (width, height), interpolation=cv2.INTER_NEAREST)
    radius = max(5, (size // 3) | 1)
    smooth = cv2.GaussianBlur(blocky, (radius, radius), 0)
    out = image.copy()
    out[grown] = smooth[grown]
    return out


def check_faces(
    frame_jpeg: bytes,
    product_mask: Mask | None,
    finder: Segmenter,
    keep_product_faces: bool,
) -> FaceCheck:
    """Find the faces in one key frame and blur every one that is not part of the product."""
    image = _decode(frame_jpeg)
    height, width = image.shape[:2]
    product = None
    if product_mask is not None:
        product = product_mask
        if product.shape != (height, width):
            product = fit(product, width, height)
    region = np.zeros((height, width), dtype=bool)
    found = blurred = kept = 0
    touches = False
    for candidate in finder.segment(frame_jpeg, FACE_PROMPT):
        face = candidate.mask
        if face.shape != (height, width):
            face = fit(face, width, height)
        area = int(face.sum())
        if area == 0:
            continue
        found += 1
        inside = int((face & product).sum()) / area if product is not None else 0.0
        if keep_product_faces and inside >= KEEP_OVERLAP:
            kept += 1
            continue
        blurred += 1
        touches = touches or inside > 0
        region |= face
    if not blurred:
        return FaceCheck(frame_jpeg, found, 0, kept, False)
    ok, encoded = cv2.imencode(
        ".jpg", blur_region(image, region), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
    )
    if not ok:  # pragma: no cover - encoding a decoded image does not fail
        raise ValueError("the blurred frame could not be saved")
    return FaceCheck(encoded.tobytes(), found, blurred, kept, touches)
