"""Hash-chained audit log: every agent and person action, tamper-evident.

Each entry stores the hash of the previous entry, and its own hash covers its content plus
that previous hash. Changing or deleting any past entry breaks every hash after it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from reel2play.db import utcnow
from reel2play.models import AuditEntry

GENESIS_HASH = "0" * 64
# Arbitrary constant that identifies the audit-log advisory lock across processes.
_AUDIT_LOCK_KEY = 0x5232504C  # "R2PL"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_hash(
    *,
    prev_hash: str,
    created_at: datetime,
    actor: str,
    action: str,
    subject_type: str,
    subject_id: str,
    data: dict[str, Any],
) -> str:
    body = _canonical(
        {
            "prev": prev_hash,
            "at": created_at.astimezone(UTC).isoformat(),
            "actor": actor,
            "action": action,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "data": data,
        }
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def record(
    session: Session,
    *,
    actor: str,
    action: str,
    subject_type: str,
    subject_id: object,
    data: dict[str, Any] | None = None,
) -> AuditEntry:
    """Append one entry. Serialised with a transaction-scoped advisory lock."""
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _AUDIT_LOCK_KEY})
    last_hash = session.scalar(
        select(AuditEntry.entry_hash).order_by(AuditEntry.id.desc()).limit(1)
    )
    prev_hash = last_hash or GENESIS_HASH
    payload = json.loads(_canonical(data or {}))
    created_at = utcnow()
    entry = AuditEntry(
        created_at=created_at,
        actor=actor,
        action=action,
        subject_type=subject_type,
        subject_id=str(subject_id),
        data=payload,
        prev_hash=prev_hash,
        entry_hash=compute_hash(
            prev_hash=prev_hash,
            created_at=created_at,
            actor=actor,
            action=action,
            subject_type=subject_type,
            subject_id=str(subject_id),
            data=payload,
        ),
    )
    session.add(entry)
    session.flush()
    return entry


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    checked: int
    first_bad_id: int | None = None


def _hash_of(entry: AuditEntry) -> str:
    return compute_hash(
        prev_hash=entry.prev_hash,
        created_at=entry.created_at,
        actor=entry.actor,
        action=entry.action,
        subject_type=entry.subject_type,
        subject_id=entry.subject_id,
        data=entry.data,
    )


def verify_entries(session: Session, entries: list[AuditEntry]) -> ChainCheck:
    """Check some entries without walking the whole log: each one's hash matches its
    content, and the hash it links back to belongs to a real earlier entry."""
    for checked, entry in enumerate(entries):
        linked = entry.prev_hash == GENESIS_HASH or (
            session.scalar(
                select(AuditEntry.id).where(
                    AuditEntry.entry_hash == entry.prev_hash, AuditEntry.id < entry.id
                )
            )
            is not None
        )
        if entry.entry_hash != _hash_of(entry) or not linked:
            return ChainCheck(ok=False, checked=checked, first_bad_id=entry.id)
    return ChainCheck(ok=True, checked=len(entries))


def verify_chain(session: Session) -> ChainCheck:
    """Recompute every hash in order; report the first entry that does not match."""
    prev_hash = GENESIS_HASH
    checked = 0
    for entry in session.scalars(select(AuditEntry).order_by(AuditEntry.id)):
        expected = compute_hash(
            prev_hash=prev_hash,
            created_at=entry.created_at,
            actor=entry.actor,
            action=entry.action,
            subject_type=entry.subject_type,
            subject_id=entry.subject_id,
            data=entry.data,
        )
        if entry.prev_hash != prev_hash or entry.entry_hash != expected:
            return ChainCheck(ok=False, checked=checked, first_bad_id=entry.id)
        prev_hash = entry.entry_hash
        checked += 1
    return ChainCheck(ok=True, checked=checked)


def entries_for(session: Session, subject_type: str, subject_id: object) -> list[AuditEntry]:
    stmt = (
        select(AuditEntry)
        .where(AuditEntry.subject_type == subject_type, AuditEntry.subject_id == str(subject_id))
        .order_by(AuditEntry.id)
    )
    return list(session.scalars(stmt))
