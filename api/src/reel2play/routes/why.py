"""The why panel (feature 51): every decision and fix for one ad, in order, with the
audit trail's own check that none of it was changed afterwards, and what the ad cost."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from reel2play import audit
from reel2play.ai import cost
from reel2play.deps import SessionDep
from reel2play.models import Ad, Build, Fix
from reel2play.routes.studio import CostOut, cost_out

router = APIRouter(prefix="/api/ads", tags=["why"])
# Bulky evidence stays in the audit log; the panel shows the decision itself.
HIDDEN_DETAILS = frozenset({"message", "measured"})


class Decision(BaseModel):
    at: datetime
    actor: str
    action: str
    message: str
    details: dict[str, Any]


class FixOut(BaseModel):
    round: int
    failed_gates: list[str]
    change: str


class BuildOut(BaseModel):
    number: int
    template: str
    reason: str
    size_bytes: int


class WhyOut(BaseModel):
    trail_intact: bool
    entries_checked: int
    decisions: list[Decision]
    builds: list[BuildOut]
    fixes: list[FixOut]
    cost: CostOut
    cost_by_role: dict[str, float]


@router.get("/{ad_id}/why")
def why(ad_id: uuid.UUID, session: SessionDep) -> WhyOut:
    ad = session.get(Ad, ad_id)
    if ad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ad not found")
    entries = audit.entries_for(session, "ad", ad.id)
    check = audit.verify_entries(session, entries)
    builds = session.scalars(select(Build).where(Build.ad_id == ad.id).order_by(Build.number))
    fixes = session.scalars(select(Fix).where(Fix.ad_id == ad.id).order_by(Fix.round))
    return WhyOut(
        trail_intact=check.ok,
        entries_checked=check.checked,
        decisions=[
            Decision(
                at=e.created_at,
                actor=e.actor,
                action=e.action,
                message=str(e.data.get("message", "")),
                details={k: v for k, v in e.data.items() if k not in HIDDEN_DETAILS},
            )
            for e in entries
        ],
        builds=[
            BuildOut(
                number=b.number,
                template=b.template,
                reason=str(b.proposal.get("reason", "")),
                size_bytes=b.size_bytes,
            )
            for b in builds
        ],
        fixes=[FixOut(round=f.round, failed_gates=f.failed_gates, change=f.change) for f in fixes],
        cost=cost_out(cost.summarize(session, ad_id=ad.id)),
        cost_by_role={role: float(pkr) for role, pkr in cost.by_role(session, ad.id).items()},
    )
