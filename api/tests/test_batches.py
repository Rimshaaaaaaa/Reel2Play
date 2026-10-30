"""Batch mode (feature 46): several products in one upload become a set of tested games."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play.ai.messages import ChatRequest, ChatResponse
from reel2play.ai.providers import CallContext, MockProvider
from reel2play.models import Ad, Analysis, Batch, Video
from reel2play.settings import get_settings
from tests.helpers import drain

SHARED = {
    "shop_name": "Synthetic Bakes",
    "rights_confirmed": "true",
    "whatsapp_number": "923001234567",
    "offer": "10% off this week",
}


def files_of(*paths: Path) -> list[tuple[str, tuple[str, bytes]]]:
    return [("files", (path.name, path.read_bytes())) for path in paths]


def test_a_batch_becomes_one_tested_game_per_product(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    stop_after_build: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [
        {"name": "Rose cupcake", "price": "Rs 450"},
        {"name": "Chocolate tart", "price": "Rs 700", "offer": "Free delivery"},
        {},
    ]
    response = client.post(
        "/api/batches",
        data={**SHARED, "items": json.dumps(items)},
        files=files_of(
            sample_media["product_video"], sample_media["photo_jpg"], sample_media["photo_png"]
        ),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["shop_key"]
    assert len(body["items"]) == 3
    assert [i["name"] for i in body["items"]] == ["Rose cupcake", "Chocolate tart", None]
    assert [i["price"] for i in body["items"]] == ["Rs 450", "Rs 700", None]
    batch = session.get(Batch, uuid.UUID(body["id"]))
    assert batch is not None
    assert batch.items == 3
    videos = list(session.scalars(select(Video).where(Video.batch_id == batch.id)))
    assert {v.shop_id for v in videos} == {batch.shop_id}
    assert {v.source for v in videos} == {"batch"}
    assert sorted(v.owner_offer or "" for v in videos) == [
        "10% off this week",
        "10% off this week",
        "Free delivery",
    ]

    # Watch what the director is told while the set is built.
    told: list[str] = []
    original = MockProvider.chat

    def spy(self: MockProvider, request: ChatRequest, ctx: CallContext) -> ChatResponse:
        told.append(" ".join(m.text for m in request.messages))
        return original(self, request, ctx)

    monkeypatch.setattr(MockProvider, "chat", spy)
    drain()
    session.expire_all()
    out = client.get(f"/api/batches/{batch.id}").json()
    assert all(i["ad_id"] for i in out["items"])
    assert all(i["template"] for i in out["items"])
    # The owner's names win over what the director saw.
    ads = {a.video_id: a for a in session.scalars(select(Ad))}
    named = {
        str(a.video_id): session.scalars(select(Analysis.brief).where(Analysis.ad_id == a.id)).one()
        for a in ads.values()
    }
    first = next(v for v in videos if v.owner_product == "Rose cupcake")
    assert named[str(first.id)]["product"]["name"] == "Rose cupcake"
    assert out["items"][2]["name"]  # named by the director when the owner left it blank
    assert any("one of a set of 3 for the same shop" in text for text in told)
    assert any("Owner's name for the product: «Rose cupcake»" in text for text in told)

    studio = client.get("/api/shop", headers={"X-Shop-Key": body["shop_key"]}).json()
    assert len(studio["ads"]) == 3


def test_a_batch_is_checked_before_anything_is_kept(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video, photo = sample_media["product_video"], sample_media["photo_jpg"]
    one = client.post("/api/batches", data=SHARED, files=files_of(video))
    assert one.status_code == 422
    assert "2 to 12 products" in one.json()["detail"]
    bad = client.post(
        "/api/batches",
        data=SHARED,
        files=[*files_of(video), ("files", ("notes.txt", b"not a video"))],
    )
    assert bad.status_code == 422
    assert bad.json()["detail"].startswith("File 2:")
    mismatch = client.post(
        "/api/batches", data={**SHARED, "items": json.dumps([{}])}, files=files_of(video, photo)
    )
    assert mismatch.json()["detail"] == "Give one line of product details for each file."
    unreadable = client.post(
        "/api/batches", data={**SHARED, "items": "{"}, files=files_of(video, photo)
    )
    assert unreadable.json()["detail"] == "The product list could not be read."
    no_rights = client.post(
        "/api/batches",
        data={**SHARED, "rights_confirmed": "false"},
        files=files_of(video, photo),
    )
    assert "yours to use" in no_rights.json()["detail"]
    too_long = client.post(
        "/api/batches",
        data={**SHARED, "items": json.dumps([{"name": "x" * 61}, {}])},
        files=files_of(video, photo),
    )
    assert too_long.status_code == 422
    assert session.scalars(select(Video)).first() is None
    assert session.scalars(select(Batch)).first() is None
    assert client.get(f"/api/batches/{uuid.uuid4()}").status_code == 404
    many = files_of(*([photo] * (get_settings().max_batch_items + 1)))
    assert client.post("/api/batches", data=SHARED, files=many).status_code == 422


def test_a_shop_adds_a_batch_with_its_studio_key(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video, photo = sample_media["product_video"], sample_media["photo_jpg"]
    first = client.post("/api/batches", data=SHARED, files=files_of(video, photo)).json()
    shop_id = first["shop_id"]
    without = client.post(
        "/api/batches", data={**SHARED, "shop_id": shop_id}, files=files_of(video, photo)
    )
    assert without.status_code == 403
    again = client.post(
        "/api/batches",
        data={**SHARED, "shop_id": shop_id},
        files=files_of(video, photo),
        headers={"X-Shop-Key": first["shop_key"]},
    )
    assert again.status_code == 201
    assert again.json()["shop_id"] == shop_id
    assert again.json()["shop_key"] is None
