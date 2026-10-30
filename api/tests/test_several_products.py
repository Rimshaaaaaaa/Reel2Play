"""Several products (feature 11): the director names the shop's other products, each is cut
out, and multi-item games show them; a catalog of photos gives one product per photo."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.analysis import CreativeBrief
from reel2play.cutout.cut import CutoutError, cut_product
from reel2play.deps import get_storage
from reel2play.jobs.queue import run_due
from reel2play.models import Analysis, Build, Sprite, Video
from reel2play.pipeline import cutout as cutout_step
from tests.helpers import ad_for

pytestmark = pytest.mark.usefixtures("stop_after_build")


def send(client: TestClient, paths: list[Path], **fields: str) -> uuid.UUID:
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true",
            "whatsapp_number": "923001234567", **fields}  # fmt: skip
    files = [("files", (p.name, p.read_bytes())) for p in paths]
    response = client.post("/api/uploads", data=data, files=files)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def run(session: Session, video_id: uuid.UUID, key: str | None = None) -> None:
    if key:
        session.execute(update(Video).where(Video.id == video_id).values(sample_key=key))
        session.commit()
    run_due("test", max_jobs=20)


def brief_for(session: Session, video_id: uuid.UUID) -> CreativeBrief:
    ad = ad_for(session, video_id)
    raw = session.scalars(select(Analysis.brief).where(Analysis.ad_id == ad.id)).one()
    return CreativeBrief.model_validate(raw)


def test_the_other_products_reach_the_game(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = send(client, [sample_media["product_video"]])
    run(session, video_id, "several")
    ad = ad_for(session, video_id)
    brief = brief_for(session, video_id)
    # The instruction-like name and the frame that does not exist are both left out.
    assert [p.name for p in brief.more_products] == ["Canvas sandal"]
    assert brief.more_products[0].key.endswith("/frames/candidate-1.jpg")
    flagged = [e for e in audit.entries_for(session, "ad", ad.id) if e.action == "guard.flagged"]
    assert flagged[0].data["field"] == "more_products"
    done = next(e for e in audit.entries_for(session, "ad", ad.id) if e.action == "analysis.done")
    assert done.data["message"].startswith("Found Canvas sneaker and 1 more (Canvas sandal)")

    sprites = session.scalars(
        select(Sprite).where(Sprite.ad_id == ad.id).order_by(Sprite.product_index)
    ).all()
    assert [s.product_index for s in sprites] == [0, 1]
    assert "and 1 more product(s): Canvas sandal" in next(
        e.data["message"]
        for e in audit.entries_for(session, "ad", ad.id)
        if e.action == "cutout.done"
    )

    build = session.scalars(select(Build).where(Build.ad_id == ad.id)).one()
    assert build.template == "catch"
    html = get_storage().get(build.html_key).decode()
    assert '"moreProducts":[{"image":"data:image/webp;base64,' in html
    assert '"name":"Canvas sandal"' in html

    out = client.get(f"/api/ads/{ad.id}").json()
    assert out["brief"]["more_products"] == ["Canvas sandal"]
    assert [s["product_index"] for s in out["sprites"]] == [0, 1]


def test_a_catalog_of_photos_gives_one_product_per_photo(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    photos = [sample_media["photo_jpg"], sample_media["photo_png"]]
    catalog = send(client, photos, catalog="true")
    views = send(client, photos)
    single = send(client, [sample_media["photo_jpg"]], catalog="true")
    for video_id in (catalog, views, single):
        run(session, video_id)
    assert session.get(Video, catalog).catalog is True  # type: ignore[union-attr]
    assert session.get(Video, views).catalog is False  # type: ignore[union-attr]
    assert session.get(Video, single).catalog is False  # type: ignore[union-attr]
    assert [p.name for p in brief_for(session, catalog).more_products] == ["Product 2"]
    assert brief_for(session, views).more_products == []


def test_a_product_that_will_not_cut_out_is_skipped(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def picky(frame: bytes, prompt: str, *args: object, **kwargs: object) -> object:
        if prompt == "sandal":
            raise CutoutError("nothing there")
        return cut_product(frame, prompt, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cutout_step, "cut_product", picky)
    video_id = send(client, [sample_media["product_video"]])
    run(session, video_id, "several")
    ad = ad_for(session, video_id)
    indexes = session.scalars(select(Sprite.product_index).where(Sprite.ad_id == ad.id)).all()
    assert list(indexes) == [0]
    assert ad.step == "build"
