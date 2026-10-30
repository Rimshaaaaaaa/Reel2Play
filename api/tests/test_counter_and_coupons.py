"""The counter poster (feature 36), the website embed (feature 37) and unique win codes with
redemption (feature 40)."""

from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.builder.cta import coupon_code
from reel2play.db import utcnow
from reel2play.insights import stats_for
from reel2play.jobs.queue import run_due
from reel2play.models import Ad, AdStatus, Coupon, Event, EventSource
from reel2play.playtest.session import LocalHarness
from reel2play.publish.embed import embed_code, embeds
from reel2play.publish.poster import (
    PosterFacts,
    check_poster,
    make_poster,
    page_count,
    poster_html,
    poster_link,
    preview,
    read_qr,
)
from reel2play.ratelimit import RateLimiter, caller_key
from reel2play.routes.coupons import LIMITS, new_code, tidy
from reel2play.settings import get_settings
from tests.helpers import OWNER_FIELDS, ad_for

SYNTHETIC = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic"
PALETTE = {
    "background": "#fff7ed",
    "surface": "#ffffff",
    "primary": "#9a3412",
    "primaryInk": "#ffffff",
    "accent": "#facc15",
    "accentInk": "#1f1300",
    "ink": "#1c1917",
    "muted": "#57534e",
}


def facts(**changes: object) -> PosterFacts:
    sprite = (SYNTHETIC / "synthetic-sprite.png").read_bytes()
    base: dict[str, object] = {
        "shop_name": "Synthetic Sweets",
        "title": "Catch the cupcakes!",
        "product_name": "Rose cupcake",
        "offer": "20% off this week",
        "price": "Rs 450",
        "language": "en",
        "direction": "ltr",
        "palette": PALETTE,
        "product_image": "data:image/png;base64," + base64.b64encode(sprite).decode(),
        "link": "https://play.example/g/AbC1234",
        "coupon": "R2P-7KQD",
        "theme": "eid",
        "synthetic": True,
    }
    return PosterFacts(**{**base, **changes})  # type: ignore[arg-type]


# --- feature 36: the counter poster ----------------------------------------------------------


def test_the_poster_is_one_a4_page_whose_qr_code_opens_the_game() -> None:
    harness = LocalHarness()
    try:
        english = make_poster(harness, facts())
        urdu = make_poster(
            harness,
            facts(
                language="ur",
                direction="rtl",
                shop_name="سنتھیٹک مٹھائی",
                title="کپ کیک پکڑیں!",
                theme="none",
                coupon=None,
            ),
        )
    finally:
        harness.close()
    for poster in (english, urdu):
        assert poster.problems == []
        assert poster.pages == 1
        assert poster.read_back == "https://play.example/g/AbC1234?from=qr"
        assert poster.pdf.startswith(b"%PDF-")
        assert len(poster.pdf) < 600_000
    small = preview(english.png)
    assert small[:2] == b"\xff\xd8"


def test_the_poster_says_only_tested_words_escaped_with_the_attribution() -> None:
    page = poster_html(facts(offer='<script>alert("x")</script>', price=None))
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
    assert "Built with Muse Spark Open" in page
    assert "Synthetic test data" in page
    assert "Eid Mubarak" in page
    assert "win your code" in page
    assert 'class="price"' not in page
    plain = poster_html(facts(coupon=None, synthetic=False, theme="none", offer=None))
    assert "win your code" not in plain
    assert "Synthetic test data" not in plain
    assert 'class="greeting"' not in plain
    assert 'class="offer"' not in plain
    urdu = poster_html(facts(language="ur", direction="rtl"))
    assert 'dir="rtl"' in urdu
    assert "اسکین کریں اور کھیلیں" in urdu
    assert "عید مبارک" in urdu


def test_a_poster_that_does_not_scan_is_not_handed_over() -> None:
    blank = (SYNTHETIC / "synthetic-sprite.png").read_bytes()
    checked = check_poster(b"not a pdf", blank, poster_link("https://play.example/g/AbC1234"))
    assert checked.read_back is None
    assert checked.problems == [
        "the poster is not a PDF",
        "the poster has 0 pages instead of one",
        "the QR code on the poster could not be read back as the game link",
    ]
    assert read_qr(b"not an image") is None
    two = b"%PDF-1.7 /Type /Pages /Type /Page x /Type /Page y"
    assert page_count(two) == 2


