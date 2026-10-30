"""The studio (features 39, 45, 48, 51): studio keys, anonymous game events and their
numbers, the shop's dashboard, cost per ad, and the why panel with its tamper check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.insights import GameStats, stats_for
from reel2play.jobs.queue import run_due
from reel2play.models import Ad, AdStatus, Event
from reel2play.shops import key_hash
from tests.helpers import OWNER_FIELDS, ad_for

pytestmark = pytest.mark.usefixtures("stop_after_build")


def upload_with_key(
    client: TestClient, path: Path, headers: dict[str, str] | None = None, **fields: str
) -> dict[str, object]:
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **OWNER_FIELDS, **fields}
    response = client.post(
        "/api/uploads",
        data=data,
        files=[("files", (path.name, path.read_bytes()))],
        headers=headers or {},
    )
    return {"http": response.status_code, **response.json()}


@pytest.fixture
def published(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> dict[str, str]:
    """A built ad, marked published, and its shop's studio key."""
    first = upload_with_key(client, sample_media["product_video"])
    run_due("test", max_jobs=10)
    ad = ad_for(session, first["id"])  # type: ignore[arg-type]
    session.execute(
        update(Ad).where(Ad.id == ad.id).values(status=AdStatus.PUBLISHED, slug="AbC1234")
    )
    session.commit()
    return {"ad": str(ad.id), "key": str(first["shop_key"]), "shop": str(first["shop_id"])}


# --- studio keys ----------------------------------------------------------------------------


