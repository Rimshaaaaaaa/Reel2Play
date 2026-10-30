"""The chat with a shop owner (feature 2), one queued message at a time.

1. The owner sends a video or photo, with the price and offer in the caption. Before saying
   yes they may add a voice note about the offer (feature 10).
2. We ask, with two buttons, whether the video is theirs to use. Nothing starts without yes.
3. On yes we download it from WhatsApp and it goes through the same upload path as the web
   page; the order button in the game opens a chat with this same number.
4. When the ad finishes, notify.py sends the game link and the gameplay Reel here.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.intake.upload import (
    Brief,
    UploadLimits,
    UploadRejectedError,
    accept_upload,
    check_voice,
    classify,
)
from reel2play.jobs import registry
from reel2play.jobs.queue import PermanentJobError
from reel2play.models import ChatState, Lead, Shop, WhatsAppChat, WhatsAppMessage
from reel2play.net import ExternalServiceError
from reel2play.pipeline.runner import SERVICES
from reel2play.settings import get_settings
from reel2play.whatsapp import messages
from reel2play.whatsapp.client import CLIENTS, WhatsAppClient
from reel2play.whatsapp.webhook import MESSAGE_JOB

MEDIA_KINDS = ("video", "image")
_PRICE = re.compile(
    r"(?:rs\.?|pkr|₨)\s?\d(?:[\d,]*\d)?(?:\.\d+)?|\d(?:[\d,]*\d)?\s?(?:rs|pkr|rupees|روپے)(?!\w)",
    re.I,
)
_OFFER_WORDS = re.compile(r"%|\boff\b|\bsale\b|\bfree\b|\bdiscount\b|\bdeal\b|رعایت|سیل|آف", re.I)
DEFAULT_SHOP_NAME = "My shop"


def read_caption(caption: str | None) -> tuple[str | None, str | None]:
    """The owner's price exactly as typed, and their offer if the rest of the caption is one."""
    text = (caption or "").strip()
    match = _PRICE.search(text)
    price = match.group(0).strip() if match else None
    rest = (text[: match.start()] + text[match.end() :]) if match else text
    rest = re.sub(r"\s{2,}", " ", rest).strip(" ,.;:-\n")
    offer = rest[:200] if rest and _OFFER_WORDS.search(rest) else None
    return price, offer


def shop_for(session: Session, chat: WhatsAppChat, profile_name: str) -> Shop:
    """This chat's shop; a shop that already uses this number on the web keeps its brand kit."""
    if chat.shop_id is not None:
        shop = session.get(Shop, chat.shop_id)
        if shop is not None:
            return shop
    shop = session.scalars(
        select(Shop).where(Shop.whatsapp_number == chat.wa_id).order_by(Shop.created_at.desc())
    ).first()
    if shop is None:
        shop = Shop(
            name=(profile_name.strip() or DEFAULT_SHOP_NAME)[:120], whatsapp_number=chat.wa_id
        )
        session.add(shop)
        session.flush()
    chat.shop_id = shop.id
    return shop


def download_problem(exc: ExternalServiceError) -> str:
    return "it is larger than 16 MB" if exc.status == 413 else "WhatsApp did not send the file"


class Chat:
    """Replies in one chat; every message sent is recorded by its id, never its number."""

    def __init__(self, session: Session, chat: WhatsAppChat, client: WhatsAppClient) -> None:
        self.session = session
        self.chat = chat
        self.client = client

    def _sent(self, message_id: str, kind: str) -> None:
        self.session.add(
            WhatsAppMessage(id=message_id, chat_id=self.chat.id, direction="out", kind=kind)
        )

    def text(self, body: str) -> None:
        self._sent(self.client.send_text(self.chat.wa_id, body), "text")

    def buttons(self, body: str, buttons: list[tuple[str, str]]) -> None:
        self._sent(self.client.send_buttons(self.chat.wa_id, body, buttons), "interactive")

    def video(self, link: str, caption: str) -> None:
        self._sent(self.client.send_video(self.chat.wa_id, link, caption), "video")

    def note(self, action: str, message: str, **data: Any) -> None:
        audit.record(
            self.session,
            actor="whatsapp",
            action=action,
            subject_type="whatsapp_chat",
            subject_id=self.chat.id,
            data={"message": message, **data},
        )


def ask_consent(chat: Chat, payload: dict[str, Any]) -> None:
    if chat.chat.state == ChatState.WORKING:
        chat.text(messages.BUSY)
        return
    chat.chat.pending = {
        "media_id": payload["media_id"],
        "kind": payload["kind"],
        "caption": payload.get("caption"),
        "profile_name": payload.get("profile_name", ""),
    }
    chat.chat.state = ChatState.AWAITING_CONSENT
    chat.buttons(messages.CONSENT, [messages.YES, messages.NO])
    chat.note("whatsapp.media_received", "Media received; asked the owner to confirm rights.")


def add_voice(chat: Chat, payload: dict[str, Any]) -> None:
    """A voice note goes with the video waiting for its yes; on its own it has nothing to brief."""
    pending = chat.chat.pending
    if not pending or chat.chat.state != ChatState.AWAITING_CONSENT:
        chat.text(messages.VOICE_FIRST)
        return
    chat.chat.pending = {**pending, "voice_media_id": payload["media_id"]}
    chat.buttons(messages.VOICE_ADDED, [messages.YES, messages.NO])
    chat.note("whatsapp.voice_received", "Voice note received for the waiting video.")


