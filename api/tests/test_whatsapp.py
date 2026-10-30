"""WhatsApp intake (feature 2) against a fake Graph API: the webhook's checks, the chat's
consent step, the upload, and the link and Reel coming back in the same chat."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from reel2play.jobs.queue import run_due
from reel2play.models import (
    Ad,
    AdStatus,
    ChatState,
    Shop,
    Video,
    WhatsAppChat,
    WhatsAppMessage,
)
from reel2play.net import ExternalServiceError
from reel2play.settings import get_settings
from reel2play.whatsapp import messages
from reel2play.whatsapp.client import CLIENTS, WhatsAppClient
from reel2play.whatsapp.conversation import read_caption
from reel2play.whatsapp.notify import send_result
from tests.helpers import drain

PHONE_ID = "1098765"
OWNER = "923001112233"
SECRET = "app-secret"
VERIFY = "verify-me"


@dataclass
class FakeGraph:
    """The Graph API endpoints the chat uses, recording what was sent."""

    media: bytes = b""
    media_size: int | None = None
    voice: bytes = b""
    sent: list[dict[str, Any]] = field(default_factory=list)
    downloads: int = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer wa-token"
        path = request.url.path
        if request.method == "POST" and path == f"/v26.0/{PHONE_ID}/messages":
            self.sent.append(json.loads(request.content))
            return httpx.Response(200, json={"messages": [{"id": f"wamid.out.{len(self.sent)}"}]})
        if path == "/v26.0/media-1":
            size = self.media_size if self.media_size is not None else len(self.media)
            return httpx.Response(
                200, json={"url": "https://lookaside.example/m/1", "file_size": size}
            )
        if path == "/v26.0/voice-1":
            return httpx.Response(
                200, json={"url": "https://lookaside.example/v/1", "file_size": len(self.voice)}
            )
        if request.url.host == "lookaside.example":
            self.downloads += 1
            voice = request.url.path.startswith("/v/")
            return httpx.Response(200, content=self.voice if voice else self.media)
        return httpx.Response(404, json={"error": "unknown"})

    @property
    def texts(self) -> list[str]:
        return [m["text"]["body"] for m in self.sent if m["type"] == "text"]


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> FakeGraph:
    settings = get_settings()
    for name, value in {
        "whatsapp_token": SecretStr("wa-token"),
        "whatsapp_app_secret": SecretStr(SECRET),
        "whatsapp_verify_token": SecretStr(VERIFY),
        "whatsapp_phone_number_id": PHONE_ID,
    }.items():
        monkeypatch.setattr(settings, name, value)
    fake = FakeGraph()
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr(
        CLIENTS, "build", lambda s: WhatsAppClient(s, httpx.Client(transport=transport))
    )
    return fake


def signed(body: bytes, secret: str = SECRET) -> dict[str, str]:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={digest}", "Content-Type": "application/json"}


def webhook(message: dict[str, Any], *, phone_id: str = PHONE_ID) -> bytes:
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550000000", "phone_number_id": phone_id},
        "contacts": [{"wa_id": OWNER, "profile": {"name": "Synthetic Shoes"}}],
        "messages": [{"from": OWNER, "timestamp": "1761600000", **message}],
    }
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "1", "changes": [{"field": "messages", "value": value}]}],
    }
    return json.dumps(payload).encode()


def video_message(message_id: str = "wamid.in.1", caption: str = "Rs 2,499, 20% off") -> bytes:
    return webhook(
        {
            "id": message_id,
            "type": "video",
            "video": {"id": "media-1", "mime_type": "video/mp4", "caption": caption},
        }
    )


def voice_message(message_id: str = "wamid.in.v") -> bytes:
    return webhook(
        {
            "id": message_id,
            "type": "audio",
            "audio": {"id": "voice-1", "mime_type": "audio/ogg; codecs=opus", "voice": True},
        }
    )


def button(answer: str, message_id: str = "wamid.in.2") -> bytes:
    return webhook(
        {
            "id": message_id,
            "type": "interactive",
            "interactive": {"type": "button_reply", "button_reply": {"id": answer, "title": "x"}},
        }
    )


def post(client: TestClient, body: bytes) -> dict[str, Any]:
    response = client.post("/webhooks/whatsapp", content=body, headers=signed(body))
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def chat_of(session: Session) -> WhatsAppChat:
    session.expire_all()
    return session.scalars(select(WhatsAppChat).where(WhatsAppChat.wa_id == OWNER)).one()


# --- the webhook ----------------------------------------------------------------------------


def test_verification_handshake(client: TestClient, graph: FakeGraph) -> None:
    query = {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1158201444"}
    response = client.get("/webhooks/whatsapp", params=query)
    assert (response.status_code, response.text) == (200, "1158201444")
    wrong = client.get("/webhooks/whatsapp", params={**query, "hub.verify_token": "nope"})
    assert wrong.status_code == 403


def test_webhook_needs_setup_and_a_valid_signature(
    client: TestClient, graph: FakeGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = video_message()
    unsigned = client.post("/webhooks/whatsapp", content=body)
    assert unsigned.status_code == 401
    forged = client.post("/webhooks/whatsapp", content=body, headers=signed(body, "other"))
    assert forged.status_code == 401
    garbage = b"not json"
    bad = client.post("/webhooks/whatsapp", content=garbage, headers=signed(garbage))
    assert bad.status_code == 400
    monkeypatch.setattr(get_settings(), "whatsapp_token", SecretStr(""))
    assert client.post("/webhooks/whatsapp", content=body, headers=signed(body)).status_code == 503
    query = {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1"}
    monkeypatch.setattr(get_settings(), "whatsapp_verify_token", SecretStr(""))
    assert client.get("/webhooks/whatsapp", params=query).status_code == 403


def test_each_message_is_handled_once(
    client: TestClient, session: Session, graph: FakeGraph
) -> None:
    assert post(client, video_message()) == {"queued": 1}
    assert post(client, video_message()) == {"queued": 0}  # Meta retried the same message
    assert post(client, webhook({"id": "x", "type": "text"}, phone_id="999")) == {"queued": 0}
    statuses_only = json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {"metadata": {"phone_number_id": PHONE_ID}, "statuses": [{}]},
                        }
                    ]
                }
            ],
        }
    ).encode()
    assert post(client, statuses_only) == {"queued": 0}
    assert session.scalar(text("SELECT count(*) FROM whatsapp_messages")) == 1


# --- the conversation -----------------------------------------------------------------------


def test_media_asks_for_consent_and_no_means_nothing_is_kept(
    client: TestClient, session: Session, graph: FakeGraph
) -> None:
    post(client, video_message())
    run_due("test")
    [ask] = graph.sent
    assert ask["to"] == OWNER
    assert ask["type"] == "interactive"
    replies = ask["interactive"]["action"]["buttons"]
    assert [b["reply"]["id"] for b in replies] == ["rights_yes", "rights_no"]
    assert all(len(b["reply"]["title"]) <= 20 for b in replies)
    chat = chat_of(session)
    assert chat.state == ChatState.AWAITING_CONSENT
    assert chat.pending is not None
    assert chat.pending["caption"] == "Rs 2,499, 20% off"

    post(client, button("rights_no"))
    run_due("test")
    assert graph.texts[-1] == messages.DECLINED
    chat = chat_of(session)
    assert (chat.state, chat.pending) == (ChatState.IDLE, None)
    assert graph.downloads == 0
    assert session.scalar(text("SELECT count(*) FROM videos")) == 0


def test_other_messages_get_help_or_a_nudge(
    client: TestClient, session: Session, graph: FakeGraph
) -> None:
    post(client, webhook({"id": "wamid.in.9", "type": "text", "text": {"body": "hi"}}))
    post(client, button("rights_yes", "wamid.in.10"))
    run_due("test")
    assert graph.texts == [messages.HELP, messages.NOTHING_PENDING]


def test_a_file_that_cannot_be_used_is_explained(
    client: TestClient, session: Session, graph: FakeGraph
) -> None:
    graph.media = b"%PDF-1.7 not a video"
    post(client, video_message())
    post(client, button("rights_yes"))
    run_due("test")
    assert graph.texts[-1].startswith("We could not use that file: Only MP4")
    graph.media_size = 20 * 1024 * 1024
    post(client, video_message("wamid.in.3"))
    post(client, button("rights_yes", "wamid.in.4"))
    run_due("test")
    assert graph.texts[-1] == "We could not use that file: it is larger than 16 MB"
    assert chat_of(session).state == ChatState.IDLE


def test_whatsapp_video_becomes_a_game_and_the_link_comes_back(
    client: TestClient, session: Session, graph: FakeGraph, sample_media: dict[str, Path]
) -> None:
    graph.media = sample_media["product_video"].read_bytes()
    post(client, video_message())
    post(client, button("rights_yes"))
    run_due("test", max_jobs=2)
    assert graph.texts == [messages.STARTED]
    assert graph.downloads == 1
    chat = chat_of(session)
    assert chat.state == ChatState.WORKING
    video = session.scalars(select(Video)).one()
    assert (video.source, video.whatsapp_chat_id, video.rights_confirmed) == (
        "whatsapp",
        chat.id,
        True,
    )
    assert (video.owner_price, video.owner_offer) == ("Rs 2,499", "20% off")
    assert (video.cta_kind, video.cta_target) == ("whatsapp", OWNER)
    shop = session.get(Shop, video.shop_id)
    assert shop is not None
    assert (shop.name, shop.whatsapp_number) == ("Synthetic Shoes", OWNER)

    post(client, video_message("wamid.in.5"))  # a second video while the first is working
    drain()
    ad = session.scalars(select(Ad)).one()
    assert ad.status == AdStatus.PUBLISHED
    assert messages.BUSY in graph.texts
    link = f"http://testserver/g/{ad.slug}"
    assert graph.texts[-1] == messages.DONE["en"].format(link=link)
    reel = graph.sent[-1]
    assert reel["type"] == "video"
    assert reel["video"]["link"].endswith("/publish/reel.mp4")
    assert reel["video"]["caption"].endswith(link)
    assert chat_of(session).state == ChatState.IDLE

    # The owner's number is only on the chat and the shop: never in jobs or the audit log.
    for query in ("SELECT payload FROM jobs", "SELECT data FROM audit_log"):
        rows = [row[0] for row in session.execute(text(query))]
        assert OWNER not in json.dumps(rows)
    out = session.scalars(select(WhatsAppMessage).where(WhatsAppMessage.direction == "out"))
    assert [m.kind for m in out][-2:] == ["text", "video"]


@pytest.mark.parametrize(
    ("status", "error", "language", "expected"),
    [
        (AdStatus.NEEDS_PERSON, None, "en", messages.NEEDS_PERSON["en"]),
        (
            AdStatus.FAILED,
            "the video is too dark",
            "ur",
            messages.FAILED["ur"].format(reason="the video is too dark"),
        ),
        (AdStatus.BLOCKED, None, None, messages.BLOCKED["en"]),
    ],
)
def test_unfinished_games_are_explained(
    session: Session,
    graph: FakeGraph,
    status: str,
    error: str | None,
    language: str | None,
    expected: str,
) -> None:
    from reel2play.whatsapp.conversation import Chat

    chat = WhatsAppChat(wa_id=OWNER, state=ChatState.WORKING)
    session.add(chat)
    session.flush()
    ad = Ad(status=status, error=error, language=language)
    send_result(Chat(session, chat, CLIENTS()), ad)
    assert graph.texts == [expected]
    assert chat.state == ChatState.IDLE


# --- small pieces ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("caption", "price", "offer"),
    [
        ("Rs 2,499, 20% off this week", "Rs 2,499", "20% off this week"),
        ("Red sneakers Rs. 1500", "Rs. 1500", None),
        ("1,999 rupees, Eid sale", "1,999 rupees", "Eid sale"),
        ("قیمت 2500 روپے", "2500 روپے", None),
        ("free delivery", None, "free delivery"),
        (None, None, None),
    ],
)
def test_price_and_offer_from_the_caption(
    caption: str | None, price: str | None, offer: str | None
) -> None:
    assert read_caption(caption) == (price, offer)


def test_client_refuses_media_over_16_mb(graph: FakeGraph) -> None:
    graph.media_size = 17 * 1024 * 1024
    with pytest.raises(ExternalServiceError, match="larger than 16 MB"):
        CLIENTS().download_media("media-1")
    assert graph.downloads == 0


# --- voice notes (feature 10) -----------------------------------------------------------------


def test_a_voice_note_goes_with_the_waiting_video(
    client: TestClient, session: Session, graph: FakeGraph, sample_media: dict[str, Path]
) -> None:
    graph.media = sample_media["product_video"].read_bytes()
    graph.voice = sample_media["video_with_audio"].read_bytes()  # any file with sound
    post(client, voice_message("wamid.in.early"))
    run_due("test", max_jobs=1)
    assert graph.texts == [messages.VOICE_FIRST]

    post(client, video_message())
    post(client, voice_message())
    run_due("test", max_jobs=2)
    assert graph.sent[-1]["interactive"]["body"]["text"] == messages.VOICE_ADDED
    post(client, button("rights_yes"))
    run_due("test", max_jobs=2)  # the yes, then the video's preparation
    video = session.scalars(select(Video)).one()
    session.refresh(video)
    assert video.voice_original_key is not None
    assert video.voice_key is not None  # prepared as speech for the director


def test_a_voice_note_whatsapp_does_not_send_is_left_out(
    client: TestClient, session: Session, graph: FakeGraph, sample_media: dict[str, Path]
) -> None:
    graph.media = sample_media["product_video"].read_bytes()
    graph.voice = b"not audio at all"
    post(client, video_message())
    post(client, voice_message())
    post(client, button("rights_yes"))
    run_due("test", max_jobs=3)
    video = session.scalars(select(Video)).one()
    assert video.voice_original_key is None
    notes = session.execute(
        text("SELECT data FROM audit_log WHERE action = 'whatsapp.voice_skipped'")
    )
    assert "voice note was left out" in str(notes.scalar_one())