# --- feature 37: the website embed -----------------------------------------------------------


def test_embed_code_is_a_short_safe_iframe_marked_as_from_the_website() -> None:
    tall, wide = embeds("https://play.example/g/AbC1234", 'Play: "Rose" <cupcake>')
    assert tall.src == "https://play.example/g/AbC1234?from=embed"
    assert wide.src == "https://play.example/g/AbC1234?layout=landscape&from=embed"
    assert tall.code.startswith('<iframe src="https://play.example/g/AbC1234?from=embed"')
    assert "aspect-ratio:9 / 16" in tall.code
    assert "layout=landscape&amp;from=embed" in wide.code
    assert 'title="Play: &quot;Rose&quot; &lt;cupcake&gt;"' in wide.code
    assert 'referrerpolicy="no-referrer"' in wide.code
    assert "<script" not in tall.code + wide.code
    assert len(embed_code("https://p.example/g/AbC1234", "Play", "tall").code) < 400


# --- feature 40: unique win codes --------------------------------------------------------------


@pytest.fixture
def published(
    client: TestClient, session: Session, sample_media: dict[str, Path], stop_after_build: None
) -> dict[str, str]:
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **OWNER_FIELDS}
    video = sample_media["product_video"]
    body = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    ).json()
    run_due("test", max_jobs=10)
    ad = ad_for(session, body["id"])
    session.execute(
        update(Ad).where(Ad.id == ad.id).values(status=AdStatus.PUBLISHED, slug="AbC1234")
    )
    session.commit()
    LIMITS.clear()
    return {"ad": str(ad.id), "key": body["shop_key"]}


def ask(client: TestClient, ad: str, **extra: str) -> tuple[int, dict[str, str], dict[str, str]]:
    response = client.post(
        "/api/coupons",
        content=json.dumps({"ad": ad, "variant": "A", **extra}),
        headers={"Content-Type": "text/plain", "Origin": "null"},
    )
    return response.status_code, response.json(), dict(response.headers)


def test_a_win_gets_a_unique_code_that_the_shop_redeems_once(
    client: TestClient, session: Session, published: dict[str, str]
) -> None:
    ad, key = published["ad"], published["key"]
    status, body, headers = ask(client, ad, **{"from": "qr"})
    assert status == 201
    code = body["code"]
    assert re.fullmatch(r"R2P-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}", code)
    assert headers["access-control-allow-origin"] == "*"
    assert headers["cache-control"] == "no-store"
    stored = session.scalars(select(Coupon)).one()
    assert (stored.code, stored.source, stored.redeemed_at) == (code, "qr", None)
    columns = set(Coupon.__table__.columns.keys())
    assert columns == {"id", "ad_id", "code", "variant", "source", "created_at", "redeemed_at"}

    # The owner types it any way they like.
    typed = code.lower().replace("-", " ")
    first = client.post(
        "/api/shop/coupons/redeem", json={"code": typed}, headers={"X-Shop-Key": key}
    ).json()
    assert first["result"] == "redeemed"
    assert first["code"] == code
    assert first["product"]
    assert "marked as used" in first["message"]
    again = client.post(
        "/api/shop/coupons/redeem", json={"code": code}, headers={"X-Shop-Key": key}
    ).json()
    assert again["result"] == "already_used"
    assert "Each code works once" in again["message"]
    shared = client.post(
        "/api/shop/coupons/redeem",
        json={"code": coupon_code(uuid.UUID(ad))},
        headers={"X-Shop-Key": key},
    ).json()
    assert shared["result"] == "shared_code"
    unknown = client.post(
        "/api/shop/coupons/redeem", json={"code": "R2P-ZZZZ-ZZZZ"}, headers={"X-Shop-Key": key}
    ).json()
    assert unknown["result"] == "not_found"
    assert (
        client.post("/api/shop/coupons/redeem", json={"code": code}).status_code == 401
    )  # no studio key
    assert "coupon.redeemed" in [e.action for e in audit.entries_for(session, "ad", stored.ad_id)]

    summary = client.get("/api/shop/coupons", headers={"X-Shop-Key": key}).json()
    assert (summary["issued"], summary["redeemed"]) == (1, 1)
    assert summary["recent"][0]["code"] == code
    assert summary["by_ad"] == [{"ad_id": ad, "issued": 1, "redeemed": 1}]


