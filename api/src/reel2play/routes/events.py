"""Anonymous game events from hosted pages (feature 39).

The game sends them with ``navigator.sendBeacon`` as plain text (a simple request, so no
preflight from the sandboxed page). Only the ad, the variant, what happened, and for a
finish the seconds and whether it was won are kept, with where the play started (a link,
the counter poster or the shop's website): no IP address, cookie or device.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from reel2play.deps import SessionDep, SettingsDep
from reel2play.models import Ad, AdStatus, Event, EventKind, EventSource
from reel2play.pipeline.easier import offer_easier

router = APIRouter(prefix="/api", tags=["events"])
MAX_BODY_BYTES = 512


class EventIn(BaseModel):
    ad: uuid.UUID
    variant: Annotated[str, Field(pattern=r"^[A-Z]$")] = "A"
    event: EventKind
    seconds: float | None = Field(default=None, ge=0, le=60)
    won: bool | None = None
    # Features 36 and 37: the poster's QR code and website embeds mark their plays.
    source: EventSource = Field(default=EventSource.LINK, alias="from")


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
async def record_event(request: Request, session: SessionDep, settings: SettingsDep) -> Response:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "event too large")
    try:
        event = EventIn.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "not a game event") from exc
    published = session.scalar(
        select(Ad.id).where(Ad.id == event.ad, Ad.status == AdStatus.PUBLISHED)
    )
    if published is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no published game")
    finish = event.event == EventKind.FINISH
    session.add(
        Event(
            ad_id=event.ad,
            variant=event.variant,
            kind=event.event,
            seconds=round(event.seconds, 1) if finish and event.seconds is not None else None,
            won=event.won if finish else None,
            source=event.source,
        )
    )
    if finish:  # feature 44: players finding the game hard start an easier version
        session.flush()
        offer_easier(session, event.ad, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
