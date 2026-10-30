"""Product tracking across frames (feature 7): a short animated sprite from the video itself.

Around the best key frame, a clip of about a second is cut into a few frames and the product
is followed through them: by SAM 3.1's video model when it is deployed, otherwise by code
(template matching from frame to frame, then GrabCut in each box seeded with the key frame's
colours, marked lower quality).
Frames where the product was lost or changed size too much are dropped. Each kept frame is
centred in a square cell at one shared scale, so the product turns, opens or pours in place
instead of sliding about. If the product does not change shape or look across the clip (a
still shot, or the camera only drifting), an animation would add nothing, and the sprite
stays still.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from reel2play.analysis import Box
from reel2play.cutout.cut import FEATHER_PX, Image, clean_mask, decode_image
from reel2play.cutout.segmenter import Mask, Tracker
from reel2play.media.frames import FRAME_MAX_SIDE
from reel2play.settings import get_settings

TRACK_FRAMES = 8
WINDOW_S = 1.2
CELL = 160
FILL = 0.92
MIN_FRAMES = 5
AREA_RANGE = (0.3, 3.0)  # a box seen edge-on and face-on can differ this much
MATCH_MIN = 0.45
# Mean change of the product's pixels (0 to 1) below which it counts as not moving.
STILL = 0.035

Cell = NDArray[np.uint8]
Rect = tuple[int, int, int, int]  # x, y, width, height in pixels


class TrackSkippedError(RuntimeError):
    """No animation for this product; the message says why in plain words."""


@dataclass(frozen=True)
class Track:
    strip_png: bytes
    frames: int
    fps: float
    method: str  # sam3.1-video | match
    quality: str  # good | lower


def clip_window(center_s: float, duration_s: float) -> tuple[float, float]:
    """About WINDOW_S seconds around the key frame, kept inside the video."""
    length = min(WINDOW_S, duration_s)
    start = min(max(0.0, center_s - length / 2), max(0.0, duration_s - length))
    return start, length


def extract_clip(video: Path, start_s: float, length_s: float, workdir: Path) -> list[bytes]:
    """TRACK_FRAMES evenly spaced JPEG frames, scaled like the key frames."""
    side = FRAME_MAX_SIDE
    scale = f"scale='if(gt(iw,ih),min({side},iw),-2)':'if(gt(iw,ih),-2,min({side},ih))'"
    rate = TRACK_FRAMES / length_s
    pattern = workdir / "track-%02d.jpg"
    subprocess.run(  # noqa: S603 - fixed arguments, our own paths
        [
            get_settings().ffmpeg_bin,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{start_s:.3f}",
            "-t",
            f"{length_s:.3f}",
            "-i",
            str(video),
            "-vf",
            f"fps={rate:.4f},{scale}",
            "-frames:v",
            str(TRACK_FRAMES),
            "-q:v",
            "3",
            str(pattern),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return [path.read_bytes() for path in sorted(workdir.glob("track-*.jpg"))]


def _resized(image: Image, width: int, height: int) -> Image:
    return np.asarray(cv2.resize(image, (width, height)), dtype=np.uint8)


def decode_mask_png(data: bytes) -> Mask:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise TrackSkippedError("the key frame's cut-out could not be read")
    return np.asarray(image > 127)


def mask_box(mask: Mask) -> Rect:
    """(x, y, w, h) of the mask's pixels."""
    ys, xs = np.nonzero(mask)
    x0, y0 = int(xs.min()), int(ys.min())
    return x0, y0, int(xs.max()) - x0 + 1, int(ys.max()) - y0 + 1


def as_fractions(rect: Rect, width: int, height: int) -> Box:
    """A pixel rectangle as the fractions the director and SAM use."""
    x, y, w, h = rect
    return Box(
        x0=max(0.0, x / width),
        y0=max(0.0, y / height),
        x1=min(1.0, (x + w) / width),
        y1=min(1.0, (y + h) / height),
    )


