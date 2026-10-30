"""Agency workspace with several brands and roles (feature 47)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from reel2play.db import utcnow
from reel2play.models import AgencyInvite, Shop, Video


def start(client: TestClient) -> tuple[str, dict[str, object]]:
    response = client.post("/api/agencies", json={"name": "Synthetic Agency", "your_name": "Sara"})
    assert response.status_code == 201, response.text
    body = response.json()
    return body["key"], body["agency"]


def as_member(key: str) -> dict[str, str]:
    return {"X-Agency-Key": key}


def test_an_agency_adds_brands_invites_people_and_makes_games(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    owner, agency = start(client)
    assert owner.startswith("agency_")
    assert agency["you"]["role"] == "owner"  # type: ignore[index]
    stored = session.scalar(text("SELECT key_hash FROM agency_members"))
    assert stored != owner
    assert len(stored) == 64

    brands = client.post(
        "/api/agency/brands",
        json={"name": "Synthetic Bakes", "whatsapp_number": "923001234567"},
        headers=as_member(owner),
    ).json()["brands"]
    assert [b["name"] for b in brands] == ["Synthetic Bakes"]
    brand = brands[0]["id"]
    bad = client.post(
        "/api/agency/brands", json={"name": "X", "whatsapp_number": "12"}, headers=as_member(owner)
    )
    assert bad.status_code == 422

    # Invites: one editor, one viewer, each single use.
    invite = client.post(
        "/api/agency/invites", json={"role": "editor"}, headers=as_member(owner)
    ).json()
    editor = client.post(
        "/api/agency/join", json={"code": invite["code"], "your_name": "Bilal"}
    ).json()
    assert editor["agency"]["you"]["role"] == "editor"
    again = client.post("/api/agency/join", json={"code": invite["code"], "your_name": "Eve"})
    assert again.status_code == 404
    view_code = client.post(
        "/api/agency/invites", json={"role": "viewer"}, headers=as_member(owner)
    ).json()["code"]
    viewer = client.post("/api/agency/join", json={"code": view_code, "your_name": "Hina"}).json()[
        "key"
    ]

    # Only the owner invites; viewers cannot add brands or make games.
    assert (
        client.post("/api/agency/invites", json={}, headers=as_member(editor["key"])).status_code
        == 403
    )
    assert (
        client.post(
            "/api/agency/brands", json={"name": "Nope"}, headers=as_member(viewer)
        ).status_code
        == 403
    )
    video = sample_media["product_video"]
    form = {
        "shop_name": "Synthetic Bakes",
        "shop_id": brand,
        "rights_confirmed": "true",
        "whatsapp_number": "923001234567",
    }
    files = [("files", (video.name, video.read_bytes()))]
    refused = client.post("/api/uploads", data=form, files=files, headers=as_member(viewer))
    assert refused.status_code == 403
    made = client.post("/api/uploads", data=form, files=files, headers=as_member(editor["key"]))
    assert made.status_code == 201, made.text
    assert made.json()["shop_key"] is None  # the brand stays the agency's
    uploaded = session.scalars(select(Video)).one()
    assert str(uploaded.shop_id) == brand

    # Everyone sees every brand; the brand's studio opens with any member's key.
    seen = client.get("/api/agency", headers=as_member(viewer)).json()
    assert [m["name"] for m in seen["members"]] == ["Sara", "Bilal", "Hina"]
    assert seen["brands"][0]["name"] == "Synthetic Bakes"
    studio = client.get(f"/api/agency/brands/{brand}", headers=as_member(viewer))
    assert studio.status_code == 200
    assert studio.json()["name"] == "Synthetic Bakes"
    assert client.get("/api/agency").status_code == 401

    # The owner changes roles and removes people; a removed key stops working.
    members = {m["name"]: m["id"] for m in seen["members"]}
    promoted = client.post(
        f"/api/agency/members/{members['Hina']}", json={"role": "editor"}, headers=as_member(owner)
    ).json()
    assert {m["name"]: m["role"] for m in promoted["members"]}["Hina"] == "editor"
    lone_owner = client.post(
        f"/api/agency/members/{members['Sara']}", json={"role": "viewer"}, headers=as_member(owner)
    )
    assert lone_owner.status_code == 409
    client.post(f"/api/agency/members/{members['Bilal']}/remove", headers=as_member(owner))
    assert client.get("/api/agency", headers=as_member(editor["key"])).status_code == 401
    assert (
        client.post(f"/api/agency/members/{members['Sara']}/remove", headers=as_member(owner))
    ).status_code == 409


def test_brands_and_invites_stay_inside_their_agency(client: TestClient, session: Session) -> None:
    first, _ = start(client)
    second, _ = start(client)
    brand = client.post(
        "/api/agency/brands", json={"name": "Synthetic Shoes"}, headers=as_member(first)
    ).json()["brands"][0]["id"]
    assert client.get(f"/api/agency/brands/{brand}", headers=as_member(second)).status_code == 404
    other_member = client.get("/api/agency", headers=as_member(second)).json()["you"]["id"]
    assert (
        client.post(
            f"/api/agency/members/{other_member}", json={"role": "viewer"}, headers=as_member(first)
        ).status_code
        == 404
    )
    code = client.post("/api/agency/invites", json={}, headers=as_member(first)).json()["code"]
    session.execute(update(AgencyInvite).values(expires_at=utcnow() - timedelta(days=1)))
    session.commit()
    expired = client.post("/api/agency/join", json={"code": code, "your_name": "Late"})
    assert expired.status_code == 404
    assert session.get(Shop, brand) is not None