def test_codes_are_limited_per_phone_and_per_game_per_day(
    client: TestClient, session: Session, published: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ad = published["ad"]
    limit = get_settings().coupons_per_visitor
    codes = {ask(client, ad)[1]["code"] for _ in range(limit)}
    assert len(codes) == limit
    status, body, headers = ask(client, ad)
    assert (status, body["detail"]) == (429, "Too many codes from this phone.")
    assert headers["access-control-allow-origin"] == "*"

    LIMITS.clear()
    monkeypatch.setattr(get_settings(), "coupons_per_ad_per_day", limit)
    status, body, _ = ask(client, ad)
    assert (status, body["detail"]) == (429, "This game has given all of today's codes.")
    session.execute(update(Coupon).values(created_at=utcnow() - timedelta(days=2)))
    session.commit()
    assert ask(client, ad)[0] == 201


def test_only_published_games_give_codes_and_bad_requests_are_refused(
    client: TestClient, session: Session, published: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ad = published["ad"]
    assert ask(client, "00000000-0000-0000-0000-000000000000")[0] == 404
    assert client.post("/api/coupons", content="nope").status_code == 400
    assert client.post("/api/coupons", content="x" * 300).status_code == 413
    session.execute(update(Ad).values(status=AdStatus.TESTING))
    session.commit()
    assert ask(client, ad)[0] == 404
    monkeypatch.setattr(get_settings(), "unique_coupons", False)
    assert ask(client, ad)[0] == 404


def test_typed_codes_are_tidied_and_new_codes_are_readable() -> None:
    assert tidy("r2p k7qd m2xp") == "R2P-K7QD-M2XP"
    assert tidy("K7QDM2XP") == "R2P-K7QD-M2XP"
    assert tidy("r2p-7kqd") == "R2P-7KQD"
    assert tidy(" odd ") == "ODD"
    for _ in range(50):
        assert not set(new_code()[4:]) & set("01OI")


def test_the_rate_limiter_forgets_and_never_keeps_the_address() -> None:
    now = [0.0]
    limiter = RateLimiter(2, 10, clock=lambda: now[0])
    key = caller_key("203.0.113.7", "ad")
    assert "203.0.113.7" not in key
    assert limiter.allow(key)
    assert limiter.allow(key)
    assert not limiter.allow(key)
    now[0] = 11
    assert limiter.allow(key)
    limiter._forget_idle(now[0] + 20)
    assert limiter._seen == {}
    limiter.clear()


# --- plays from the poster and the website -------------------------------------------------------


def test_plays_from_the_poster_and_the_website_are_counted_apart(
    client: TestClient, session: Session, published: dict[str, str]
) -> None:
    ad = published["ad"]
    for source in ("qr", "qr", "embed", None):
        body: dict[str, str] = {"ad": ad, "event": "play"}
        if source:
            body["from"] = source
        assert client.post("/api/events", content=json.dumps(body)).status_code == 204
    bad = {"ad": ad, "event": "play", "from": "someone@example.com"}
    assert client.post("/api/events", content=json.dumps(bad)).status_code == 400
    assert {e.source for e in session.scalars(select(Event))} == {
        EventSource.QR,
        EventSource.EMBED,
        EventSource.LINK,
    }
    [stats] = stats_for(session, [uuid.UUID(ad)]).values()
    assert (stats.plays, stats.poster_plays, stats.website_plays) == (4, 2, 1)
    studio = client.get("/api/shop", headers={"X-Shop-Key": published["key"]}).json()
    assert studio["ads"][0]["stats"]["poster_plays"] == 2
