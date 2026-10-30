"""The self-improving loop (feature 44): players finding a live game hard start an easier
version, which is tested, held for the owner, and published under the same link only when
the owner chooses it."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.builder.templates import Tier, load_templates
from reel2play.insights import GameStats
from reel2play.models import Ad, AdStatus, Event, Export, ExportKind, Suggestion
from reel2play.pipeline.easier import (
    EasierPlan,
    describe,
    easier_direction,
    easier_values,
    offer_easier,
    too_hard,
)
from reel2play.routes.game_page import PAGES
from reel2play.settings import get_settings
from tests.helpers import OWNER_FIELDS, ad_for, drain


def published_ad(client: TestClient, session: Session, video: Path) -> tuple[Ad, str]:
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **OWNER_FIELDS}
    body = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    ).json()
    drain()
    ad = ad_for(session, uuid.UUID(body["id"]))
    assert ad.status == AdStatus.PUBLISHED
    return ad, body["shop_key"]


def event(client: TestClient, ad: Ad, kind: str, **extra: object) -> None:
    body = json.dumps({"ad": str(ad.id), "event": kind, **extra})
    assert client.post("/api/events", content=body).status_code == 204


def test_hard_games_get_an_easier_version_the_owner_chooses(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    ad, key = published_ad(client, session, sample_media["product_video"])
    slug = ad.slug
    assert client.get(f"/api/ads/{ad.id}/easier").json() == {
        "hard": False,
        "reason": None,
        "stats": GameStats().as_json(),
        "version": None,
    }

    # Players find it hard: thirty plays, and the few who finish lose.
    for _ in range(get_settings().easier_after_plays):
        event(client, ad, "play")
    event(client, ad, "finish", seconds=24.0, won=False)
    event(client, ad, "finish", seconds=24.0, won=False)  # a second finish starts nothing new
    session.expire_all()
    [easier] = session.scalars(select(Ad).where(Ad.easier_for == ad.id)).all()
    assert easier.suggestion == Suggestion.MAKING
    assert easier.group_id != ad.group_id

    drain()
    session.expire_all()
    assert easier.status == AdStatus.READY
    assert easier.suggestion == Suggestion.READY
    assert easier.slug is None
    assert ad.status == AdStatus.PUBLISHED
    assert ad.slug == slug
    trail = [e.action for e in audit.entries_for(session, "ad", easier.id)]
    assert "easier.designed" in trail
    assert "test.passed" in trail
    assert trail[-1] == "easier.ready"
    assert "publish.page" not in trail  # held for the owner, not published
    designed = next(
        e for e in audit.entries_for(session, "ad", easier.id) if e.action == "easier.designed"
    )
    assert designed.data["by"] == "model"

    shown = client.get(f"/api/ads/{ad.id}/easier").json()
    assert shown["hard"] is True
    assert shown["reason"] == "only 7% of 30 plays reached the end"
    assert shown["version"]["state"] == "ready"
    assert "goal" in shown["version"]["change"]
    assert "sig=" in shown["version"]["play_url"]
    studio = client.get("/api/shop", headers={"X-Shop-Key": key}).json()
    assert [a["id"] for a in studio["ads"]] == [str(ad.id)]  # not shown until chosen

    # Only the shop may choose it.
    assert client.post(f"/api/ads/{ad.id}/easier/use").status_code == 401
    chosen = client.post(f"/api/ads/{ad.id}/easier/use", headers={"X-Shop-Key": key})
    assert chosen.status_code == 202
    assert chosen.json()["version"]["state"] == "using"
    again = client.post(f"/api/ads/{ad.id}/easier/use", headers={"X-Shop-Key": key})
    assert again.status_code == 409
    drain()
    session.expire_all()

    # The easier version took over the same link; the old one is kept as replaced.
    assert (easier.status, easier.suggestion, easier.slug) == (AdStatus.PUBLISHED, "used", slug)
    assert (ad.status, ad.slug) == (AdStatus.REPLACED, None)
    PAGES.clear()
    page = client.get(f"/g/{slug}")
    assert page.status_code == 200
    assert str(easier.id) in page.text
    assert f'<meta property="og:url" content="http://testserver/g/{slug}">' in page.text
    poster = session.scalars(
        select(Export).where(Export.ad_id == easier.id, Export.kind == ExportKind.POSTER)
    ).one()
    assert poster.details["qr"] == f"http://testserver/g/{slug}?from=qr"
    assert "easier.used" in [e.action for e in audit.entries_for(session, "ad", easier.id)]
    studio = client.get("/api/shop", headers={"X-Shop-Key": key}).json()
    assert {(a["id"], a["status"]) for a in studio["ads"]} == {
        (str(easier.id), "published"),
        (str(ad.id), "replaced"),
    }
    assert client.get(f"/api/ads/{easier.id}").json()["easier_for"] == str(ad.id)
    # A replaced game makes no more versions.
    assert offer_easier(session, ad.id, get_settings()) is None


def test_the_owner_can_keep_the_live_game(
    client: TestClient, session: Session, sample_media: dict[str, Path], stop_after_build: None
) -> None:
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **OWNER_FIELDS}
    video = sample_media["product_video"]
    body = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    ).json()
    drain()
    ad = ad_for(session, uuid.UUID(body["id"]))
    key = body["shop_key"]
    ad.status = AdStatus.PUBLISHED
    session.add_all([Event(ad_id=ad.id, kind="play") for _ in range(40)])
    session.add_all([Event(ad_id=ad.id, kind="finish", won=False, seconds=20) for _ in range(30)])
    session.commit()
    assert (
        client.post(f"/api/ads/{ad.id}/easier/dismiss", headers={"X-Shop-Key": key}).status_code
        == 404
    )
    easier = offer_easier(session, ad.id, get_settings())
    assert easier is not None
    session.commit()
    assert (
        client.post(f"/api/ads/{ad.id}/easier/use", headers={"X-Shop-Key": key}).status_code == 409
    )
    kept = client.post(f"/api/ads/{ad.id}/easier/dismiss", headers={"X-Shop-Key": key})
    assert kept.status_code == 200
    assert kept.json()["version"]["state"] == "dismissed"
    assert kept.json()["reason"] == "only 0% of 30 finished games were won"
    assert (
        client.post(f"/api/ads/{ad.id}/easier/dismiss", headers={"X-Shop-Key": key}).status_code
        == 409
    )
    other = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    ).json()
    assert (
        client.post(f"/api/ads/{ad.id}/easier/use", headers={"X-Shop-Key": other["shop_key"]})
    ).status_code == 404
    assert client.get(f"/api/ads/{uuid.uuid4()}/easier").status_code == 404
    # One easier version per game: a dismissed one is not made again.
    assert offer_easier(session, ad.id, get_settings()) is None


@pytest.mark.parametrize(
    ("stats", "reason"),
    [
        (GameStats(plays=29, finishes=1), None),
        (GameStats(plays=30, finishes=12, wins=8), "only 40% of 30 plays reached the end"),
        (GameStats(plays=30, finishes=20, wins=6), "only 30% of 20 finished games were won"),
        (GameStats(plays=30, finishes=20, wins=12), None),
    ],
)
def test_code_decides_when_a_game_is_too_hard(stats: GameStats, reason: str | None) -> None:
    assert too_hard(stats, get_settings()) == reason


def test_only_easier_values_inside_the_ranges_are_kept() -> None:
    catch = load_templates(get_settings().templates_dir)["catch"]
    before = catch.resolve(Tier.NORMAL)
    assert easier_direction(catch, "goal") == -1
    assert easier_direction(catch, "spawn_every") == 1
    plan = EasierPlan(
        difficulty=Tier.NORMAL,
        difficulty_overrides={"goal": 8, "fall_speed": 300, "spawn_every": 9, "nonsense": 1},
    )
    after = easier_values(catch, before, plan)
    assert after["goal"] == 8  # easier: kept
    assert after["fall_speed"] == before["fall_speed"]  # harder: ignored
    assert after["spawn_every"] == catch.params["spawn_every"].max  # clamped to the range
    assert "nonsense" not in after
    # When the model gives nothing easier, code steps every value halfway towards easy.
    stepped = easier_values(catch, before, EasierPlan(difficulty=Tier.HARD))
    assert stepped["goal"] == before["goal"] - 2
    assert stepped == easier_values(catch, before, None)
    assert describe(before, stepped).startswith("goal 10 to 8")
    # At the easy end of every range there is nothing left to change.
    floor = {
        name: (p.min if easier_direction(catch, name) < 0 else p.max)
        for name, p in catch.params.items()
    }
    assert easier_values(catch, floor, None) == floor
