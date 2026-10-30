"""Game images, inlined as data URLs: small WebP sprites and a square product photo."""

from __future__ import annotations

import base64
import io

from PIL import Image

from reel2play.analysis import Box

SPRITE_SIDE = 320
PHOTO_SIDE = 480
LOGO_SIDE = 160


def _data_url(image: Image.Image, fmt: str, mime: str, **options: object) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **options)
    return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def _open(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def sprite_data_url(png: bytes, side: int = SPRITE_SIDE) -> str:
    """A transparent WebP no larger than ``side`` pixels."""
    image = _open(png).convert("RGBA")
    image.thumbnail((side, side), Image.Resampling.LANCZOS)
    return _data_url(image, "WEBP", "image/webp", quality=82, method=6)


def strip_data_url(png: bytes) -> str:
    """The animation strip as a transparent WebP, at its own size (frames are already small)."""
    return _data_url(_open(png).convert("RGBA"), "WEBP", "image/webp", quality=80, method=6)


def logo_data_url(png: bytes) -> str:
    return sprite_data_url(png, LOGO_SIDE)


def square_crop(width: int, height: int, box: Box | None) -> tuple[int, int, int, int]:
    """A square around the product box (with some room), kept inside the frame."""
    if box is None:
        side = min(width, height)
        left, top = (width - side) // 2, (height - side) // 2
        return left, top, left + side, top + side
    x, y, w, h = box.to_pixels(width, height)
    side = int(min(max(w, h) * 1.35, width, height))
    cx, cy = x + w / 2, y + h / 2
    left = int(min(max(cx - side / 2, 0), width - side))
    top = int(min(max(cy - side / 2, 0), height - side))
    return left, top, left + side, top + side


def photo_data_url(frame_jpeg: bytes, box: Box | None) -> str:
    """The key frame cropped square around the product, as a JPEG for the puzzle."""
    image = _open(frame_jpeg).convert("RGB")
    cropped = image.crop(square_crop(image.width, image.height, box))
    cropped = cropped.resize((PHOTO_SIDE, PHOTO_SIDE), Image.Resampling.LANCZOS)
    return _data_url(cropped, "JPEG", "image/jpeg", quality=80, optimize=True)


def plain_photo_data_url(sprite_png: bytes, colour: str) -> str:
    """Feature 55: when faces could not be checked, the "photo" is the product cut-out on a
    soft field of the shop's colour, so no frame of the video (or anyone in it) is shown."""
    sprite = _open(sprite_png).convert("RGBA")
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    soft = tuple(round(c + (255 - c) * 0.82) for c in (red, green, blue))
    field = Image.new("RGBA", (PHOTO_SIDE, PHOTO_SIDE), (*soft, 255))
    sprite.thumbnail((int(PHOTO_SIDE * 0.8), int(PHOTO_SIDE * 0.8)), Image.Resampling.LANCZOS)
    left = (PHOTO_SIDE - sprite.width) // 2
    top = (PHOTO_SIDE - sprite.height) // 2
    field.alpha_composite(sprite, (left, top))
    return _data_url(field.convert("RGB"), "JPEG", "image/jpeg", quality=80, optimize=True)
