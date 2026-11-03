"""SAM 3.1 clients: text-prompted masks (feature 6) and the product followed across a short
clip (feature 7), from our Modal app (workers/modal/sam.py; formats in sam_core.py).

segment: {"image": base64 JPEG, "prompt": "shoe", "threshold": 0.4, "max_masks": 5}
      → {"width": W, "height": H, "masks": [{"score", "box", "mask_png": base64 PNG}]}
track:   {"frames": [base64 JPEG], "prompt": "shoe", "key_index": 3, "box": [x0, y0, x1, y1]}
      → {"width": W, "height": H, "frames": [{"index", "score", "mask_png" or null}]}
Auth: a Modal proxy token, sent as ``Bearer <id>.<secret>``.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import cv2
import httpx
import numpy as np
from numpy.typing import NDArray

from reel2play.analysis import Box
from reel2play.net import (
    ExternalServiceError,
    auth_headers,
    make_client,
    raise_for_status,
    with_retries,
)
from reel2play.settings import AIMode, Settings

SERVICE = "SAM 3.1 on Modal"
Mask = NDArray[np.bool_]


COOLDOWN_S = 600.0
SAM_DOWN: dict[str, float] = {"until": 0.0}


def answered(call: Callable[[], dict[str, object]], attempts: int) -> dict[str, object]:
    """Call SAM 3.1; no answer in time (Modal may be waiting for a free GPU) becomes an
    ``ExternalServiceError``, so callers fall back to code instead of failing the game.
    After no answer, SAM is skipped for ten minutes so later steps and games do not wait."""
    if time.monotonic() < SAM_DOWN["until"]:
        raise ExternalServiceError(SERVICE, "skipped: no answer a moment ago", status=503)
    try:
        return with_retries(call, attempts=attempts, base_delay=2.0)
    except httpx.HTTPError as exc:
        SAM_DOWN["until"] = time.monotonic() + COOLDOWN_S
        raise ExternalServiceError(
            SERVICE, f"no answer ({type(exc).__name__})", status=504
        ) from exc


@dataclass(frozen=True)
class MaskCandidate:
    mask: Mask
    score: float


class Segmenter(Protocol):
    name: str

    def segment(self, image_jpeg: bytes, prompt: str) -> list[MaskCandidate]: ...


def decode_mask(png_b64: str, width: int, height: int) -> Mask:
    raw = np.frombuffer(base64.b64decode(png_b64), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ExternalServiceError(SERVICE, "a mask could not be decoded", status=502)
    if image.shape != (height, width):
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_NEAREST)
    return np.asarray(image > 127)


class Sam3Client:
    name = "sam3.1"

    def __init__(
        self, url: str, token: str, client: httpx.Client | None = None, max_masks: int = 5
    ) -> None:
        self._url = url
        self._token = token
        self._client = client or make_client(httpx.Timeout(75.0, connect=10.0))
        self._max_masks = max_masks

    def segment(self, image_jpeg: bytes, prompt: str) -> list[MaskCandidate]:
        body = {
            "image": base64.b64encode(image_jpeg).decode("ascii"),
            "prompt": prompt,
            "threshold": 0.4,
            "max_masks": self._max_masks,
        }

        def call() -> dict[str, object]:
            response = self._client.post(self._url, json=body, headers=auth_headers(self._token))
            raise_for_status(SERVICE, response)
            data: dict[str, object] = response.json()
            return data

        data = answered(call, attempts=1)
        width, height = int(str(data["width"])), int(str(data["height"]))
        masks = data.get("masks")
        if not isinstance(masks, list):
            raise ExternalServiceError(SERVICE, "response has no masks list", status=502)
        return [
            MaskCandidate(decode_mask(str(m["mask_png"]), width, height), float(m["score"]))
            for m in masks
        ]


class Tracker(Protocol):
    name: str

    def track(
        self, frames_jpeg: list[bytes], prompt: str, key_index: int, box: Box | None
    ) -> list[Mask | None]: ...


class Sam3Tracker:
    """SAM 3.1's video model: one object followed through every frame of the clip."""

    name = "sam3.1-video"

    def __init__(self, url: str, token: str, client: httpx.Client | None = None) -> None:
        self._url = url
        self._token = token
        self._client = client or make_client(httpx.Timeout(180.0, connect=10.0))

    def track(
        self, frames_jpeg: list[bytes], prompt: str, key_index: int, box: Box | None
    ) -> list[Mask | None]:
        body = {
            "frames": [base64.b64encode(f).decode("ascii") for f in frames_jpeg],
            "prompt": prompt,
            "key_index": key_index,
            "box": [box.x0, box.y0, box.x1, box.y1] if box else None,
        }

        def call() -> dict[str, object]:
            response = self._client.post(self._url, json=body, headers=auth_headers(self._token))
            raise_for_status(SERVICE, response)
            data: dict[str, object] = response.json()
            return data

        data = answered(call, attempts=1)
        width, height = int(str(data["width"])), int(str(data["height"]))
        frames = data.get("frames")
        if not isinstance(frames, list) or len(frames) != len(frames_jpeg):
            raise ExternalServiceError(
                SERVICE, "tracking answered for the wrong frames", status=502
            )
        return [
            decode_mask(str(f["mask_png"]), width, height) if f.get("mask_png") else None
            for f in frames
        ]


def build_tracker(settings: Settings) -> Tracker | None:
    """SAM 3.1 tracking when deployed and models are live; None means code follows the product."""
    token = settings.modal_proxy_token.get_secret_value()
    if settings.ai_mode is AIMode.MOCK or not settings.sam_track_endpoint or not token:
        return None
    return Sam3Tracker(settings.sam_track_endpoint, token)


def build_segmenter(settings: Settings) -> Segmenter | None:
    """SAM 3.1 when it is deployed and models are live; None means the fallback cut-out."""
    token = settings.modal_proxy_token.get_secret_value()
    if settings.ai_mode is AIMode.MOCK or not settings.sam_url or not token:
        return None
    return Sam3Client(settings.sam_url, token)


FACE_MASKS = 30  # a crowded frame: every face, not just the clearest five


def build_face_finder(settings: Settings) -> Segmenter | None:
    """Feature 55: SAM 3.1 finding faces; None means faces cannot be checked here."""
    token = settings.modal_proxy_token.get_secret_value()
    if settings.ai_mode is AIMode.MOCK or not settings.sam_url or not token:
        return None
    return Sam3Client(settings.sam_url, token, max_masks=FACE_MASKS)
