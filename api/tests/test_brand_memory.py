"""Memory per brand (feature 53): the director sees what worked for this shop before."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play.brand_memory import BrandMemory, remember
from reel2play.jobs.queue import run_due
from reel2play.models import Ad, AdStatus, Event, Shop, Suggestion, Video
from tests.helpers import OWNER_FIELDS, ad_for, trail


def shop_with_games(session: Session) -> Shop:
    shop = Shop(name="Synthetic Bakes", language="en")
    session.add(shop)
    session.flush()
    video = Video(shop_id=shop.id)
    session.add(video)
    session.flush()

    def game(template: str, plays: int, finishes: int, taps: int, **fields: object) -> Ad:
        ad = Ad(
            shop_id=shop.id,
            video_id=video.id,
            template=template,
            status=fields.pop("status", AdStatus.PUBLISHED),
            **fields,
        )
        session.add(ad)
        session.flush()
        session.add_all(
            [Event(ad_id=ad.id, variant=ad.variant, kind="play") for _ in range(plays)]
            + [Event(ad_id=ad.id, variant=ad.variant, kind="finish", won=True, seconds=20)
               for _ in range(finishes)]
            + [Event(ad_id=ad.id, variant=ad.variant, kind="cta") for _ in range(taps)]
        )  # fmt: skip
        return ad

    game("catch", 40, 32, 8)  # 80% finish, 25% of finishers order: the best
    runner = game("runner", 30, 12, 1)  # players found it hard
    game("runner", 0, 0, 0, status=AdStatus.FAILED)  # never live: not counted
    group = uuid.uuid4()
    game("puzzle", 25, 20, 2, group_id=group, variant="A")
    game("memory", 25, 22, 5, group_id=group, variant="B")  # wins the A/B test
    game("stack", 5, 4, 1)  # too few plays to judge
    easier = game("runner", 0, 0, 0, status=AdStatus.READY)  # waiting: not counted
    easier.easier_for = runner.id
    easier.suggestion = Suggestion.READY
    session.commit()
    return shop


def test_the_shop_memory_ranks_what_worked(session: Session) -> None:
    shop = shop_with_games(session)
    memory = remember(session, shop)
    assert memory.best is not None
    assert memory.best.template == "catch"
    lines = memory.lines()
    assert lines[0] == (
        "catch: 1 game, 40 plays, 80% finished, 25% of finishers tapped order, the best so far"
    )
    runner = next(line for line in lines if line.startswith("runner"))
    assert runner == (
        "runner: 1 game, 30 plays, 40% finished, 8% of finishers tapped order, "
        "players found it hard (an easier version was made)"
    )
    assert any(line.startswith("memory:") and "won 1 A/B test" in line for line in lines)
    assert any(line.startswith("stack:") and "too few plays to judge" in line for line in lines)
    assert memory.for_director().startswith("- catch:")
    assert BrandMemory().for_director() == "none yet: this is the shop's first game."
    assert BrandMemory().best is None


def test_the_director_is_told_and_the_studio_shows_it(
    client: TestClient, session: Session, sample_media: dict[str, Path], stop_after_build: None
) -> None:
    video = sample_media["product_video"]
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **OWNER_FIELDS}
    first = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    ).json()
    run_due("test", max_jobs=10)
    ad = ad_for(session, uuid.UUID(first["id"]))
    assert "memory.used" not in trail(session, ad)  # the shop's first game
    session.execute(update(Ad).where(Ad.id == ad.id).values(status=AdStatus.PUBLISHED))
    session.add_all([Event(ad_id=ad.id, kind="play") for _ in range(30)])
    session.commit()

    second = client.post(
        "/api/uploads",
        data={**data, "shop_id": first["shop_id"]},
        files=[("files", (video.name, video.read_bytes()))],
        headers={"X-Shop-Key": first["shop_key"]},
    ).json()
    run_due("test", max_jobs=10)
    newer = ad_for(session, uuid.UUID(second["id"]))
    entries = [e for e in trail(session, newer) if e == "memory.used"]
    assert entries == ["memory.used"]
    studio = client.get("/api/shop", headers={"X-Shop-Key": first["shop_key"]}).json()
    assert studio["memory"] == [f"{ad.template}: 1 game, 30 plays, 0% finished, the best so far"]
    assert session.scalars(select(Ad).where(Ad.id == newer.id)).one().template
