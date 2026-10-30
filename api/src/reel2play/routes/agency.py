"""Agency workspace with several brands and roles (feature 47).

An agency starts with its owner's key. The owner invites people with single-use codes that
carry a role; editors add brands and make games for them (uploads and batches accept the
``X-Agency-Key`` header with a brand's ``shop_id``); everyone sees every brand's games and
numbers. Personal data is limited to the name each person chooses to show their team.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select

from reel2play import audit
from reel2play.agency import allowed, brand_for, key_hash, member_for_key, new_key
from reel2play.db import utcnow
from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.insights import GameStats, stats_for
from reel2play.intake.upload import Brief
from reel2play.models import (
    Ad,
    AdStatus,
    Agency,
    AgencyInvite,
    AgencyMember,
    AgencyRole,
    Shop,
)
from reel2play.routes.studio import ShopOut, shop_out
from reel2play.routes.uploads import unprocessable

router = APIRouter(prefix="/api", tags=["agency"])
INVITE_DAYS = 7
NOT_A_MEMBER = "This browser is not linked to an agency."


class AgencyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    your_name: str = Field(min_length=1, max_length=80)


class JoinIn(BaseModel):
    code: str = Field(min_length=6, max_length=40)
    your_name: str = Field(min_length=1, max_length=80)


class InviteIn(BaseModel):
    role: AgencyRole = AgencyRole.EDITOR


class BrandIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    whatsapp_number: str | None = None
    shop_url: str | None = Field(default=None, max_length=500)
    language: str = Field(default="auto", pattern=r"^(auto|ur|en)$")


class RoleIn(BaseModel):
    role: AgencyRole


class MemberOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    you: bool


class BrandOut(BaseModel):
    id: uuid.UUID
    name: str
    games: int
    live: int
    plays: int
    cta_taps: int


class AgencyOut(BaseModel):
    id: uuid.UUID
    name: str
    you: MemberOut
    members: list[MemberOut]
    brands: list[BrandOut]


class KeyOut(BaseModel):
    """Given once: the browser keeps the key; only its hash is stored."""

    key: str
    agency: AgencyOut


class InviteOut(BaseModel):
    code: str
    role: str
    expires_at: datetime


def need_member(session: SessionDep, key: str | None) -> AgencyMember:
    member = member_for_key(session, key)
    if member is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_A_MEMBER)
    return member


def need_role(member: AgencyMember, role: AgencyRole) -> None:
    if not allowed(member, role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"This needs the {role.value} role.")


def agency_out(session: SessionDep, member: AgencyMember) -> AgencyOut:
    agency = session.get(Agency, member.agency_id)
    if agency is None:  # pragma: no cover - members are deleted with their agency
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agency not found")
    members = list(
        session.scalars(
            select(AgencyMember)
            .where(AgencyMember.agency_id == agency.id)
            .order_by(AgencyMember.created_at)
        )
    )
    shops = list(
        session.scalars(select(Shop).where(Shop.agency_id == agency.id).order_by(Shop.name))
    )
    ads = list(session.scalars(select(Ad).where(Ad.shop_id.in_([s.id for s in shops]))))
    stats = stats_for(session, [ad.id for ad in ads])
    brands = []
    for shop in shops:
        own = [ad for ad in ads if ad.shop_id == shop.id]
        numbers = [stats.get(ad.id, GameStats()) for ad in own]
        brands.append(
            BrandOut(
                id=shop.id,
                name=shop.name,
                games=len(own),
                live=sum(1 for ad in own if ad.status == AdStatus.PUBLISHED),
                plays=sum(n.plays for n in numbers),
                cta_taps=sum(n.cta_taps for n in numbers),
            )
        )

    def out(m: AgencyMember) -> MemberOut:
        return MemberOut(id=m.id, name=m.name, role=m.role, you=m.id == member.id)

    return AgencyOut(
        id=agency.id,
        name=agency.name,
        you=out(member),
        members=[out(m) for m in members],
        brands=brands,
    )


def note(session: SessionDep, member: AgencyMember, action: str, message: str) -> None:
    audit.record(
        session,
        actor="agency",
        action=action,
        subject_type="agency",
        subject_id=member.agency_id,
        data={"message": message, "member": str(member.id)},
    )


@router.post("/agencies", status_code=status.HTTP_201_CREATED)
def start_agency(wanted: AgencyIn, session: SessionDep) -> KeyOut:
    agency = Agency(name=wanted.name.strip())
    session.add(agency)
    session.flush()
    key = new_key()
    owner = AgencyMember(
        agency_id=agency.id,
        name=wanted.your_name.strip(),
        role=AgencyRole.OWNER,
        key_hash=key_hash(key),
    )
    session.add(owner)
    session.flush()
    note(session, owner, "agency.created", "The agency workspace was started.")
    return KeyOut(key=key, agency=agency_out(session, owner))


@router.get("/agency")
def my_agency(
    session: SessionDep, x_agency_key: Annotated[str | None, Header()] = None
) -> AgencyOut:
    return agency_out(session, need_member(session, x_agency_key))


@router.post("/agency/invites", status_code=status.HTTP_201_CREATED)
def invite(
    wanted: InviteIn, session: SessionDep, x_agency_key: Annotated[str | None, Header()] = None
) -> InviteOut:
    member = need_member(session, x_agency_key)
    need_role(member, AgencyRole.OWNER)
    code = secrets.token_urlsafe(9)
    expires = utcnow() + timedelta(days=INVITE_DAYS)
    session.add(
        AgencyInvite(
            agency_id=member.agency_id,
            role=wanted.role,
            code_hash=key_hash(code),
            expires_at=expires,
        )
    )
    note(session, member, "agency.invited", f"An invite for a new {wanted.role.value} was made.")
    return InviteOut(code=code, role=wanted.role, expires_at=expires)


@router.post("/agency/join", status_code=status.HTTP_201_CREATED)
def join(wanted: JoinIn, session: SessionDep) -> KeyOut:
    found = session.scalars(
        select(AgencyInvite).where(AgencyInvite.code_hash == key_hash(wanted.code.strip()))
    ).first()
    if found is None or found.used_at is not None or found.expires_at < utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invite is not valid any more.")
    found.used_at = utcnow()
    key = new_key()
    member = AgencyMember(
        agency_id=found.agency_id,
        name=wanted.your_name.strip(),
        role=found.role,
        key_hash=key_hash(key),
    )
    session.add(member)
    session.flush()
    note(session, member, "agency.joined", f"A new {found.role} joined.")
    return KeyOut(key=key, agency=agency_out(session, member))


@router.post("/agency/members/{member_id}")
def change_role(
    member_id: uuid.UUID,
    wanted: RoleIn,
    session: SessionDep,
    x_agency_key: Annotated[str | None, Header()] = None,
) -> AgencyOut:
    member = need_member(session, x_agency_key)
    need_role(member, AgencyRole.OWNER)
    other = session.get(AgencyMember, member_id)
    if other is None or other.agency_id != member.agency_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
    owners = session.scalar(
        select(func.count(AgencyMember.id)).where(
            AgencyMember.agency_id == member.agency_id, AgencyMember.role == AgencyRole.OWNER
        )
    )
    if other.role == AgencyRole.OWNER and wanted.role != AgencyRole.OWNER and owners == 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "An agency always keeps one owner.")
    other.role = wanted.role
    note(session, member, "agency.role", f"A member is now a {wanted.role.value}.")
    return agency_out(session, member)


@router.post("/agency/members/{member_id}/remove")
def remove_member(
    member_id: uuid.UUID, session: SessionDep, x_agency_key: Annotated[str | None, Header()] = None
) -> AgencyOut:
    member = need_member(session, x_agency_key)
    need_role(member, AgencyRole.OWNER)
    other = session.get(AgencyMember, member_id)
    if other is None or other.agency_id != member.agency_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
    if other.id == member.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "An owner cannot remove themselves.")
    session.delete(other)
    session.flush()
    note(session, member, "agency.removed", "A member was removed; their key no longer works.")
    return agency_out(session, member)


@router.post("/agency/brands", status_code=status.HTTP_201_CREATED)
def add_brand(
    wanted: BrandIn, session: SessionDep, x_agency_key: Annotated[str | None, Header()] = None
) -> AgencyOut:
    member = need_member(session, x_agency_key)
    need_role(member, AgencyRole.EDITOR)
    try:
        checked = Brief(  # the same checks as an upload's shop details
            shop_name=wanted.name,
            whatsapp_number=wanted.whatsapp_number,
            shop_url=wanted.shop_url,
            language=wanted.language,
        )
    except ValidationError as exc:
        raise unprocessable(exc) from exc
    session.add(
        Shop(
            name=checked.shop_name.strip(),
            language=checked.language,
            whatsapp_number=checked.whatsapp_number,
            shop_url=checked.shop_url,
            agency_id=member.agency_id,
        )
    )
    session.flush()
    note(session, member, "agency.brand", f"A brand was added: {wanted.name.strip()}.")
    return agency_out(session, member)


@router.get("/agency/brands/{shop_id}")
def brand_studio(
    shop_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    x_agency_key: Annotated[str | None, Header()] = None,
) -> ShopOut:
    member = need_member(session, x_agency_key)
    shop = brand_for(session, member, shop_id, AgencyRole.VIEWER)
    if shop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "brand not found")
    return shop_out(session, storage, settings, shop)
