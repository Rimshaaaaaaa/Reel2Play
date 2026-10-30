"""Agency workspaces (feature 47): who may do what with which brands.

Like a shop's studio there are no accounts: each person keeps a key in their browser, and only
its SHA-256 is stored. Roles: the owner does everything and invites people; an editor adds
brands and makes games for them; a viewer sees the brands and their numbers.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play.models import AgencyMember, AgencyRole, Shop

KEY_BYTES = 24
RANK = {AgencyRole.VIEWER: 0, AgencyRole.EDITOR: 1, AgencyRole.OWNER: 2}


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    return "agency_" + secrets.token_urlsafe(KEY_BYTES)


def member_for_key(session: Session, key: str | None) -> AgencyMember | None:
    if not key:
        return None
    member = session.scalars(
        select(AgencyMember).where(AgencyMember.key_hash == key_hash(key))
    ).first()
    if member is None or not hmac.compare_digest(member.key_hash, key_hash(key)):
        return None
    return member


def allowed(member: AgencyMember, need: AgencyRole) -> bool:
    return RANK[AgencyRole(member.role)] >= RANK[need]


def brand_for(
    session: Session, member: AgencyMember, shop_id: uuid.UUID, need: AgencyRole
) -> Shop | None:
    """The brand, if it belongs to the member's agency and their role is enough."""
    shop = session.get(Shop, shop_id)
    if shop is None or shop.agency_id != member.agency_id or not allowed(member, need):
        return None
    return shop
