"""Gameplay Reel (feature 33), its Meta lead-in cut, and the link-preview image.

The frames come from an exact replay of the tester's winning run (playtest/replay.py). The
Reel opens on the game's title card for a second, plays the run sped up to fit, and holds
the end card with the offer, for 10 to 15 seconds in all at 9:16. It has no sound track:
the shop's own music is never reused, and the shop can add music from Instagram's library.
"""

from __future__ import annotations

import io
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from reel2play.media.video import run_tool
from reel2play.playtest.replay import Frame, Recording
from reel2play.settings import get_settings

INTRO_S = 1.0
END_HOLD_S = 3.0
GAMEPLAY_MAX_S = 10.0
REEL_MIN_S = 10.0
LEAD_IN_S = 5.0
OUTPUT_FPS = 30
WIDTH, HEIGHT = 720, 1280
PREVIEW_SIZE = 600


@dataclass(frozen=True)
class Shot:
    frame: Frame
    seconds: float


def timeline(recording: Recording) -> list[Shot]:
    """Each frame with how long it shows: intro, the run sped up to fit, then the end card."""
    played = [f for f in recording.frames if f.t > 0]
    game_s = played[-1].t if played else 0.0
    speed = max(1.0, game_s / GAMEPLAY_MAX_S)
    shots = [Shot(recording.intro, INTRO_S)]
    previous = 0.0
    for frame in played:
        if frame.t <= previous:
            continue  # the game had ended; the end card is held below
        shots.append(Shot(frame, (frame.t - previous) / speed))
        previous = frame.t
    gameplay_s = game_s / speed
    shots.append(Shot(recording.end, max(END_HOLD_S, REEL_MIN_S - INTRO_S - gameplay_s)))
    return shots


def encode(shots: list[Shot], target: Path) -> None:
    """Write the shots as a silent H.264 MP4 at 720 x 1280."""
    with tempfile.TemporaryDirectory(prefix="r2p-reel-") as tmp:
        folder = Path(tmp)
        lines: list[str] = []
        for index, shot in enumerate(shots):
            path = folder / f"{index:05d}.jpg"
            path.write_bytes(shot.frame.jpeg)
            lines += [f"file '{path.name}'", f"duration {shot.seconds:.4f}"]
        lines.append(f"file '{len(shots) - 1:05d}.jpg'")  # the concat demuxer needs the last again
        (folder / "list.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        scale = f"scale={WIDTH}:{HEIGHT}:flags=lanczos:force_original_aspect_ratio=decrease"
        pad = f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2"
        run_tool(
            [
                get_settings().ffmpeg_bin,
                "-y",
                "-v",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(folder / "list.txt"),
                "-vf",
                f"{scale},{pad},fps={OUTPUT_FPS},format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-movflags",
                "+faststart",
                "-an",
                str(target),
            ]
        )


def cut_lead_in(reel: Path, target: Path) -> None:
    """The Reel's first seconds, for the Meta playable's lead-in video."""
    run_tool(
        [
            get_settings().ffmpeg_bin,
            "-y",
            "-v",
            "error",
            "-i",
            str(reel),
            "-t",
            f"{LEAD_IN_S}",
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
            "-an",
            str(target),
        ]
    )


def preview_image(end_card: bytes) -> bytes:
    """A square JPEG of the end card's middle, for link previews in WhatsApp and Facebook."""
    image = Image.open(io.BytesIO(end_card)).convert("RGB")
    side = min(image.width, image.height)
    top = (image.height - side) // 2
    square = image.crop((0, top, side, top + side)).resize((PREVIEW_SIZE, PREVIEW_SIZE))
    out = io.BytesIO()
    square.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


# --- square and landscape Reels (feature 18) ---------------------------------------------


@dataclass(frozen=True)
class ShapedPage:
    """A square or landscape page: its picture, and where the 9:16 game sits in it."""

    shape: str
    png: bytes
    x: int
    y: int
    width: int
    height: int


def _even(value: float) -> int:
    return max(2, round(value / 2) * 2)


def frame_reel(reel: Path, frame: ShapedPage, target: Path) -> None:
    """The portrait Reel played inside the square or landscape page: the offer panel stays
    beside it the whole time. Silent, like the Reel itself."""
    with tempfile.TemporaryDirectory(prefix="r2p-shape-") as tmp:
        background = Path(tmp) / "page.png"
        background.write_bytes(frame.png)
        with Image.open(background) as page:
            page_w, page_h = _even(page.width), _even(page.height)
        game = f"scale={_even(frame.width)}:{_even(frame.height)}:flags=lanczos"
        run_tool(
            [
                get_settings().ffmpeg_bin,
                "-y",
                "-v",
                "error",
                "-loop",
                "1",
                "-i",
                str(background),
                "-i",
                str(reel),
                "-filter_complex",
                f"[0:v]scale={page_w}:{page_h}[page];[1:v]{game}[game];"
                f"[page][game]overlay={frame.x}:{frame.y}:shortest=1,format=yuv420p",
                "-r",
                str(OUTPUT_FPS),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-an",
                "-movflags",
                "+faststart",
                str(target),
            ]
        )
