"""QR code poster for the shop counter (feature 36).

An A4 page with the shop's name, the product picture, the offer and price the owner set, and
a large QR code that opens the game. Every word on it comes from the tested game or from
this file, never from a model. Before the poster is saved, its QR code is read back from a
picture of the page, so a poster that does not open the game is never handed to the shop.

The QR code carries ``?from=qr``, so the shop can see how many plays came from the counter
(nothing about the player is in it).
"""

from __future__ import annotations

import base64
import html
import io
import re
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
import segno
from PIL import Image

from reel2play.playtest.session import Harness

ATTRIBUTION = "Built with Muse Spark Open"
A4_CSS_PX = (794, 1123)  # 210 x 297 mm at 96 CSS pixels per inch
PREVIEW_WIDTH = 480
FONTS = {
    "ur": '"Noto Nastaliq Urdu", "Jameel Noori Nastaleeq", "Noto Naskh Arabic", "Segoe UI", '
    "sans-serif",
    "en": 'ui-rounded, "SF Pro Rounded", "Segoe UI", Roboto, system-ui, sans-serif',
}
WORDS: dict[str, dict[str, str]] = {
    "en": {
        "scan": "Scan to play",
        "how": "Point your phone camera at the code, play the game and win your code.",
        "how_plain": "Point your phone camera at the code and play the game.",
        "or_open": "Or open",
        "synthetic": "Synthetic test data",
    },
    "ur": {
        "scan": "اسکین کریں اور کھیلیں",
        "how": "فون کا کیمرہ کوڈ پر رکھیں، گیم کھیلیں اور اپنا کوڈ جیتیں۔",
        "how_plain": "فون کا کیمرہ کوڈ پر رکھیں اور گیم کھیلیں۔",
        "or_open": "یا کھولیں",
        "synthetic": "Synthetic test data",
    },
}
GREETINGS = {
    "ramzan": {"en": "Ramzan Kareem", "ur": "رمضان کریم"},
    "eid": {"en": "Eid Mubarak", "ur": "عید مبارک"},
    "independence_day": {"en": "Happy Independence Day", "ur": "یومِ آزادی مبارک"},
    "wedding_season": {"en": "Wedding season", "ur": "شادیوں کا موسم"},
    "winter_sale": {"en": "Winter sale", "ur": "سردیوں کی سیل"},
}
PAGE_OBJECT = re.compile(rb"/Type\s*/Page(?!s)")


def poster_link(link: str) -> str:
    """The link inside the QR code: the game page, marked as coming from the poster."""
    return f"{link}?from=qr"


def qr_svg(data: str) -> str:
    """The QR code as inline SVG, medium error correction, with the standard quiet zone."""
    code = segno.make(data, error="m", micro=False)
    svg: str = code.svg_inline(scale=1, border=4, omitsize=True, dark="#111318", light="#ffffff")
    return svg.replace("<svg ", '<svg role="img" aria-label="QR code" ', 1)


@dataclass(frozen=True)
class PosterFacts:
    """What the poster says. All of it was on the tested game or set by the owner."""

    shop_name: str
    title: str
    product_name: str
    offer: str | None
    price: str | None
    language: str
    direction: str
    palette: dict[str, str]
    product_image: str  # a data URL of the product cut-out
    link: str
    coupon: str | None = None
    theme: str = "none"
    synthetic: bool = False


def facts_from(
    config: dict[str, Any], *, shop_name: str, link: str, product_image: str, synthetic: bool
) -> PosterFacts:
    text = config["text"]
    return PosterFacts(
        shop_name=shop_name,
        title=text["title"],
        product_name=text["productName"],
        offer=text.get("offer"),
        price=text.get("price"),
        language=config["language"],
        direction=config["direction"],
        palette=config["palette"],
        product_image=product_image,
        link=link,
        coupon=config.get("coupon"),
        theme=config.get("theme") or "none",
        synthetic=synthetic,
    )


