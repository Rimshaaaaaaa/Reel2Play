"""The 13 quality gates on hand-made evidence: each one passes and fails for its reason."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from reel2play.analysis import CreativeBrief
from reel2play.builder.theme import build_palette
from reel2play.gates import (
    GATES,
    can_be_won,
    cta_works,
    finish_time,
    fits_screen,
    honest_claims,
    loads_fast,
    looks_like_product,
    no_errors,
    no_network,
    offer_shown,
    readable_text,
    rights,
    run_gates,
    size,
)
from reel2play.gates.base import CriticReview, Evidence, RunSummary, ScreenCheck
from reel2play.gates.readable_text import css_hex

BRIEF = CreativeBrief.model_validate(
    {
        "product": {
            "name": "Sneaker",
            "category": "shoes",
            "description": "",
            "segment_prompt": "shoe",
        },
        "palette": ["#c8243a", "#f2b705"],
        "mood": "m",
        "audience": "a",
        "tone_of_voice": "t",
        "language": "en",
        "price": "Rs 2,499",
        "offer_text": "20% off",
        "offer_source": "owner",
        "cod_available": False,
        "free_delivery": False,
        "seen_price": None,
        "cta": {"kind": "whatsapp", "target": "923001234567"},
        "key_frames": [{"index": 0, "time_s": 0, "key": "k", "reason": "r"}],
    }
)


def end_card(**part_changes: Any) -> dict[str, Any]:
    box = {"x": 20, "y": 100, "width": 300, "height": 40}
    parts = {
        name: {"text": text, "box": box, "visible": True, "clipped": False, "href": None}
        for name, text in (
            ("result", "You won!"),
            ("offer", "20% off"),
            ("price", "Rs 2,499"),
            ("cta", "Order"),
        )
    }
    for name, change in part_changes.items():
        parts[name] = {**parts[name], **change}
    return {
        "visible": True,
        "stage": {"x": 0, "y": 0, "width": 360, "height": 640},
        "viewport": {"width": 360, "height": 640},
        "parts": parts,
        "styles": [
            {
                "text": "You won!",
                "color": "rgb(35, 35, 46)",
                "background": "rgb(251, 251, 253)",
                "size": 26,
            }
        ],
    }


def evidence(**changes: Any) -> Evidence:
    palette = build_palette(BRIEF.palette)
    screen = ScreenCheck(360, 640, 120, end_card(), "shots/phone.png")
    base = Evidence(
        brief=BRIEF,
        config={
            "text": {
                "title": "Catch!",
                "instruction": "Tap.",
                "win": "Yay",
                "lose": "Aw",
                "ctaLabel": "Order",
                "productName": "Sneaker",
                "offer": "20% off",
                "price": "Rs 2,499",
            },
            "palette": palette.model_dump(by_alias=True),
        },
        palette=palette,
        size_bytes=40_000,
        rights_confirmed=True,
        audio_removed=True,
        runs=[RunSummary(i, "scripted", True, s, 30) for i, s in enumerate((16.0, 18.0, 21.0))],
        screens={"phone": screen, "tablet": replace(screen, width=768, height=1024)},
        cta={
            "href": "https://wa.me/923001234567?text=Sneaker",
            "popups": ["https://wa.me/x"],
            "message": "I want to order: Sneaker. My code: R2P-AAAA",
        },
        log={"console_errors": [], "requests": [], "navigations": []},
        critic=CriticReview(
            product_matches=True,
            offer_visible=True,
            price_matches=True,
            text_readable=True,
            language_ok=True,
        ),
        gameplay_key="shots/gameplay.png",
    )
    return replace(base, **changes)


def test_good_evidence_passes_every_gate() -> None:
    results = run_gates(evidence())
    assert len(results) == len(GATES) == 13
    assert [r.gate for r in results if not r.passed] == []
    assert all(r.message for r in results)


@pytest.mark.parametrize(
    ("module", "bad", "words"),
    [
        (
            loads_fast,
            {"screens": {"phone": ScreenCheck(360, 640, 2600, end_card(), "k")}},
            "2600 ms",
        ),
        (size, {"size_bytes": 3 * 1024 * 1024}, "limit is 2 MB"),
        (no_network, {"log": {"requests": ["https://x"], "navigations": []}}, "1 request"),
        (
            can_be_won,
            {"runs": [RunSummary(0, "s", False, 20, 1), RunSummary(1, "s", True, 20, 1)]},
            "won only 1 of 2",
        ),
        (finish_time, {"runs": [RunSummary(0, "s", True, 9, 1)]}, "too short"),
        (finish_time, {"runs": [RunSummary(0, "s", True, 31, 1)]}, "too long"),
        (finish_time, {"runs": []}, "too short"),
        (no_errors, {"log": {"console_errors": ["TypeError: x"]}}, "1 error"),
        (rights, {"audio_removed": False}, "not removed"),
    ],
)
def test_each_gate_fails_for_its_reason(module: Any, bad: dict[str, Any], words: str) -> None:
    result = module.check(evidence(**bad))
    assert not result.passed
    assert words in result.message


def test_offer_shown_checks_page_text_and_critic() -> None:
    wrong_price = evidence(
        screens={"phone": ScreenCheck(360, 640, 100, end_card(price={"text": "Rs 2,49"}), "k")}
    )
    assert "'Rs 2,49'" in offer_shown.check(wrong_price).message
    no_offer = evidence(
        screens={"phone": ScreenCheck(360, 640, 100, end_card(offer={"visible": False}), "k")}
    )
    assert "offer is not on the end card" in offer_shown.check(no_offer).message
    hidden = dict(end_card(), visible=False)
    assert (
        "did not appear"
        in offer_shown.check(
            evidence(screens={"phone": ScreenCheck(360, 640, 1, hidden, "k")})
        ).message
    )
    critic = CriticReview(
        product_matches=True,
        offer_visible=False,
        price_matches=False,
        price_seen="Rs 2,4",
        text_readable=True,
        language_ok=True,
    )
    result = offer_shown.check(evidence(critic=critic))
    assert not result.passed
    assert "could not read the offer" in result.message
    assert result.screenshot_key == "shots/phone.png"


def test_cta_gate_for_whatsapp_and_links() -> None:
    assert not cta_works.check(
        evidence(cta={"href": "https://evil.example", "popups": ["x"], "message": "Sneaker"})
    ).passed
    assert not cta_works.check(
        evidence(cta={"href": "https://wa.me/1?text=hi", "popups": [], "message": "hi"})
    ).passed
    other_number = cta_works.check(
        evidence(cta={"href": "https://wa.me/111?text=x", "popups": ["x"], "message": "Sneaker"})
    )
    assert not other_number.passed
    assert other_number.measured == {
        "opens": "wa.me",
        "opened": True,
        "to_shop_number": False,
        "order_written": True,
    }
    assert "923001234567" not in str(cta_works.check(evidence()).measured)
    link_brief = BRIEF.model_copy(
        update={"cta": BRIEF.cta.model_copy(update={"kind": "link", "target": "https://shop.pk"})}
    )
    assert cta_works.check(
        evidence(brief=link_brief, cta={"href": "https://shop.pk", "popups": ["https://shop.pk"]})
    ).passed
    assert not cta_works.check(evidence(brief=link_brief, cta={"href": None})).passed


def test_fits_screen_finds_overflow_and_clipping() -> None:
    off = end_card(cta={"box": {"x": 20, "y": 620, "width": 300, "height": 60}})
    clipped = end_card(offer={"clipped": True})
    result = fits_screen.check(
        evidence(
            screens={
                "phone": ScreenCheck(360, 640, 1, off, "phone.png"),
                "tablet": ScreenCheck(768, 1024, 1, clipped, "tablet.png"),
            }
        )
    )
    assert not result.passed
    assert "phone: the cta is outside the game area" in result.measured["problems"]
    assert "tablet: the offer text is cut off" in result.measured["problems"]
    assert result.screenshot_key == "phone.png"
    big = dict(end_card(), stage={"x": 0, "y": 0, "width": 400, "height": 700})
    assert (
        "larger than the screen"
        in fits_screen.check(
            evidence(screens={"phone": ScreenCheck(360, 640, 1, big, "k")})
        ).message
    )
    gone = dict(end_card(), stage=None)
    assert (
        "did not show"
        in fits_screen.check(
            evidence(screens={"phone": ScreenCheck(360, 640, 1, gone, "k")})
        ).message
    )
    missing_box = end_card(price={"box": None})
    assert not fits_screen.check(
        evidence(screens={"phone": ScreenCheck(360, 640, 1, missing_box, "k")})
    ).passed


def shaped(layout: str | None, side: dict[str, Any] | None) -> dict[str, Any]:
    card = end_card()
    stage = {"x": 600, "y": 10, "width": 293, "height": 520}
    parts = {k: {**v, "box": {"x": 620, "y": 200, "width": 250, "height": 40}}
             for k, v in card["parts"].items()}  # fmt: skip
    return {**card, "stage": stage, "viewport": {"width": 960, "height": 540}, "parts": parts,
            "layout": layout, "side": side}  # fmt: skip


def test_fits_screen_checks_square_and_landscape_pages() -> None:
    panel = {"x": 20, "y": 10, "width": 560, "height": 520}
    good = evidence(
        screens={"landscape": ScreenCheck(960, 540, 1, shaped("landscape", panel), "wide.png")}
    )
    assert fits_screen.check(good).passed
    assert "square and landscape pages" in fits_screen.check(good).message
    portrait = shaped("portrait", panel)
    off = shaped("landscape", {**panel, "x": 700})
    result = fits_screen.check(
        evidence(
            screens={
                "landscape": ScreenCheck(960, 540, 1, off, "wide.png"),
                "square": ScreenCheck(540, 540, 1, portrait, "square.png"),
            }
        )
    )
    assert result.measured["problems"] == [
        "landscape: the offer panel is outside the screen",
        "square: the page did not take the square shape",
    ]


def test_product_and_readability_use_the_critic() -> None:
    assert not looks_like_product.check(evidence(critic=None)).passed
    bad = CriticReview(
        product_matches=False,
        product_notes="a broken fragment",
        offer_visible=True,
        price_matches=True,
        text_readable=False,
        language_ok=False,
    )
    result = looks_like_product.check(evidence(critic=bad))
    assert "a broken fragment" in result.message
    readable = readable_text.check(evidence(critic=bad))
    assert "hard to read" in readable.message
    assert "wrong language" in readable.message


def test_readable_text_measures_the_page() -> None:
    styles = [
        {"text": "Faint", "color": "rgb(200, 200, 200)", "background": "rgb(255, 255, 255)"},
        {"text": "Glass", "color": "rgb(0, 0, 0)", "background": "rgba(255, 255, 255, 0.5)"},
    ]
    card = dict(end_card(), styles=styles)
    result = readable_text.check(evidence(screens={"phone": ScreenCheck(360, 640, 1, card, "k")}))
    assert not result.passed
    assert "'Faint'" in result.message
    assert css_hex("rgb(1, 2, 3)") == "#010203"
    assert css_hex("linear-gradient(red, blue)") is None
    bad_palette = build_palette(BRIEF.palette).model_copy(update={"muted": "#eeeeee"})
    assert not readable_text.check(evidence(palette=bad_palette)).passed


def test_honest_claims_catches_made_up_numbers() -> None:
    text = dict(evidence().config["text"])
    made_up = dict(text, offer="50% off", title="Only Rs 99!", price="Rs 1")
    result = honest_claims.check(evidence(config={"text": made_up}))
    assert not result.passed
    problems = result.measured["problems"]
    assert "the game's price is not the owner's price" in problems
    assert "the offer has numbers the owner did not give" in problems
    assert "the title mentions a price" in problems
