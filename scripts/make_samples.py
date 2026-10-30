"""Make the synthetic try-it samples in samples/ with ffmpeg (run once; the files are kept).

They are simple drawn shapes, labelled synthetic everywhere they appear. Real sample videos
from shops that agreed go in the same folder with ``"synthetic": false`` in the manifest.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p"]

# A sneaker (red upper, white sole, laces) drifting slowly across a warm grey studio.
SNEAKER = (
    "color=c=0xe9e4dc:size=360x640:rate=15:duration=6,"
    "drawbox=x=0:y=430:w=iw:h=210:color=0xd5cec2:t=fill,"
    "drawbox=x='80+8*sin(t)':y=300:w=200:h=95:color=0xc8243a:t=fill,"
    "drawbox=x='70+8*sin(t)':y=390:w=225:h=30:color=0xfafafa:t=fill,"
    "drawbox=x='120+8*sin(t)':y=315:w=70:h=8:color=0xffffff:t=fill,"
    "drawbox=x='120+8*sin(t)':y=335:w=70:h=8:color=0xffffff:t=fill"
)
# A two-layer cake on a stand, turning a little.
CAKE = (
    "color=c=0xf3eee6:size=360x640:rate=15:duration=6,"
    "drawbox=x=60:y=470:w=240:h=14:color=0x7a5a3a:t=fill,"
    "drawbox=x='90+6*sin(t*1.3)':y=330:w=180:h=70:color=0xf2a7c3:t=fill,"
    "drawbox=x='110+6*sin(t*1.3)':y=270:w=140:h=60:color=0xf7c6d9:t=fill,"
    "drawbox=x='90+6*sin(t*1.3)':y=400:w=180:h=70:color=0x8a4b2d:t=fill"
)


def render(name: str, graph: str) -> None:
    target = SAMPLES / name
    subprocess.run(  # noqa: S603 - fixed arguments
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", graph, *X264, str(target)],  # noqa: S607
        check=True,
    )
    print(target, target.stat().st_size)


if __name__ == "__main__":
    SAMPLES.mkdir(exist_ok=True)
    render("synthetic-sneaker.mp4", SNEAKER)
    render("synthetic-cake.mp4", CAKE)