def follow(images: list[Image], key_index: int, start: Rect) -> list[Rect | None]:
    """The product's box in every frame, found by matching it frame to frame from the key."""
    boxes: list[Rect | None] = [None] * len(images)
    boxes[key_index] = start
    for direction in (1, -1):
        current = start
        index = key_index + direction
        while 0 <= index < len(images):
            found = _match(images[index - direction], images[index], current)
            if found is None:
                break
            boxes[index] = current = found
            index += direction
    return boxes


def _match(previous: Image, image: Image, box: Rect) -> Rect | None:
    x, y, w, h = box
    template = previous[y : y + h, x : x + w]
    height, width = image.shape[:2]
    margin_x, margin_y = max(8, int(w * 0.4)), max(8, int(h * 0.4))
    sx0, sy0 = max(0, x - margin_x), max(0, y - margin_y)
    sx1, sy1 = min(width, x + w + margin_x), min(height, y + h + margin_y)
    area = image[sy0:sy1, sx0:sx1]
    if area.shape[0] < h or area.shape[1] < w:
        return None
    scores = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
    _, best, _, (bx, by) = cv2.minMaxLoc(scores)
    if best < MATCH_MIN:
        return None
    return sx0 + bx, sy0 + by, w, h


def colour_model(image: Image, mask: Mask) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Hue and saturation histograms of the product and of what surrounds it."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    ring = cv2.dilate(mask.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
    hists = []
    for region in (mask, ring & ~mask):
        hist = cv2.calcHist([hsv], [0, 1], region.astype(np.uint8), [30, 32], [0, 180, 0, 256])
        peak = float(hist.max())
        hists.append(np.asarray(hist * (255.0 / peak) if peak else hist, np.float32))
    return hists[0], hists[1]


def colour_cut(image: Image, rect: Rect, model: tuple[NDArray[np.float32], ...]) -> Mask:
    """GrabCut seeded by the key frame's colours: product-coloured pixels in the box start as
    probable product, the rest of the box as probable background."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    product, around = (
        cv2.calcBackProject([hsv], [0, 1], hist, [0, 180, 0, 256], 1).astype(np.float32)
        for hist in model
    )
    likely = product > around
    height, width = image.shape[:2]
    x, y, w, h = rect
    pad_x, pad_y = w // 8, h // 8
    x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
    x1, y1 = min(width, x + w + pad_x), min(height, y + h + pad_y)
    seed = np.full((height, width), cv2.GC_BGD, np.uint8)
    seed[y0:y1, x0:x1] = cv2.GC_PR_BGD
    inside = np.zeros((height, width), bool)
    inside[y0:y1, x0:x1] = True
    seed[inside & likely] = cv2.GC_PR_FGD
    if not (seed == cv2.GC_PR_FGD).any():
        return np.zeros((height, width), bool)
    background = np.zeros((1, 65), np.float64)
    foreground = np.zeros((1, 65), np.float64)
    cv2.grabCut(image, seed, (0, 0, 1, 1), background, foreground, 3, cv2.GC_INIT_WITH_MASK)
    return np.asarray((seed == cv2.GC_FGD) | (seed == cv2.GC_PR_FGD))


def code_masks(
    images: list[Image], key_index: int, key_mask: Mask
) -> tuple[list[Mask | None], list[Rect | None]]:
    """The fallback: follow the key mask's box frame to frame, then cut the product out of
    each box using the key frame's colours."""
    boxes = follow(images, key_index, mask_box(key_mask))
    model = colour_model(images[key_index], key_mask)
    masks: list[Mask | None] = []
    for image, rect in zip(images, boxes, strict=True):
        # The key frame is cut the same way too, so every frame's edges match.
        masks.append(None if rect is None else clean_mask(colour_cut(image, rect, model)))
    return masks, boxes


def kept_frames(masks: list[Mask | None], key_mask: Mask) -> list[int]:
    """Frames whose product is about the key frame's size; the rest were lost or confused."""
    key_area = float(np.count_nonzero(key_mask))
    low, high = AREA_RANGE
    return [
        index
        for index, mask in enumerate(masks)
        if mask is not None and mask.any() and low <= np.count_nonzero(mask) / key_area <= high
    ]


