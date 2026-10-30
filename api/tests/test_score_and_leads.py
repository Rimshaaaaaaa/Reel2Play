"""Score sharing without personal data (feature 42) and opt-in lead capture over WhatsApp,
with consent (feature 43)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.deps import get_storage
from reel2play.insights import stats_for
from reel2play.jobs.queue import run_due
from reel2play.models import (
    Ad,
    AdStatus,
    ChatState,
    Event,
    Export,
    ExportKind,
    Lead,
    Shop,
    WhatsAppChat,
)
from reel2play.routes.game_page import PAGES
from reel2play.settings import get_settings
from reel2play.whatsapp import messages
from reel2play.whatsapp.webhook import WaText, command_of
from tests.helpers import OWNER_FIELDS, ad_for
from tests.test_whatsapp import FakeGraph, graph, signed, webhook  # noqa: F401 (a fixture)

PLAYER = "923339998877"


@pytest.fixture
def published(
    client: TestClient, session: Session, sample_media: dict[str, Path], stop_after_build: None
) -> dict[str, str]:
    data = {"shop_name": "Synthetic Sweets", "rights_confirmed": "true", **OWNER_FIELDS}
    video = sample_media["product_video"]
    body = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    ).json()
    run_due("test", max_jobs=10)
    ad = ad_for(session, uuid.UUID(body["id"]))
    session.execute(
        update(Ad).where(Ad.id == ad.id).values(status=AdStatus.PUBLISHED, slug="AbC1234")
    )
    page_key = f"ads/{ad.id}/publish/game.html"
    get_storage().put(page_key, b"<html><head><title>Game</title></head><body></body></html>",
                      "text/html")  # fmt: skip
    session.add(Export(ad_id=ad.id, kind=ExportKind.HOSTED, key=page_key, content_type="text/html",
                       size_bytes=60, public=False))  # fmt: skip
    session.commit()
    return {"ad": str(ad.id), "key": body["shop_key"], "shop": body["shop_id"]}


# --- feature 42 -------------------------------------------------------------------------------


def test_challenges_and_the_plays_they_bring_are_counted_without_names(
    client: TestClient, session: Session, published: dict[str, str]
) -> None:
    ad = published["ad"]
    events: list[dict[str, Any]] = [
        {"ad": ad, "event": "share"},
        {"ad": ad, "event": "share", "name": "Ali", "phone": "923001234567"},
        {"ad": ad, "event": "play", "from": "share"},
        {"ad": ad, "event": "play"},
    ]
    for body in events:
        assert client.post("/api/events", content=json.dumps(body)).status_code == 204
    columns = set(Event.__table__.columns.keys())
    assert columns == {"id", "ad_id", "variant", "kind", "seconds", "won", "source", "created_at"}
    [stats] = stats_for(session, [uuid.UUID(ad)]).values()
    assert (stats.shares, stats.challenge_plays, stats.plays) == (2, 1, 2)


# --- feature 43 -------------------------------------------------------------------------------


@pytest.fixture
def leads_on(graph: FakeGraph, monkeypatch: pytest.MonkeyPatch) -> FakeGraph:  # noqa: F811
    monkeypatch.setattr(get_settings(), "whatsapp_business_number", "923001112223")
    return graph


def player_says(client: TestClient, message_id: str, **message: Any) -> None:
    body = webhook({"id": message_id, **message}).replace(
        b'"from": "923001112233"', f'"from": "{PLAYER}"'.encode()
    )
    response = client.post("/webhooks/whatsapp", content=body, headers=signed(body))
    assert response.status_code == 200, response.text
    run_due("test", max_jobs=5)


def test_only_join_and_stop_are_kept_from_a_players_text() -> None:
    assert command_of(WaText(body=" join k7qdm2 ")) == "join:K7QDM2"
    assert command_of(WaText(body="STOP")) == "stop"
    assert command_of(WaText(body="بند")) == "stop"
    assert command_of(WaText(body="hello, my name is Ali")) is None
    assert command_of(None) is None


def test_a_player_signs_up_with_consent_and_stop_deletes_it(
    client: TestClient, session: Session, published: dict[str, str], leads_on: FakeGraph
) -> None:
    key = {"X-Shop-Key": published["key"]}
    off = client.get("/api/shop/leads", headers=key).json()
    assert off == {
        "available": True,
        "enabled": False,
        "code": None,
        "join_link": None,
        "agreed": 0,
    }
    on = client.post("/api/shop/leads", json={"enabled": True}, headers=key).json()
    code = on["code"]
    assert len(code) == 6
    assert on["join_link"] == f"https://wa.me/923001112223?text=JOIN%20{code}"

    # Every live game now shows the link on its end card.
    PAGES.clear()
    page = client.get("/g/AbC1234").text
    assert 'name="r2p-optin"' in page
    assert f"JOIN%20{code}" in page

    player_says(client, "wamid.p.1", type="text", text={"body": f"JOIN {code}"})
    asked = leads_on.sent[-1]
    assert asked["type"] == "interactive"
    assert "Synthetic Sweets may send you offers" in asked["interactive"]["body"]["text"]
    chat = session.scalars(select(WhatsAppChat).where(WhatsAppChat.wa_id == PLAYER)).one()
    assert chat.state == ChatState.AWAITING_LEAD
    assert session.scalars(select(Lead)).first() is None  # nothing kept before a yes

    player_says(
        client,
        "wamid.p.2",
        type="interactive",
        interactive={"type": "button_reply", "button_reply": {"id": "lead_yes", "title": "Yes"}},
    )
    session.expire_all()
    lead = session.scalars(select(Lead)).one()
    assert "may send you offers" in lead.consent_text
    assert leads_on.texts[-1].startswith("Done: Synthetic Sweets may send you offers")
    assert client.get("/api/shop/leads", headers=key).json()["agreed"] == 1
    sheet = client.get("/api/shop/leads.csv", headers=key)
    assert sheet.headers["content-type"].startswith("text/csv")
    assert f"+{PLAYER}" in sheet.text
    assert client.get("/api/shop/leads.csv").status_code == 401
    # The number never goes into the audit trail.
    trail = [e.data for e in audit.entries_for(session, "whatsapp_chat", chat.id)]
    assert PLAYER not in json.dumps(trail)

    player_says(client, "wamid.p.3", type="text", text={"body": "STOP"})
    session.expire_all()
    assert session.scalars(select(Lead)).first() is None
    assert session.scalars(select(WhatsAppChat).where(WhatsAppChat.wa_id == PLAYER)).first() is None
    assert leads_on.texts[-1].startswith("Stopped:")

    # Turned off: the link leaves every game.
    client.post("/api/shop/leads", json={"enabled": False}, headers=key)
    PAGES.clear()
    assert 'name="r2p-optin"' not in client.get("/g/AbC1234").text


def test_unknown_codes_and_no_thanks_keep_nothing(
    client: TestClient, session: Session, published: dict[str, str], leads_on: FakeGraph
) -> None:
    player_says(client, "wamid.q.1", type="text", text={"body": "JOIN ZZZZZZ"})
    assert leads_on.texts[-1] == messages.LEAD_UNKNOWN
    key = {"X-Shop-Key": published["key"]}
    code = client.post("/api/shop/leads", json={"enabled": True}, headers=key).json()["code"]
    player_says(client, "wamid.q.2", type="text", text={"body": f"join {code}"})
    player_says(
        client,
        "wamid.q.3",
        type="interactive",
        interactive={"type": "button_reply", "button_reply": {"id": "lead_no", "title": "No"}},
    )
    assert leads_on.texts[-1] == messages.LEAD_DECLINED
    assert session.scalars(select(Lead)).first() is None
    # A yes after the shop turned sign-ups off keeps nothing either.
    player_says(client, "wamid.q.4", type="text", text={"body": f"join {code}"})
    client.post("/api/shop/leads", json={"enabled": False}, headers=key)
    player_says(
        client,
        "wamid.q.5",
        type="interactive",
        interactive={"type": "button_reply", "button_reply": {"id": "lead_yes", "title": "Yes"}},
    )
    assert leads_on.texts[-1] == messages.LEAD_UNKNOWN
    assert session.scalars(select(Lead)).first() is None


def test_sign_ups_need_whatsapp_on_the_server(
    client: TestClient, session: Session, published: dict[str, str]
) -> None:
    key = {"X-Shop-Key": published["key"]}
    assert client.get("/api/shop/leads", headers=key).json()["available"] is False
    refused = client.post("/api/shop/leads", json={"enabled": True}, headers=key)
    assert refused.status_code == 409
    shop = session.get(Shop, uuid.UUID(published["shop"]))
    assert shop is not None
    assert shop.leads_enabled is False
