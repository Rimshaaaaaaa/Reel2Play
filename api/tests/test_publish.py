"""Publishing pieces on their own (features 32 to 35): Reel timing and encoding, the link
preview, the hosted page's tags, the Meta playable checks, and the captions' honesty."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from reel2play.ai.client import NO_SUBJECT
from reel2play.ai.messages import ChatResponse
from reel2play.ai.prompts import load_prompt
from reel2play.analysis import CreativeBrief
from reel2play.builder.html import BuiltGame
from reel2play.media.video import probe
from reel2play.playtest.replay import Frame, Recording
from reel2play.publish import meta
from reel2play.publish.captions import (
    CaptionDraft,
    clean_hashtags,
    code_draft,
    finish,
    honest,
    write_captions,
)
from reel2play.publish.hosted import (
    SLUG_LENGTH,
    new_slug,
    page_link,
    preview_tags,
    with_preview,
)
from reel2play.publish.reel import cut_lead_in, encode, preview_image, timeline
from reel2play.settings import get_settings
from tests.helpers import Scripted, make_client

BRIEF = CreativeBrief.model_validate(
    {
        "product": {
            "name": "Canvas sneaker",
            "category": "shoes",
            "description": "",
            "segment_prompt": "shoe",
        },
        "palette": ["#c8243a"],
        "mood": "m",
        "audience": "a",
        "tone_of_voice": "friendly",
        "language": "en",
        "price": "Rs 2,499",
        "offer_text": "20% off this week",
        "offer_source": "owner",
        "cod_available": False,
        "free_delivery": False,
        "seen_price": None,
        "cta": {"kind": "whatsapp", "target": "923001234567"},
        "key_frames": [{"index": 0, "time_s": 0, "key": "k", "reason": "r"}],
    }
)
LINK = "https://r2p.example/g/AbC1234"


def jpeg(color: str, size: tuple[int, int] = (360, 640)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG")
    return out.getvalue()


def recording(game_s: float, fps: int = 10) -> Recording:
    steps = round(game_s * fps)
    frames = [Frame(round((i + 1) / fps, 4), jpeg("#c8243a")) for i in range(steps)]
    frames.append(Frame(game_s, jpeg("#c8243a")))  # the end card, game time already stopped
    return Recording(
        intro=Frame(0, jpeg("#ffffff")),
        end=Frame(game_s, jpeg("#1c1a36")),
        frames=frames,
        won=True,
        seconds=game_s,
    )


# --- the Reel -------------------------------------------------------------------------------


@pytest.mark.parametrize(("game_s", "total"), [(18.0, 14.0), (10.0, 14.0), (4.0, 10.0)])
def test_timeline_fits_a_reel(game_s: float, total: float) -> None:
    shots = timeline(recording(game_s))
    assert shots[0].seconds == 1.0
    assert shots[-1].frame.jpeg == recording(game_s).end.jpeg
    assert sum(s.seconds for s in shots) == pytest.approx(total, abs=0.01)
    assert all(s.seconds > 0 for s in shots)
    gameplay = sum(s.seconds for s in shots[1:-1])
    assert gameplay == pytest.approx(min(game_s, 10.0), abs=0.01)


def test_reel_and_lead_in_are_encoded(tmp_path: Path) -> None:
    reel, lead_in = tmp_path / "reel.mp4", tmp_path / "lead-in.mp4"
    encode(timeline(recording(6.0, fps=5)), reel)
    found = probe(reel)
    assert (found.width, found.height) == (720, 1280)
    assert found.duration_s == pytest.approx(10.0, abs=0.2)
    assert not found.has_audio
    cut_lead_in(reel, lead_in)
    assert probe(lead_in).duration_s == pytest.approx(5.0, abs=0.2)


def test_preview_is_a_square_of_the_end_card() -> None:
    image = Image.open(io.BytesIO(preview_image(jpeg("#1c1a36", (720, 1280)))))
    assert image.format == "JPEG"
    assert image.size == (600, 600)


# --- the hosted page ------------------------------------------------------------------------


def test_short_links_are_random_codes() -> None:
    slugs = {new_slug() for _ in range(200)}
    assert len(slugs) == 200
    assert all(len(s) == SLUG_LENGTH and s.isalnum() for s in slugs)
    assert page_link("https://api.example", "AbC1234") == "https://api.example/g/AbC1234"


def test_preview_tags_are_escaped_and_placed_after_the_title() -> None:
    tags = preview_tags(
        title='Shoes "R" <Us>', description="20% off", image_url="https://x/p.jpg", page_url=LINK
    )
    assert '<meta property="og:title" content="Shoes &quot;R&quot; &lt;Us&gt;">' in tags
    page = b"<html><head><meta charset='utf-8'><title>Play</title><style></style></head></html>"
    placed = with_preview(page, tags).decode()
    assert placed.index("og:title") > placed.index("</title>")
    assert placed.index("og:title") < placed.index("<style>")
    with pytest.raises(ValueError, match="no <title>"):
        with_preview(b"<html></html>", tags)


# --- the Meta playable ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        "window.location='https://x'",
        "document.location.href=u",
        "location.replace(u)",
        "top.location=u",
        "window.open (u)",
    ],
)
def test_redirect_code_is_refused(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    html = f"<html><script>{code}</script></html>".encode()
    monkeypatch.setattr(meta, "compile_game", lambda *a: BuiltGame(html, len(html), "x"))
    with pytest.raises(meta.MetaExportError, match="redirect code"):
        meta.build_meta_html(None, get_settings())  # type: ignore[arg-type]


def test_playable_zip_holds_index_html(monkeypatch: pytest.MonkeyPatch) -> None:
    data = meta.zip_playable(b"<html>game</html>")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.namelist() == ["index.html"]
    monkeypatch.setattr(meta, "META_ZIP_MAX_BYTES", 10)
    with pytest.raises(meta.MetaExportError, match="bytes with 1 files"):
        meta.zip_playable(b"<html>game</html>")


def test_meta_check_problems() -> None:
    assert meta.MetaCheck(cta_calls=1).problems == []
    found = meta.MetaCheck(cta_calls=0, requests=["https://x"], popups=["https://y"]).problems
    assert found == [
        "the button did not call FbPlayableAd.onCTAClick()",
        "the game made 1 network request(s)",
        "the game tried to open another page",
    ]


# --- captions -------------------------------------------------------------------------------


def test_hashtags_are_cleaned() -> None:
    tags = ["#Sneakers", "shoe shop", "sneakers", "eid2026", "#", "a", "کراچی", "x" * 31]
    assert clean_hashtags([*tags, "one", "two", "three", "four"]) == [
        "Sneakers",
        "shoeshop",
        "eid",
        "کراچی",
        "one",
        "two",
    ]


def test_numbers_must_come_from_the_facts() -> None:
    facts = ["Rs 2,499", "20% off this week", "Catch 10 sneakers"]
    good = CaptionDraft(
        instagram="Catch 10 and get 20% off",
        facebook="Rs 2,499",
        whatsapp_status="Play!",
        hashtags=["shoes"],
    )
    bad = good.model_copy(update={"facebook": "Now only Rs 1,999"})
    urdu_digits = good.model_copy(update={"whatsapp_status": "۲۰% آف"})
    assert honest(good, facts)
    assert not honest(bad, facts)
    assert honest(urdu_digits, facts)


def test_finished_captions_carry_the_link_and_tags() -> None:
    draft = CaptionDraft(
        instagram="Play!",
        facebook="Play our game.",
        whatsapp_status="Play",
        hashtags=["#shoes", "sale"],
    )
    done = finish(draft, BRIEF, LINK, "model")
    assert done.instagram == "Play!\n\nPlay the game: link in bio.\n\n#shoes #sale"
    assert done.facebook == f"Play our game.\n\nPlay: {LINK}"
    assert done.whatsapp_status == f"Play\n{LINK}"
    assert done.as_json()["hashtags"] == ["shoes", "sale"]


def test_code_captions_use_only_the_owners_facts() -> None:
    draft = code_draft(BRIEF)
    assert draft.facebook == (
        "Canvas sneaker: play our 20-second game. Win and get 20% off this week. Price: Rs 2,499."
    )
    urdu = code_draft(BRIEF.model_copy(update={"language": "ur", "price": None}))
    assert "Canvas sneaker" in urdu.facebook
    assert "قیمت" not in urdu.facebook


def answers(text: dict[str, object]) -> ChatResponse:
    return ChatResponse(text=json.dumps(text))


@pytest.mark.parametrize(
    ("answer", "written_by"),
    [
        (
            {
                "instagram": "Catch 10!",
                "facebook": "20% off",
                "whatsapp_status": "Play",
                "hashtags": ["shoes"],
            },
            "model",
        ),
        (
            {
                "instagram": "70% off everything!",
                "facebook": "Rs 99",
                "whatsapp_status": "Play",
                "hashtags": [],
            },
            "code",
        ),
    ],
)
def test_write_captions(answer: dict[str, object], written_by: str) -> None:
    provider = Scripted("baseten_spark", [answers(answer)])
    captions = write_captions(
        make_client(provider, prompt_loader=load_prompt),
        NO_SUBJECT,
        shop_name="Synthetic Shoes",
        brief=BRIEF,
        game_text={"title": "Catch!", "instruction": "Catch 10 sneakers."},
        link=LINK,
    )
    assert captions.written_by == written_by
    assert captions.facebook.endswith(LINK)
