"""Tell the shop in its WhatsApp chat how the ad ended: the link and the Reel, or why not.

Runs on every finished ad; ads that did not come from WhatsApp, or a server without
WhatsApp keys, are skipped.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play.jobs import registry
from reel2play.models import Ad, AdStatus, ChatState, Export, ExportKind, Video, WhatsAppChat
from reel2play.pipeline.runner import FINISHED_JOB, SERVICES
from reel2play.publish.hosted import page_link
from reel2play.settings import get_settings
from reel2play.whatsapp import messages
from reel2play.whatsapp.client import CLIENTS
from reel2play.whatsapp.conversation import Chat


def send_result(chat: Chat, ad: Ad) -> None:
    language = ad.language if ad.language in ("ur", "en") else "en"
    if ad.status == AdStatus.PUBLISHED and ad.slug:
        link = page_link(get_settings().share_base, ad.slug)
        chat.text(messages.DONE[language].format(link=link))
        reel = chat.session.scalars(
            select(Export).where(Export.ad_id == ad.id, Export.kind == ExportKind.REEL)
        ).first()
        if reel is not None:
            caption = str((ad.captions or {}).get("whatsapp_status", link))
            chat.video(SERVICES.storage().public_url(reel.key), caption)
    elif ad.status == AdStatus.NEEDS_PERSON:
        chat.text(messages.NEEDS_PERSON[language])
    elif ad.status == AdStatus.BLOCKED:
        chat.text(messages.BLOCKED[language])
    else:
        chat.text(messages.FAILED[language].format(reason=ad.error or "an unknown problem"))
    chat.chat.state = ChatState.IDLE
    chat.note("whatsapp.result_sent", f"Told the shop the ad is {ad.status}.", ad_id=str(ad.id))


def send_easier(chat: Chat, ad: Ad) -> None:
    """Feature 44: an easier version is tested and waiting; the owner decides in the studio."""
    language = ad.language if ad.language in ("ur", "en") else "en"
    link = f"{get_settings().web_base_url.rstrip('/')}/ads/{ad.easier_for}"
    chat.text(messages.EASIER[language].format(link=link))
    chat.note("whatsapp.easier_sent", "Told the shop an easier version is ready.", ad_id=str(ad.id))


@registry.register(FINISHED_JOB)
def ad_finished(session: Session, payload: dict[str, Any]) -> None:
    ad = session.get(Ad, uuid.UUID(payload["ad_id"]))
    # Only the first version answers the chat; A/B versions are the owner's own request.
    if ad is None or ad.variant != "A" or not get_settings().whatsapp_ready:
        return
    # An easier version (feature 44) only speaks when it is ready for the owner to choose.
    if ad.easier_for and ad.status != AdStatus.READY:
        return
    video = session.get(Video, ad.video_id)
    if video is None or video.whatsapp_chat_id is None:
        return
    record = session.get(WhatsAppChat, video.whatsapp_chat_id)
    if record is None:
        return
    if ad.status == AdStatus.READY:
        send_easier(Chat(session, record, CLIENTS()), ad)
    else:
        send_result(Chat(session, record, CLIENTS()), ad)
