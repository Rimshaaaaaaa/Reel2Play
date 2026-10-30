"""Key-frame candidates (feature 5): scene changes plus even samples, scored for sharpness.

Code proposes the candidates and their sharpness; the director picks the best product shots.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from reel2play.media.video import run_tool
from reel2play.settings import get_settings

SCENE_THRESHOLD = 0.3
MAX_CANDIDATES = 6
MIN_GAP_S = 0.6
FRAME_MAX_SIDE = 960
_PTS = re.compile(r"pts_time:([0-9.]+)")


@dataclass(frozen=True)
class Candidate:
    index: int
    time_s: float
    path: Path
    sharpness: float


def scene_changes(video: Path, threshold: float = SCENE_THRESHOLD) -> list[float]:
    """Times (seconds) where ffmpeg's scene score jumps above ``threshold``."""
    stderr = run_tool(
        [
            get_settings().ffmpeg_bin,
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-vf",
            f"select='gt(scene,{threshold})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture="stderr",
    )
    return [round(float(t), 2) for t in _PTS.findall(stderr)]


def candidate_times(
    duration_s: float, scenes: list[float], limit: int = MAX_CANDIDATES
) -> list[float]:
    """Scene changes first, then even samples, at least MIN_GAP_S apart, in time order."""
    if duration_s <= 0:
        return [0.0]
    margin = min(0.3, duration_s / 10)
    even = [margin + (duration_s - 2 * margin) * (i + 0.5) / limit for i in range(limit)]
    chosen: list[float] = []
    for t in [*(s + 0.15 for s in scenes), *even]:
        t = round(min(max(t, 0.0), max(0.0, duration_s - 0.05)), 2)
        if all(abs(t - c) >= MIN_GAP_S for c in chosen):
            chosen.append(t)
        if len(chosen) == limit:
            break
    return sorted(chosen) or [0.0]


def extract_frame(video: Path, time_s: float, target: Path) -> None:
    side = FRAME_MAX_SIDE
    scale = f"scale='if(gt(iw,ih),min({side},iw),-2)':'if(gt(iw,ih),-2,min({side},ih))'"
    run_tool(
        [
            get_settings().ffmpeg_bin,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{time_s:.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            scale,
            "-q:v",
            "3",
            str(target),
        ]
    )


def sharpness(path: Path) -> float:
    """Variance of the Laplacian: higher means a crisper, more detailed frame."""
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return 0.0
    return round(float(cv2.Laplacian(image, cv2.CV_64F).var()), 2)


def video_candidates(video: Path, duration_s: float, workdir: Path) -> list[Candidate]:
    times = candidate_times(duration_s, scene_changes(video))
    candidates: list[Candidate] = []
    for index, time_s in enumerate(times):
        path = workdir / f"candidate-{index}.jpg"
        extract_frame(video, time_s, path)
        candidates.append(Candidate(index, time_s, path, sharpness(path)))
    return candidates


def photo_candidates(photos: list[Path], workdir: Path) -> list[Candidate]:
    """Each photo becomes a candidate, re-encoded as a bounded JPEG."""
    candidates: list[Candidate] = []
    for index, photo in enumerate(photos[:MAX_CANDIDATES]):
        image = cv2.imread(str(photo), cv2.IMREAD_COLOR)
        if image is None:
            continue
        height, width = image.shape[:2]
        factor = min(1.0, FRAME_MAX_SIDE / max(height, width))
        if factor < 1.0:
            image = cv2.resize(image, (int(width * factor), int(height * factor)))
        path = workdir / f"candidate-{index}.jpg"
        cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        candidates.append(Candidate(index, 0.0, path, sharpness(path)))
    return candidates


def dominant_colors(path: Path, count: int = 4) -> list[str]:
    """The ``count`` most common colours of an image, as hex, most common first."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return []
    small = cv2.resize(image, (64, 64), interpolation=cv2.INTER_NEAREST)
    pixels = small.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    start = np.zeros((pixels.shape[0], 1), np.int32)
    _, labels, centers = cv2.kmeans(pixels, count, start, criteria, 3, cv2.KMEANS_PP_CENTERS)
    order = np.argsort(-np.bincount(labels.flatten().astype(np.int64), minlength=count))
    return [
        "#{:02x}{:02x}{:02x}".format(*(int(c) for c in centers[i][::-1]))  # BGR to RGB
        for i in order
    ]