def voice_for(chat: Chat, pending: dict[str, Any]) -> bytes | None:
    """The voice note's file, or None (with a note) when WhatsApp did not send it."""
    media_id = pending.get("voice_media_id")
    if not media_id:
        return None
    try:
        data = chat.client.download_media(str(media_id))
        check_voice(data)
    except (ExternalServiceError, UploadRejectedError) as exc:
        reason = str(exc) if isinstance(exc, UploadRejectedError) else download_problem(exc)
        chat.note("whatsapp.voice_skipped", f"The voice note was left out: {reason}")
        return None
    return data


def start_game(chat: Chat) -> None:
    pending = chat.chat.pending
    if not pending or chat.chat.state != ChatState.AWAITING_CONSENT:
        chat.text(messages.NOTHING_PENDING)
        return
    settings = get_settings()
    try:
        data = chat.client.download_media(str(pending["media_id"]))
        files = classify([data], UploadLimits(settings.max_upload_bytes, settings.max_photos))
    except (UploadRejectedError, ExternalServiceError) as exc:
        reason = str(exc) if isinstance(exc, UploadRejectedError) else download_problem(exc)
        chat.chat.pending, chat.chat.state = None, ChatState.IDLE
        chat.text(messages.REJECTED.format(reason=reason))
        chat.note("whatsapp.media_rejected", f"Could not use the media: {reason}")
        return
    shop = shop_for(chat.session, chat.chat, str(pending.get("profile_name", "")))
    price, offer = read_caption(pending.get("caption"))
    brief = Brief(
        shop_name=shop.name,
        shop_id=shop.id,
        whatsapp_number=chat.chat.wa_id,
        price=price,
        offer=offer,
        rights_confirmed=True,
    )
    voice = voice_for(chat, pending)
    video = accept_upload(
        chat.session, SERVICES.storage(), brief, files, source="whatsapp", voice=voice
    )
    video.whatsapp_chat_id = chat.chat.id
    chat.chat.pending, chat.chat.state = None, ChatState.WORKING
    chat.text(messages.STARTED)
    chat.note(
        "whatsapp.upload_started",
        "The owner confirmed the video is theirs; the game is being made.",
        video_id=str(video.id),
        price_given=price is not None,
        offer_given=offer is not None,
        voice_note=voice is not None,
    )


def decline(chat: Chat) -> None:
    chat.chat.pending, chat.chat.state = None, ChatState.IDLE
    chat.text(messages.DECLINED)
    chat.note("whatsapp.rights_declined", "The owner said the video is not theirs; nothing kept.")


# --- feature 43: a player asks for a shop's offers, with consent --------------------------


def ask_lead(chat: Chat, code: str) -> None:
    shop = chat.session.scalars(
        select(Shop).where(Shop.lead_code == code, Shop.leads_enabled.is_(True))
    ).first()
    if shop is None:
        chat.text(messages.LEAD_UNKNOWN)
        return
    chat.chat.pending = {"lead_shop": str(shop.id)}
    chat.chat.state = ChatState.AWAITING_LEAD
    chat.buttons(
        messages.LEAD_CONSENT.format(shop=shop.name), [messages.LEAD_YES, messages.LEAD_NO]
    )
    chat.note("lead.asked", "A player asked for a shop's offers; asked for consent.")


def save_lead(chat: Chat) -> None:
    pending = chat.chat.pending or {}
    shop = (
        chat.session.get(Shop, uuid.UUID(pending["lead_shop"])) if "lead_shop" in pending else None
    )
    chat.chat.pending, chat.chat.state = None, ChatState.IDLE
    if shop is None or not shop.leads_enabled:
        chat.text(messages.LEAD_UNKNOWN)
        return
    consent = messages.LEAD_CONSENT.format(shop=shop.name)
    exists = chat.session.scalars(
        select(Lead).where(Lead.shop_id == shop.id, Lead.chat_id == chat.chat.id)
    ).first()
    if exists is None:
        chat.session.add(Lead(shop_id=shop.id, chat_id=chat.chat.id, consent_text=consent))
    chat.text(messages.LEAD_DONE.format(shop=shop.name))
    chat.note("lead.consented", "A player agreed to get this shop's offers.", shop_id=str(shop.id))


def stop_leads(chat: Chat) -> None:
    """STOP: every sign-up of this number is deleted, and the chat too if it is a player's."""
    chat.session.execute(delete(Lead).where(Lead.chat_id == chat.chat.id))
    chat.text(messages.LEAD_STOPPED)
    chat.note("lead.stopped", "A player sent STOP; their sign-ups were deleted.")
    if chat.chat.shop_id is None:
        chat.session.flush()
        chat.session.delete(chat.chat)


@registry.register(MESSAGE_JOB)
def handle_message(session: Session, payload: dict[str, Any]) -> None:
    record = session.get(WhatsAppChat, uuid.UUID(payload["chat_id"]))
    if record is None:
        raise PermanentJobError("the chat is gone")
    chat = Chat(session, record, CLIENTS())
    kind, button = payload["kind"], payload.get("button_id")
    command = payload.get("command") or ""
    if command.startswith("join:"):
        ask_lead(chat, command.removeprefix("join:"))
    elif command == "stop":
        stop_leads(chat)
    elif button == messages.LEAD_YES[0]:
        save_lead(chat)
    elif button == messages.LEAD_NO[0]:
        chat.chat.pending, chat.chat.state = None, ChatState.IDLE
        chat.text(messages.LEAD_DECLINED)
    elif kind in MEDIA_KINDS and payload.get("media_id"):
        ask_consent(chat, payload)
    elif kind == "audio" and payload.get("media_id"):
        add_voice(chat, payload)
    elif button == messages.YES[0]:
        start_game(chat)
    elif button == messages.NO[0]:
        decline(chat)
    else:
        chat.text(messages.HELP)