def poster_html(facts: PosterFacts) -> str:
    """One A4 page. Neutral paper, the shop's colours on the raised QR card and the offer."""
    e = html.escape
    words = WORDS[facts.language]
    p = facts.palette
    greeting = GREETINGS.get(facts.theme, {}).get(facts.language)
    printed = re.sub(r"^https?://", "", facts.link)
    parts = {
        "greeting": f'<p class="greeting">{e(greeting)}</p>' if greeting else "",
        "offer": f'<p class="offer">{e(facts.offer)}</p>' if facts.offer else "",
        "price": f'<p class="price" dir="auto">{e(facts.price)}</p>' if facts.price else "",
        "synthetic": (
            f'<p class="synthetic" lang="en" dir="ltr">{e(words["synthetic"])}</p>'
            if facts.synthetic
            else ""
        ),
    }
    how = words["how"] if facts.coupon else words["how_plain"]
    return f"""<!doctype html>
<html lang="{e(facts.language)}" dir="{e(facts.direction)}">
<head>
<meta charset="utf-8">
<title>{e(facts.shop_name)}: {e(facts.title)}</title>
<style>
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; }}
body {{
  width: 210mm; height: 297mm; overflow: hidden;
  font-family: {FONTS[facts.language]};
  color: #1b1d24; background: #f6f6f4;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}}
.sheet {{
  height: 100%; padding: 14mm 15mm 11mm;
  display: grid; grid-template-rows: auto auto 1fr auto; gap: 7mm;
  background:
    radial-gradient(120mm 90mm at 85% 0%,
      color-mix(in srgb, {p["primary"]} 16%, transparent), transparent 70%),
    radial-gradient(110mm 80mm at 0% 100%,
      color-mix(in srgb, {p["accent"]} 14%, transparent), transparent 70%),
    #f6f6f4;
}}
header {{ display: flex; align-items: center; justify-content: space-between; gap: 6mm; }}
.shop {{ margin: 0; font-size: 13mm; line-height: 1.15; font-weight: 900;
  letter-spacing: -0.01em; }}
.greeting {{
  margin: 0; padding: 2.2mm 5mm; border-radius: 99px; white-space: nowrap;
  font-size: 5mm; font-weight: 800; color: {p["primaryInk"]}; background: {p["primary"]};
  box-shadow: 0 1.2mm 0 color-mix(in srgb, {p["primary"]} 60%, black);
}}
.product {{
  display: grid; grid-template-columns: 70mm 1fr; align-items: center; gap: 8mm;
  padding: 7mm; border-radius: 9mm; background: #ffffff;
  box-shadow: inset 0 0 0 0.3mm #e4e4e0, 0 2mm 0 #dcdcd6, 0 7mm 14mm -6mm rgb(0 0 0 / 0.25);
}}
.product img {{ width: 70mm; height: 62mm; object-fit: contain;
  filter: drop-shadow(0 3mm 3mm rgb(0 0 0 / 0.2)); }}
.facts {{ display: grid; gap: 4mm; justify-items: start; }}
.title {{ margin: 0; font-size: 9mm; line-height: 1.2; font-weight: 900; }}
.name {{ margin: 0; font-size: 6mm; color: #4a4d57; font-weight: 700; }}
.offer {{
  margin: 0; padding: 2.4mm 6mm; border-radius: 99px; font-size: 7mm; font-weight: 900;
  color: {p["accentInk"]}; background: {p["accent"]};
  box-shadow: 0 1.4mm 0 color-mix(in srgb, {p["accent"]} 60%, black);
}}
.price {{ margin: 0; font-size: 10mm; font-weight: 900; unicode-bidi: isolate; }}
.scan {{
  display: grid; justify-items: center; align-content: center; gap: 4mm;
  padding: 8mm 8mm 7mm; border-radius: 11mm; background: #ffffff;
  box-shadow: inset 0 0 0 0.8mm {p["primary"]},
    0 3mm 0 color-mix(in srgb, {p["primary"]} 70%, black),
    0 10mm 18mm -8mm rgb(0 0 0 / 0.35);
}}
.qr {{ width: 92mm; height: 92mm; }}
.qr svg {{ width: 100%; height: 100%; display: block; shape-rendering: crispEdges; }}
.scan h2 {{ margin: 0; font-size: 11mm; font-weight: 900; color: {p["primary"]}; }}
.scan p {{ margin: 0; max-width: 140mm; text-align: center; font-size: 5.4mm; line-height: 1.5;
  color: #3b3e48; }}
.link {{ font-size: 5mm; color: #3b3e48; }}
.link strong {{ direction: ltr; unicode-bidi: isolate; color: #1b1d24; }}
footer {{ display: flex; justify-content: space-between; align-items: end; gap: 6mm; }}
footer p {{ margin: 0; font-size: 3.6mm; color: #6b6e78; }}
.synthetic {{ padding: 1mm 3mm; border-radius: 2mm; background: #fde68a;
  color: #4a3b00 !important; }}
</style>
</head>
<body>
<main class="sheet">
  <header>
    <h1 class="shop">{e(facts.shop_name)}</h1>
    {parts["greeting"]}
  </header>
  <section class="product">
    <img src="{e(facts.product_image)}" alt="{e(facts.product_name)}">
    <div class="facts">
      <p class="title">{e(facts.title)}</p>
      <p class="name">{e(facts.product_name)}</p>
      {parts["offer"]}
      {parts["price"]}
    </div>
  </section>
  <section class="scan">
    <div class="qr" data-r2p="qr">{qr_svg(poster_link(facts.link))}</div>
    <h2>{e(words["scan"])}</h2>
    <p>{e(how)}</p>
    <p class="link">{e(words["or_open"])} <strong>{e(printed)}</strong></p>
  </section>
  <footer>
    <p lang="en" dir="ltr">{e(ATTRIBUTION)}</p>
    {parts["synthetic"]}
  </footer>
</main>
</body>
</html>
"""


