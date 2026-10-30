"""ffmpeg and ffprobe wrappers. Every call has a timeout and a clear error."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from reel2play.settings import get_settings

DEFAULT_TIMEOUT_S = 180


class MediaToolError(RuntimeError):
    pass


def run_tool(
    args: list[str],
    timeout_s: int = DEFAULT_TIMEOUT_S,
    capture: Literal["stdout", "stderr"] = "stdout",
) -> str:
    """Run an ffmpeg-family tool and return the chosen output stream."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed binaries, no shell
            args, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaToolError(f"{Path(args[0]).name} timed out after {timeout_s}s") from exc
    except FileNotFoundError as exc:
        raise MediaToolError(f"{args[0]} is not installed") from exc
    if result.returncode != 0:
        tail = result.stderr.strip().splitlines()[-3:]
        raise MediaToolError(f"{Path(args[0]).name} failed: {' | '.join(tail)}")
    return result.stdout if capture == "stdout" else result.stderr


@dataclass(frozen=True)
class ProbeResult:
    duration_s: float
    width: int
    height: int
    has_audio: bool
    has_video: bool


def probe(path: Path) -> ProbeResult:
    out = run_tool(
        [
            get_settings().ffprobe_bin,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout_s=30,
    )
    data = json.loads(out)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    duration = float(data.get("format", {}).get("duration") or 0.0)
    return ProbeResult(
        duration_s=round(duration, 2),
        width=int(video.get("width", 0)) if video else 0,
        height=int(video.get("height", 0)) if video else 0,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        has_video=video is not None,
    )


def strip_audio(source: Path, target: Path) -> None:
    """Keep the video stream only; the original sound never travels further.

    Copies the stream when the container allows it, otherwise re-encodes to H.264.
    """
    ffmpeg = get_settings().ffmpeg_bin
    base = [ffmpeg, "-y", "-v", "error", "-i", str(source), "-map", "0:v:0", "-an"]
    try:
        run_tool([*base, "-c:v", "copy", "-movflags", "+faststart", str(target)])
    except MediaToolError:
        run_tool(
            [
                *base,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(target),
            ]
        )


def extract_audio(source: Path, target: Path, *, max_seconds: float | None = None) -> None:
    """Mono 16 kHz MP3 of the spoken track, read by the director only (never reused)."""
    limit = ["-t", f"{max_seconds:g}"] if max_seconds else []
    run_tool(
        [
            get_settings().ffmpeg_bin,
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            *limit,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "48k",
            str(target),
        ]
    )
