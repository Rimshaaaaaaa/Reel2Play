"""A/B tests (feature 19): versions B and C of a published ad are different games, each tested
and published; one link shares visitors between them; the studio sees which one leads."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.insights import MIN_PLAYS, GameStats, leader
from reel2play.models import Ad, AdStatus, Build, Event, Video
from reel2play.routes.game_page import PAGES
from tests.helpers import OWNER_FIELDS, ad_for, drain


def published_ad(client: TestClient, session: Session, video: Path) -> tuple[Ad, str]:
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **OWNER_FIELDS}
    response = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    drain()
    ad = ad_for(session, uuid.UUID(body["id"]))
    assert ad.status == AdStatus.PUBLISHED
    return ad, body["shop_key"]


def test_three_versions_are_three_different_games(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    ad, key = published_ad(client, session, sample_media["product_video"])
    before = client.get(f"/api/ads/{ad.id}/variants").json()
    assert [v["variant"] for v in before["versions"]] == ["A"]
    assert before["link"] is None
    assert before["verdict"] == "Make the other versions to start the test."

    assert client.post(f"/api/ads/{ad.id}/variants").status_code == 403
    assert (
        client.post(f"/api/ads/{ad.id}/variants", headers={"X-Shop-Key": "no"}).status_code == 403
    )
    made = client.post(f"/api/ads/{ad.id}/variants", headers={"X-Shop-Key": key})
    assert made.status_code == 201, made.text
    assert [v["variant"] for v in made.json()["versions"]] == ["A", "B", "C"]
    again = client.post(f"/api/ads/{ad.id}/variants", headers={"X-Shop-Key": key})
    assert [v["id"] for v in again.json()["versions"]] == [v["id"] for v in made.json()["versions"]]

    drain()
    session.expire_all()
    group = list(session.scalars(select(Ad).where(Ad.group_id == ad.group_id).order_by(Ad.variant)))
    assert [(a.variant, a.status) for a in group] == [
        ("A", AdStatus.PUBLISHED),
        ("B", AdStatus.PUBLISHED),
        ("C", AdStatus.PUBLISHED),
    ]
    assert len({a.template for a in group}) == 3
    builds = [
        session.scalars(select(Build).where(Build.ad_id == a.id).order_by(Build.number)).first()
        for a in group
    ]
    colours = {(b.proposal["primary_color"], b.proposal["accent_color"]) for b in builds if b}
    assert len(colours) == 3
    b_trail = [e.action for e in audit.entries_for(session, "ad", group[1].id)]
    assert b_trail[0] == "ad.created"
    assert "analyze.started" not in b_trail  # it starts from A's reading of the video
    assert "variant.changed" in b_trail

    test = client.get(f"/api/ads/{ad.id}/variants").json()
    assert test["link"].endswith(f"/v/{ad.ab_slug}")
    assert test["verdict"] == "Waiting for the first plays of every version."
    studio = client.get("/api/shop", headers={"X-Shop-Key": key}).json()
    assert sorted(a["variant"] for a in studio["ads"]) == ["A", "B", "C"]
    assert {a["group_id"] for a in studio["ads"]} == {str(ad.group_id)}

    # The one link serves one of the three pages at random, never cached.
    PAGES.clear()
    pages = set()
    for _ in range(12):
        page = client.get(f"/v/{ad.ab_slug}")
        assert page.status_code == 200
        assert page.headers["cache-control"] == "no-store"
        assert "sandbox allow-scripts" in page.headers["content-security-policy"]
        pages.add(page.text)
    assert 1 < len(pages) <= 3
    assert client.get("/v/AAAAAAA").status_code == 404
    assert client.get("/v/not a slug").status_code == 404

    # Plays come in, tagged with their version; the test says who is ahead.
    for version, taps in (("A", 2), ("B", 9), ("C", 3)):
        target = next(a for a in group if a.variant == version)
        session.add_all(
            [Event(ad_id=target.id, variant=version, kind="play") for _ in range(MIN_PLAYS)]
            + [Event(ad_id=target.id, variant=version, kind="finish", seconds=18.0, won=True)
               for _ in range(MIN_PLAYS)]
            + [Event(ad_id=target.id, variant=version, kind="cta") for _ in range(taps)]
        )  # fmt: skip
    session.commit()
    result = client.get(f"/api/ads/{group[1].id}/variants").json()
    assert result["leader"] == "B"
    assert result["verdict"] == "Version B gets the most order taps per finished game."


def test_only_a_published_first_version_can_be_split(
    client: TestClient, session: Session, sample_media: dict[str, Path], stop_after_build: None
) -> None:
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **OWNER_FIELDS}
    video = sample_media["product_video"]
    body = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    ).json()
    drain()
    ad = ad_for(session, uuid.UUID(body["id"]))
    response = client.post(f"/api/ads/{ad.id}/variants", headers={"X-Shop-Key": body["shop_key"]})
    assert (response.status_code, response.json()["detail"]) == (
        409,
        "Only a published game can get two more versions.",
    )
    assert client.get(f"/api/ads/{uuid.uuid4()}/variants").status_code == 404
    assert session.get(Video, ad.video_id) is not None


@pytest.mark.parametrize(
    ("stats", "best", "verdict"),
    [
        ({"A": GameStats(plays=30)}, None, "Make the other versions"),
        ({"A": GameStats(plays=30), "B": GameStats(plays=4)}, None, "B need more"),
        (
            {
                "A": GameStats(plays=30, finishes=20, cta_taps=4),
                "B": GameStats(plays=30, finishes=20, cta_taps=5),
            },
            None,
            "Too close to call",
        ),
        (
            {
                "A": GameStats(plays=30, finishes=27, cta_taps=4),
                "B": GameStats(plays=30, finishes=18, cta_taps=3),
            },
            "A",
            "finished by the most players",
        ),
    ],
)
def test_who_leads(stats: dict[str, GameStats], best: str | None, verdict: str) -> None:
    found, words = leader(stats)
    assert found == best
    assert verdict in words
