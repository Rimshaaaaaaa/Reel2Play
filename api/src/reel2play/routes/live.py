"""Live progress (feature 65): each agent's lines as they happen, as server-sent events.

The page opens one stream per ad. Every second the stream sends the new audit lines and
the ad's status; it ends when the ad is finished, or after a while (the page then falls
back to asking every few seconds).
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from reel2play.db import session_scope
from reel2play.deps import SessionDep
from reel2play.models import Ad, AuditEntry
from reel2play.pipeline.runner import TERMINAL

router = APIRouter(prefix="/api/ads", tags=["live"])
POLL_S = 1.0
MAX_STREAM_S = 600.0
HEARTBEAT_S = 15.0


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def progress_lines(ad_id: uuid.UUID, after: int) -> tuple[list[AuditEntry], str | None]:
    with session_scope() as session:
        ad = session.get(Ad, ad_id)
        rows = session.scalars(
            select(AuditEntry)
            .where(
                AuditEntry.subject_type == "ad",
                AuditEntry.subject_id == str(ad_id),
                AuditEntry.id > after,
            )
            .order_by(AuditEntry.id)
        ).all()
        session.expunge_all()
        return list(rows), ad.status if ad else None


def stream(
    ad_id: uuid.UUID,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[str]:
    started = last_beat = clock()
    after, last_status = 0, ""
    while True:
        rows, ad_status = progress_lines(ad_id, after)
        for row in rows:
            after = row.id
            if "message" in row.data:
                line = {
                    "at": row.created_at,
                    "actor": row.actor,
                    "action": row.action,
                    "message": row.data["message"],
                }
                yield sse("progress", line)
        if ad_status != last_status:
            last_status = ad_status or ""
            yield sse("status", {"status": ad_status})
        if ad_status is None or ad_status in TERMINAL or clock() - started > MAX_STREAM_S:
            yield sse("end", {"status": ad_status})
            return
        if clock() - last_beat > HEARTBEAT_S:
            last_beat = clock()
            yield ": keep-alive\n\n"
        sleep(POLL_S)


@router.get("/{ad_id}/stream")
def live(ad_id: uuid.UUID, session: SessionDep) -> StreamingResponse:
    if session.get(Ad, ad_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ad not found")
    return StreamingResponse(
        stream(ad_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
