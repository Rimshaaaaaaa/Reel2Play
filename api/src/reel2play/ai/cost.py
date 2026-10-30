"""Cost meter (feature 48): tokens and rupees for every model call."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from reel2play.ai.config import EndpointConfig
from reel2play.ai.messages import Usage
from reel2play.db import session_scope
from reel2play.models import ModelCall

MILLION = Decimal(1_000_000)


def usd_cost(config: EndpointConfig | None, usage: Usage, latency_ms: int) -> Decimal:
    if config is None:
        return Decimal(0)
    tokens = (
        config.usd_per_m_input * usage.input_tokens + config.usd_per_m_output * usage.output_tokens
    ) / MILLION
    seconds = config.usd_per_second * Decimal(latency_ms) / Decimal(1000)
    return (tokens + seconds).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def to_pkr(usd: Decimal, rate: float) -> Decimal:
    return (usd * Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class CallRecord:
    role: str
    endpoint: str
    model: str
    prompt_name: str
    usage: Usage
    usd: Decimal
    pkr: Decimal
    latency_ms: int
    ok: bool
    error: str | None = None
    ad_id: uuid.UUID | None = None
    video_id: uuid.UUID | None = None


class Recorder(Protocol):
    def record(self, call: CallRecord) -> None: ...


@dataclass
class MemoryRecorder:
    calls: list[CallRecord] = field(default_factory=list)

    def record(self, call: CallRecord) -> None:
        self.calls.append(call)


class DbRecorder:
    """Writes each call in its own transaction, so failed calls are counted too."""

    def record(self, call: CallRecord) -> None:
        with session_scope() as session:
            session.add(
                ModelCall(
                    ad_id=call.ad_id,
                    video_id=call.video_id,
                    role=call.role,
                    endpoint=call.endpoint,
                    model=call.model,
                    prompt_name=call.prompt_name,
                    input_tokens=call.usage.input_tokens,
                    output_tokens=call.usage.output_tokens,
                    usd_cost=call.usd,
                    pkr_cost=call.pkr,
                    latency_ms=call.latency_ms,
                    ok=call.ok,
                    error=call.error,
                )
            )


@dataclass(frozen=True)
class CostSummary:
    calls: int
    input_tokens: int
    output_tokens: int
    usd: Decimal
    pkr: Decimal


def summarize(
    session: Session, *, ad_id: uuid.UUID | None = None, video_id: uuid.UUID | None = None
) -> CostSummary:
    stmt = select(
        func.count(ModelCall.id),
        func.coalesce(func.sum(ModelCall.input_tokens), 0),
        func.coalesce(func.sum(ModelCall.output_tokens), 0),
        func.coalesce(func.sum(ModelCall.usd_cost), 0),
        func.coalesce(func.sum(ModelCall.pkr_cost), 0),
    )
    if ad_id is not None:
        stmt = stmt.where(ModelCall.ad_id == ad_id)
    if video_id is not None:
        stmt = stmt.where(ModelCall.video_id == video_id)
    calls, tokens_in, tokens_out, usd, pkr = session.execute(stmt).one()
    return CostSummary(
        calls=int(calls),
        input_tokens=int(tokens_in),
        output_tokens=int(tokens_out),
        usd=Decimal(usd),
        pkr=Decimal(pkr),
    )


def by_role(session: Session, ad_id: uuid.UUID) -> dict[str, Decimal]:
    """Rupees spent on one ad, per agent role."""
    rows = session.execute(
        select(ModelCall.role, func.coalesce(func.sum(ModelCall.pkr_cost), 0))
        .where(ModelCall.ad_id == ad_id)
        .group_by(ModelCall.role)
        .order_by(ModelCall.role)
    )
    return {role: Decimal(pkr) for role, pkr in rows}


def by_ad(session: Session, ad_ids: list[uuid.UUID]) -> dict[uuid.UUID, CostSummary]:
    if not ad_ids:
        return {}
    rows = session.execute(
        select(
            ModelCall.ad_id,
            func.count(ModelCall.id),
            func.coalesce(func.sum(ModelCall.input_tokens), 0),
            func.coalesce(func.sum(ModelCall.output_tokens), 0),
            func.coalesce(func.sum(ModelCall.usd_cost), 0),
            func.coalesce(func.sum(ModelCall.pkr_cost), 0),
        )
        .where(ModelCall.ad_id.in_(ad_ids))
        .group_by(ModelCall.ad_id)
    )
    return {
        ad_id: CostSummary(int(calls), int(t_in), int(t_out), Decimal(usd), Decimal(pkr))
        for ad_id, calls, t_in, t_out, usd, pkr in rows
        if ad_id is not None
    }
