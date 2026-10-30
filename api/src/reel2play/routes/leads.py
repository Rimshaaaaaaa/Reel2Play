"""The shop's side of opt-in lead capture over WhatsApp (feature 43).

The owner turns sign-ups on in the studio. Every live game of the shop then shows a small
"Get offers on WhatsApp" link on its end card; it opens a chat with Reel2Play's number with
"JOIN <code>" written, which the player must send themselves. The chat then asks, with two
buttons, whether the shop may send them offers; only a yes is kept, with the words agreed
to. STOP deletes it. The owner sees how many agreed and can download the list to message
them from their own WhatsApp.
"""

from __future__ import annotations

import csv
import io
import secrets
from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select

from reel2play import audit
from reel2play.builder.cta import ALPHABET
from reel2play.deps import SessionDep, SettingsDep
from reel2play.models import Lead, Shop, WhatsAppChat
from reel2play.routes.studio import current_shop
from reel2play.settings import Settings

router = APIRouter(prefix="/api/shop", tags=["leads"])
CODE_LENGTH = 6


class LeadsOut(BaseModel):
    available: bool  # the server has WhatsApp set up for sign-ups
    enabled: bool
    code: str | None
    join_link: str | None
    agreed: int


class LeadsIn(BaseModel):
    enabled: bool


def join_link(settings: Settings, code: str) -> str:
    return f"https://wa.me/{settings.whatsapp_business_number}?text={quote('JOIN ' + code)}"


def optin_link(settings: Settings, shop: Shop) -> str | None:
    """What a live game's end card links to, when this shop takes sign-ups."""
    if not (settings.leads_ready and shop.leads_enabled and shop.lead_code):
        return None
    return join_link(settings, shop.lead_code)


def leads_out(session: SessionDep, settings: Settings, shop: Shop) -> LeadsOut:
    agreed = session.scalar(select(func.count(Lead.id)).where(Lead.shop_id == shop.id)) or 0
    return LeadsOut(
        available=settings.leads_ready,
        enabled=shop.leads_enabled,
        code=shop.lead_code,
        join_link=optin_link(settings, shop),
        agreed=agreed,
    )


def new_code(session: SessionDep) -> str:
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        if session.scalar(select(Shop.id).where(Shop.lead_code == code)) is None:
            return code


@router.get("/leads")
def get_leads(
    session: SessionDep, settings: SettingsDep, x_shop_key: Annotated[str | None, Header()] = None
) -> LeadsOut:
    return leads_out(session, settings, current_shop(session, x_shop_key))


@router.post("/leads")
def set_leads(
    wanted: LeadsIn,
    session: SessionDep,
    settings: SettingsDep,
    x_shop_key: Annotated[str | None, Header()] = None,
) -> LeadsOut:
    shop = current_shop(session, x_shop_key)
    if wanted.enabled and not settings.leads_ready:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Sign-ups need WhatsApp to be set up on this server first."
        )
    shop.leads_enabled = wanted.enabled
    if wanted.enabled and not shop.lead_code:
        shop.lead_code = new_code(session)
    audit.record(
        session,
        actor="shop",
        action="leads.on" if wanted.enabled else "leads.off",
        subject_type="shop",
        subject_id=shop.id,
        data={
            "message": "Sign-ups for offers " + ("turned on." if wanted.enabled else "turned off.")
        },
    )
    return leads_out(session, settings, shop)


@router.get("/leads.csv")
def export_leads(
    session: SessionDep, x_shop_key: Annotated[str | None, Header()] = None
) -> Response:
    """The numbers that agreed, with when and to what; only for the shop's own offers."""
    shop = current_shop(session, x_shop_key)
    rows: list[tuple[str, datetime, str]] = [
        (wa_id, created_at, consent)
        for wa_id, created_at, consent in session.execute(
            select(WhatsAppChat.wa_id, Lead.created_at, Lead.consent_text)
            .join(WhatsAppChat, WhatsAppChat.id == Lead.chat_id)
            .where(Lead.shop_id == shop.id)
            .order_by(Lead.created_at)
        )
    ]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["whatsapp_number", "agreed_at", "agreed_to"])
    for wa_id, created_at, consent in rows:
        writer.writerow([f"+{wa_id}", created_at.isoformat(timespec="seconds"), consent])
    audit.record(
        session,
        actor="shop",
        action="leads.exported",
        subject_type="shop",
        subject_id=shop.id,
        data={"message": f"The owner downloaded {len(rows)} sign-ups.", "count": len(rows)},
    )
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="whatsapp-sign-ups.csv"',
            "Cache-Control": "no-store",
        },
    )
