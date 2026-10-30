"""Read the audit trail (feeds the why panel) and verify the hash chain."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from reel2play import audit
from reel2play.deps import SessionDep

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditOut(BaseModel):
    id: int
    created_at: datetime
    actor: str
    action: str
    data: dict[str, Any]
    entry_hash: str


class ChainOut(BaseModel):
    ok: bool
    checked: int
    first_bad_id: int | None


@router.get("/verify")
def verify(session: SessionDep) -> ChainOut:
    result = audit.verify_chain(session)
    return ChainOut(ok=result.ok, checked=result.checked, first_bad_id=result.first_bad_id)


@router.get("/{subject_type}/{subject_id}")
def trail(subject_type: str, subject_id: str, session: SessionDep) -> list[AuditOut]:
    return [
        AuditOut(
            id=e.id,
            created_at=e.created_at,
            actor=e.actor,
            action=e.action,
            data=e.data,
            entry_hash=e.entry_hash,
        )
        for e in audit.entries_for(session, subject_type, subject_id)
    ]
