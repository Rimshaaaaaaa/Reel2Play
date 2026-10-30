"""The WhatsApp webhook: Meta's verification handshake, and incoming messages.

Every POST must carry Meta's ``X-Hub-Signature-256`` (HMAC-SHA256 of the raw body with the
app secret). Messages are recorded by id, so Meta's retries are handled once, and the work
is queued so the webhook answers at once.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play.db import session_scope, utcnow
from reel2play.deps import SettingsDep
from reel2play.jobs import enqueue
from reel2play.models import WhatsAppChat, WhatsAppMessage
from reel2play.settings import Settings

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])
MESSAGE_JOB = "whatsapp.message"


class Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class WaMedia(Lenient):
    id: str
    mime_type: str = ""
    caption: str | None = None


class WaButtonReply(Lenient):
    id: str


class WaInteractive(Lenient):
    type: str
    button_reply: WaButtonReply | None = None


class WaText(Lenient):
    body: str = ""


class WaMessage(Lenient):
    id: str
    sender: str = Field(alias="from")
    type: str
    text: WaText | None = None
    video: WaMedia | None = None
    image: WaMedia | None = None
    audio: WaMedia | None = None
    interactive: WaInteractive | None = None


class WaProfile(Lenient):
    name: str = ""


class WaContact(Lenient):
    wa_id: str
    profile: WaProfile | None = None


class WaValue(Lenient):
    metadata: dict[str, Any] = Field(default_factory=dict)
    contacts: list[WaContact] = Field(default_factory=list)
    messages: list[WaMessage] = Field(default_factory=list)


class WaChange(Lenient):
    field: str = ""
    value: WaValue


class WaEntry(Lenient):
    changes: list[WaChange] = Field(default_factory=list)


class WebhookPayload(Lenient):
    object: str = ""
    entry: list[WaEntry] = Field(default_factory=list)


def valid_signature(body: bytes, header: str, secret: str) -> bool:
    if not secret or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), expected)


_JOIN = re.compile(r"^\s*join\s+([A-Za-z0-9-]{4,16})\s*$", re.I)
_STOP = re.compile(r"^\s*(stop|unsubscribe|بند)\s*$", re.I)


def command_of(text: WaText | None) -> str | None:
    """Feature 43: only the two words a player may send, never the message itself."""
    body = text.body if text else ""
    if match := _JOIN.match(body):
        return f"join:{match.group(1).upper()}"
    if _STOP.match(body):
        return "stop"
    return None


def job_payload(chat: WhatsAppChat, message: WaMessage, profile_name: str) -> dict[str, Any]:
    """Only what the conversation needs: the kind, the media id and caption, the button, and
    a JOIN or STOP command (feature 43); other text is never kept."""
    media = message.video or message.image or message.audio
    reply = message.interactive.button_reply if message.interactive else None
    return {
        "command": command_of(message.text),
        "chat_id": str(chat.id),
        "kind": message.type,
        "media_id": media.id if media else None,
        "mime_type": media.mime_type if media else None,
        "caption": media.caption if media else None,
        "button_id": reply.id if reply else None,
        "profile_name": profile_name,
    }


def chat_for(session: Session, wa_id: str) -> WhatsAppChat:
    chat = session.scalars(select(WhatsAppChat).where(WhatsAppChat.wa_id == wa_id)).first()
    if chat is None:
        chat = WhatsAppChat(wa_id=wa_id)
        session.add(chat)
        session.flush()
    return chat


def accept(session: Session, payload: WebhookPayload, phone_number_id: str) -> int:
    """Record new messages for our number and queue each one; returns how many were queued."""
    queued = 0
    for change in (c for e in payload.entry for c in e.changes if c.field == "messages"):
        value = change.value
        if value.metadata.get("phone_number_id") != phone_number_id:
            continue
        names = {c.wa_id: c.profile.name for c in value.contacts if c.profile}
        for message in value.messages:
            if session.get(WhatsAppMessage, message.id) is not None:
                continue  # Meta retried a message we already have
            chat = chat_for(session, message.sender)
            chat.last_inbound_at = utcnow()
            session.add(
                WhatsAppMessage(id=message.id, chat_id=chat.id, direction="in", kind=message.type)
            )
            enqueue(session, MESSAGE_JOB, job_payload(chat, message, names.get(message.sender, "")))
            queued += 1
    return queued


def _receive(body: bytes, settings: Settings) -> int:
    payload = WebhookPayload.model_validate_json(body)
    with session_scope() as session:
        return accept(session, payload, settings.whatsapp_phone_number_id)


@router.get("", response_class=PlainTextResponse)
def verify(
    settings: SettingsDep,
    mode: Annotated[str, Query(alias="hub.mode")] = "",
    token: Annotated[str, Query(alias="hub.verify_token")] = "",
    challenge: Annotated[str, Query(alias="hub.challenge")] = "",
) -> str:
    expected = settings.whatsapp_verify_token.get_secret_value()
    if not expected or mode != "subscribe" or not hmac.compare_digest(token, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "verification failed")
    return challenge


@router.post("")
async def receive(request: Request, settings: SettingsDep) -> dict[str, int]:
    if not settings.whatsapp_ready:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "WhatsApp is not set up")
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not valid_signature(body, signature, settings.whatsapp_app_secret.get_secret_value()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad signature")
    try:
        queued = await run_in_threadpool(_receive, body, settings)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "not a WhatsApp webhook") from exc
    return {"queued": queued}