def test_a_new_shop_gets_a_key_once_and_needs_it_after(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video = sample_media["video_silent"]
    first = upload_with_key(client, video)
    key = first["shop_key"]
    assert first["http"] == 201
    assert isinstance(key, str)
    assert len(key) >= 30
    stored = session.scalar(text("SELECT access_key_hash FROM shops"))
    assert stored == key_hash(key)
    assert key not in json.dumps([str(r) for r in session.execute(text("SELECT * FROM shops"))])

    shop = str(first["shop_id"])
    assert upload_with_key(client, video, shop_id=shop)["http"] == 403
    assert upload_with_key(client, video, {"X-Shop-Key": "wrong"}, shop_id=shop)["http"] == 403
    again = upload_with_key(client, video, {"X-Shop-Key": key}, shop_id=shop)
    assert again["http"] == 201
    assert again["shop_id"] == first["shop_id"]
    assert again["shop_key"] is None


# --- events and their numbers ---------------------------------------------------------------


def beacon(client: TestClient, body: object) -> int:
    raw = body if isinstance(body, str) else json.dumps(body)
    response = client.post("/api/events", content=raw, headers={"Content-Type": "text/plain"})
    return int(response.status_code)


def test_game_events_are_counted_without_personal_data(
    client: TestClient, session: Session, published: dict[str, str]
) -> None:
    ad = published["ad"]
    for event in (
        {"ad": ad, "event": "play", "seconds": 3},
        {"ad": ad, "event": "play"},
        {"ad": ad, "event": "play"},
        {"ad": ad, "event": "play", "variant": "B"},
        {"ad": ad, "event": "finish", "seconds": 18.26, "won": True},
        {"ad": ad, "event": "finish", "seconds": 22.0, "won": False},
        {"ad": ad, "event": "finish", "seconds": 16.0, "won": True},
        {"ad": ad, "event": "cta"},
    ):
        assert beacon(client, event) == 204
    assert beacon(client, "not json") == 400
    assert beacon(client, {"ad": ad, "event": "steal"}) == 400
    assert beacon(client, {"ad": ad, "event": "play", "variant": "AB"}) == 400
    assert beacon(client, {"ad": ad, "event": "finish", "seconds": 999}) == 400
    assert beacon(client, {"ad": ad, "event": "play", "x": "y" * 600}) == 413
    unknown = "00000000-0000-0000-0000-000000000000"
    assert beacon(client, {"ad": unknown, "event": "play"}) == 404

    rows = session.execute(text("SELECT * FROM events ORDER BY id")).mappings().all()
    assert set(rows[0]) == {
        "id", "ad_id", "variant", "kind", "seconds", "won", "source", "created_at"
    }  # fmt: skip
    assert rows[0]["seconds"] is None  # only finishes keep their time
    assert rows[4]["seconds"] == 18.3

    [stats] = stats_for(session, [session.get(Ad, rows[0]["ad_id"]).id]).values()  # type: ignore[union-attr]
    assert stats == GameStats(plays=4, finishes=3, wins=2, cta_taps=1, median_seconds=18.3)
    assert stats.completion == 0.75
    assert stats.cta_rate == 0.333
    assert GameStats().as_json()["completion"] is None
    assert stats_for(session, []) == {}
    assert session.query(Event).count() == 8


def test_unpublished_games_take_no_events(
    client: TestClient, session: Session, published: dict[str, str]
) -> None:
    session.execute(update(Ad).values(status=AdStatus.NEEDS_PERSON))
    session.commit()
    assert beacon(client, {"ad": published["ad"], "event": "play"}) == 404


# --- the dashboard --------------------------------------------------------------------------


def test_the_studio_shows_only_this_shops_ads(
    client: TestClient, session: Session, published: dict[str, str], sample_media: dict[str, Path]
) -> None:
    assert client.get("/api/shop").status_code == 401
    assert client.get("/api/shop", headers={"X-Shop-Key": "nope"}).status_code == 401
    other = upload_with_key(client, sample_media["video_silent"], shop_name="Other Shop")
    assert other["shop_id"] != published["shop"]
    beacon(client, {"ad": published["ad"], "event": "play"})

    body = client.get("/api/shop", headers={"X-Shop-Key": published["key"]}).json()
    assert body["name"] == "Synthetic Shoes"
    assert [ad["id"] for ad in body["ads"]] == [published["ad"]]
    [ad] = body["ads"]
    assert ad["product"] == "Canvas sneaker"
    assert ad["link"] == "http://testserver/g/AbC1234"
    assert ad["stats"]["plays"] == 1
    assert ad["cost"]["calls"] == 2  # the director read the video, then designed the game
    assert body["brand_kit"]["palette"][0] == "#c8243a"
    assert body["totals"] == {"ads": 1, "published": 1, "plays": 1, "cta_taps": 0, "pkr": 0.0}


# --- the why panel --------------------------------------------------------------------------


def test_the_why_panel_explains_and_detects_tampering(
    client: TestClient, session: Session, published: dict[str, str]
) -> None:
    assert client.get(f"/api/ads/{published['shop']}/why").status_code == 404
    why = client.get(f"/api/ads/{published['ad']}/why").json()
    assert why["trail_intact"] is True
    assert why["entries_checked"] == len(why["decisions"])
    actions = [d["action"] for d in why["decisions"]]
    assert actions[:2] == ["ad.created", "analyze.started"]
    done = next(d for d in why["decisions"] if d["action"] == "analysis.done")
    assert done["details"]["product"] == "Canvas sneaker"
    assert "message" not in done["details"]
    assert why["builds"][0]["reason"].startswith("A light, quick product")
    assert why["fixes"] == []
    assert why["cost"]["calls"] == 2
    assert set(why["cost_by_role"]) >= {"director"}

    session.execute(
        text(
            "UPDATE audit_log SET data = jsonb_set(data, '{product}', '\"Something else\"') "
            "WHERE action = 'analysis.done'"
        )
    )
    session.commit()
    tampered = client.get(f"/api/ads/{published['ad']}/why").json()
    assert tampered["trail_intact"] is False


def test_verify_entries_needs_a_real_link(session: Session) -> None:
    first = audit.record(session, actor="t", action="a", subject_type="x", subject_id="1")
    second = audit.record(session, actor="t", action="b", subject_type="x", subject_id="1")
    assert audit.verify_entries(session, [first, second]).ok
    second.prev_hash = "f" * 64
    broken = audit.verify_entries(session, [first, second])
    assert (broken.ok, broken.first_bad_id) == (False, second.id)