def cells(images: list[Image], masks: list[Mask]) -> list[Cell]:
    """Each frame's product centred in a CELL square, all at one scale (RGBA)."""
    rects = [mask_box(m) for m in masks]
    scale = CELL * FILL / max(max(w, h) for _, _, w, h in rects)
    out: list[Cell] = []
    for image, mask, (x, y, w, h) in zip(images, masks, rects, strict=True):
        hard = mask[y : y + h, x : x + w].astype(np.uint8) * 255
        alpha = cv2.GaussianBlur(hard, (2 * FEATHER_PX + 1, 2 * FEATHER_PX + 1), 0)
        crop = cv2.cvtColor(image[y : y + h, x : x + w], cv2.COLOR_BGR2BGRA)
        crop[:, :, 3] = alpha
        size = (max(1, round(w * scale)), max(1, round(h * scale)))
        crop = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
        cell = np.zeros((CELL, CELL, 4), np.uint8)
        left, top = (CELL - size[0]) // 2, (CELL - size[1]) // 2
        cell[top : top + size[1], left : left + size[0]] = crop
        out.append(cell)
    return out


def change(images: list[Image], rects: list[Rect | None], keep: list[int], key: int) -> float:
    """How much the product itself changes: each kept frame's product area, taken at the key
    frame's size around where the product is, against the key frame's (0 to 1). Comparing
    pixels, not cut-outs, keeps a still product still even when its cut-outs differ a little."""
    key_rect = rects[key]
    if key_rect is None:  # pragma: no cover - the key frame is always followed
        return 0.0
    _, _, w, h = key_rect
    height, width = images[0].shape[:2]

    def patch(index: int) -> NDArray[np.float32]:
        rect = rects[index]
        assert rect is not None
        cx, cy = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
        x = int(min(max(cx - w / 2, 0), width - w))
        y = int(min(max(cy - h / 2, 0), height - h))
        gray = cv2.cvtColor(images[index][y : y + h, x : x + w], cv2.COLOR_BGR2GRAY)
        return np.asarray(gray, np.float32) / np.float32(255)

    base = patch(key)
    return max(float(np.abs(patch(i) - base).mean()) for i in keep if i != key)


def strip(cells_: list[Cell]) -> bytes:
    ok, png = cv2.imencode(".png", np.hstack(cells_))
    if not ok:  # pragma: no cover - encoding a valid array cannot fail
        raise TrackSkippedError("the animation could not be saved")
    return png.tobytes()


def track_product(
    clip: list[bytes],
    key_index: int,
    key_mask: Mask,
    prompt: str,
    tracker: Tracker | None,
    seconds: float,
) -> Track:
    """Follow the product through ``clip`` and make its animation strip, or say why not."""
    if len(clip) < MIN_FRAMES:
        raise TrackSkippedError("the video is too short to animate the product")
    images = [decode_image(frame) for frame in clip]
    height, width = images[0].shape[:2]
    images = [i if i.shape[:2] == (height, width) else _resized(i, width, height) for i in images]
    if key_mask.shape != (height, width):
        key_mask = np.asarray(_resized(key_mask.astype(np.uint8), width, height) > 0)
    method, quality = "match", "lower"
    masks: list[Mask | None]
    rects: list[Rect | None]
    if tracker is not None:
        box = as_fractions(mask_box(key_mask), width, height)
        masks = [
            m if m is None else clean_mask(m) for m in tracker.track(clip, prompt, key_index, box)
        ]
        rects = [mask_box(m) if m is not None and m.any() else None for m in masks]
        method, quality = tracker.name, "good"
    else:
        masks, rects = code_masks(images, key_index, key_mask)
    found_on_key = masks[key_index]
    if found_on_key is None or not found_on_key.any():
        raise TrackSkippedError("the product was not found on the key frame")
    keep = kept_frames(masks, found_on_key)
    if len(keep) < MIN_FRAMES:
        raise TrackSkippedError(
            f"the product could be followed in only {len(keep)} of {len(clip)} frames"
        )
    if change(images, rects, keep, key_index) < STILL:
        raise TrackSkippedError("the product does not turn or change in the video")
    made = cells([images[i] for i in keep], [m for i in keep if (m := masks[i]) is not None])
    return Track(strip(made), len(made), round(len(clip) / seconds, 2), method, quality)