def read_qr(png: bytes) -> str | None:
    """Read the QR code back from a picture of the poster, the way a phone camera would."""
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    detector = cv2.QRCodeDetector()
    for scale in (1.0, 0.5):
        picture = image if scale == 1.0 else cv2.resize(image, None, fx=scale, fy=scale)
        text, _, _ = detector.detectAndDecode(picture)
        if text:
            return str(text)
    return None


def page_count(pdf: bytes) -> int:
    return len(PAGE_OBJECT.findall(pdf))


def preview(png: bytes) -> bytes:
    """A small JPEG of the poster for the share card."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    height = round(image.height * PREVIEW_WIDTH / image.width)
    out = io.BytesIO()
    image.resize((PREVIEW_WIDTH, height)).save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


@dataclass(frozen=True)
class Poster:
    pdf: bytes
    png: bytes
    read_back: str | None
    pages: int
    problems: list[str] = field(default_factory=list)


def check_poster(pdf: bytes, png: bytes, expected: str) -> Poster:
    read_back = read_qr(png)
    pages = page_count(pdf)
    problems: list[str] = []
    if not pdf.startswith(b"%PDF-"):
        problems.append("the poster is not a PDF")
    if pages != 1:
        problems.append(f"the poster has {pages} pages instead of one")
    if read_back != expected:
        problems.append("the QR code on the poster could not be read back as the game link")
    return Poster(pdf, png, read_back, pages, problems)


def make_poster(harness: Harness, facts: PosterFacts) -> Poster:
    """Print the poster in the sandboxed browser (no network) and check it."""
    page = poster_html(facts).encode("utf-8")
    reply = harness.call("poster", html_b64=base64.b64encode(page).decode("ascii"))
    pdf = base64.b64decode(reply["pdf_b64"])
    png = base64.b64decode(reply["png_b64"])
    return check_poster(pdf, png, poster_link(facts.link))
