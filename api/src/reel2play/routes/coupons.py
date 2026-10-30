"""Unique win codes and redemption (feature 40).

A hosted game page asks for a code when the player wins: one per visit, a few per phone per
ten minutes, a daily cap per game. The code is random and readable (``R2P-K7QD-M2XP``) and
goes into the WhatsApp order message, so the shop sees it in the chat and marks it used in
the studio. Nothing about the player is kept: no phone number, name, IP address or device.

A win on a phone cannot be proven (the game runs on the phone), so a code says "this phone
won the game", not more; the shop still decides what discount it gives.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from reel2play import audit
from reel2play.builder.cta import ALPHABET, coupon_code
from reel2play.db import utcnow
from reel2play.deps import SessionDep, SettingsDep
from reel2play.models import Ad, AdStatus, Build, Coupon, EventSource
from reel2play.ratelimit import RateLimiter, caller_key
from reel2play.routes.studio import current_shop

router = APIRouter(prefix="/api", tags=["coupons"])
MAX_BODY_BYTES = 256
WINDOW_S = 600
CODE = re.compile(r"^R2P-[A-Z0-9]{4}-[A-Z0-9]{4}$")
LIMITS: dict[int, RateLimiter] = {}


def limiter(per_visitor: int) -> RateLimiter:
    """One limiter per configured limit (tests change the setting)."""
    return LIMITS.setdefault(per_visitor, RateLimiter(per_visitor, WINDOW_S))


def new_code() -> str:
    """Random, readable, and with no 0/O or 1/I to mix up when read aloud."""
    pick = "".join(secrets.choice(ALPHABET) for _ in range(8))
    return f"R2P-{pick[:4]}-{pick[4:]}"


def tidy(code: str) -> str:
    """What the owner types, as a code: any case, spaces or missing dashes."""
    letters = re.sub(r"[^A-Z0-9]", "", code.upper())
    if letters.startswith("R2P"):
        letters = letters[3:]
    if len(letters) == 8:
        return f"R2P-{letters[:4]}-{letters[4:]}"
    if len(letters) == 4:
        return f"R2P-{letters}"
    return code.strip().upper()


class CouponIn(BaseModel):
    ad: uuid.UUID
    variant: Annotated[str, Field(pattern=r"^[A-Z]$")] = "A"
    source: EventSource = Field(default=EventSource.LINK, alias="from")


def anyone(body: dict[str, object], code: int = status.HTTP_200_OK) -> JSONResponse:
    """The game page is sandboxed (its origin is "null"), so the answer is open to any origin;
    it carries no cookies and nothing private."""
    return JSONResponse(
        body,
        status_code=code,
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
    )


@router.post("/coupons")
async def issue_coupon(request: Request, session: SessionDep, settings: SettingsDep) -> Response:
    if not settings.unique_coupons:
        return anyone({"detail": "Unique codes are off."}, status.HTTP_404_NOT_FOUND)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return anyone({"detail": "Too large."}, status.HTTP_413_CONTENT_TOO_LARGE)
    try:
        wanted = CouponIn.model_validate_json(body)
    except ValidationError:
        return anyone({"detail": "Not a coupon request."}, status.HTTP_400_BAD_REQUEST)
    ad = session.get(Ad, wanted.ad)
    if ad is None or ad.status != AdStatus.PUBLISHED:
        return anyone({"detail": "No published game."}, status.HTTP_404_NOT_FOUND)
    caller = request.client.host if request.client else "unknown"
    if not limiter(settings.coupons_per_visitor).allow(caller_key(caller, str(ad.id))):
        return anyone({"detail": "Too many codes from this phone."}, 429)
    since = utcnow() - timedelta(days=1)
    today = session.scalar(
        select(func.count(Coupon.id)).where(Coupon.ad_id == ad.id, Coupon.created_at >= since)
    )
    if (today or 0) >= settings.coupons_per_ad_per_day:
        return anyone({"detail": "This game has given all of today's codes."}, 429)
    for _ in range(5):
        coupon = Coupon(ad_id=ad.id, code=new_code(), variant=wanted.variant, source=wanted.source)
        try:
            with session.begin_nested():
                session.add(coupon)
        except IntegrityError:  # pragma: no cover - 32^8 codes; a clash is very unlikely
            continue
        return anyone({"code": coupon.code}, status.HTTP_201_CREATED)
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "try again")  # pragma: no cover


# --- the shop's side: redeem and count ---------------------------------------------------

Result = Literal["redeemed", "already_used", "shared_code", "not_found"]
MESSAGES: dict[str, str] = {
    "redeemed": "Done: {code} is marked as used. Give the customer the game's offer.",
    "already_used": "{code} was already used on {when}. Each code works once.",
    "shared_code": "{code} is the game's shared code, shown when a phone could not get its "
    "own. It can be used more than once, so check the WhatsApp chat it came from.",
    "not_found": "{code} is not a code from your games. Check the letters with the customer.",
}


class RedeemIn(BaseModel):
    code: str = Field(min_length=4, max_length=24)


class RedeemOut(BaseModel):
    result: Result
    code: str
    message: str
    product: str | None = None
    ad_id: uuid.UUID | None = None
    issued_at: datetime | None = None
    redeemed_at: datetime | None = None


def product_of(ad: Ad, session: SessionDep) -> str | None:
    config = session.scalars(
        select(Build.config).where(Build.ad_id == ad.id).order_by(Build.number.desc())
    ).first()
    return str(config["text"]["productName"]) if config else None


@router.post("/shop/coupons/redeem")
def redeem(
    wanted: RedeemIn,
    session: SessionDep,
    x_shop_key: Annotated[str | None, Header()] = None,
) -> RedeemOut:
    shop = current_shop(session, x_shop_key)
    code = tidy(wanted.code)
    found = session.execute(
        select(Coupon, Ad)
        .join(Ad, Ad.id == Coupon.ad_id)
        .where(Coupon.code == code, Ad.shop_id == shop.id)
        .with_for_update(of=Coupon)
    ).first()
    if found is None:
        ads = session.scalars(select(Ad).where(Ad.shop_id == shop.id))
        shared = next((ad for ad in ads if coupon_code(ad.id) == code), None)
        result: Result = "shared_code" if shared else "not_found"
        return RedeemOut(
            result=result,
            code=code,
            message=MESSAGES[result].format(code=code, when=""),
            ad_id=shared.id if shared else None,
            product=product_of(shared, session) if shared else None,
        )
    coupon, ad = found
    if coupon.redeemed_at is not None:
        when = coupon.redeemed_at.strftime("%d %b %Y")
        result = "already_used"
    else:
        coupon.redeemed_at = utcnow()
        when = ""
        result = "redeemed"
        audit.record(
            session,
            actor="shop",
            action="coupon.redeemed",
            subject_type="ad",
            subject_id=ad.id,
            data={"message": f"A win code was used at the shop ({code}).", "code": code},
        )
    return RedeemOut(
        result=result,
        code=code,
        message=MESSAGES[result].format(code=code, when=when),
        product=product_of(ad, session),
        ad_id=ad.id,
        issued_at=coupon.created_at,
        redeemed_at=coupon.redeemed_at,
    )


class CouponCount(BaseModel):
    ad_id: uuid.UUID
    issued: int
    redeemed: int


class RecentCoupon(BaseModel):
    code: str
    ad_id: uuid.UUID
    issued_at: datetime
    redeemed_at: datetime | None


class CouponsOut(BaseModel):
    issued: int
    redeemed: int
    by_ad: list[CouponCount]
    recent: list[RecentCoupon]


def coupon_counts(session: SessionDep, ad_ids: list[uuid.UUID]) -> dict[uuid.UUID, CouponCount]:
    if not ad_ids:
        return {}
    rows = session.execute(
        select(Coupon.ad_id, func.count(Coupon.id), func.count(Coupon.redeemed_at))
        .where(Coupon.ad_id.in_(ad_ids))
        .group_by(Coupon.ad_id)
    )
    return {
        ad_id: CouponCount(ad_id=ad_id, issued=issued, redeemed=redeemed)
        for ad_id, issued, redeemed in rows
    }


@router.get("/shop/coupons")
def coupons(session: SessionDep, x_shop_key: Annotated[str | None, Header()] = None) -> CouponsOut:
    shop = current_shop(session, x_shop_key)
    ids = list(session.scalars(select(Ad.id).where(Ad.shop_id == shop.id)))
    counts = coupon_counts(session, ids)
    recent = session.scalars(
        select(Coupon)
        .where(Coupon.ad_id.in_(ids))
        .order_by(Coupon.created_at.desc(), Coupon.id.desc())
        .limit(20)
    )
    return CouponsOut(
        issued=sum(c.issued for c in counts.values()),
        redeemed=sum(c.redeemed for c in counts.values()),
        by_ad=list(counts.values()),
        recent=[
            RecentCoupon(
                code=c.code, ad_id=c.ad_id, issued_at=c.created_at, redeemed_at=c.redeemed_at
            )
            for c in recent
        ],
    )
