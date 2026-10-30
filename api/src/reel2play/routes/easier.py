"""The owner's side of the self-improving loop (feature 44): see why an easier version was
made, play it, and choose it or put it away."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from reel2play import audit
from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.insights import GameStats, stats_for
from reel2play.models import Ad, AdStatus
from reel2play.pipeline.easier import (
    SuggestionError,
    dismiss_easier,
    latest_build_of,
    suggestion_for,
    too_hard,
    use_easier,
)
from reel2play.routes.studio import current_shop

router = APIRouter(prefix="/api/ads", tags=["easier versions"])


class EasierVersion(BaseModel):
    id: uuid.UUID
    status: str
    state: str | None
    change: str | None
    play_url: str | None


class EasierOut(BaseModel):
    """Whether players find the game hard, and the easier version if one was made."""

    hard: bool
    reason: str | None
    stats: dict[str, float | int | None]
    version: EasierVersion | None


def change_of(session: SessionDep, ad: Ad) -> str | None:
    """What the easier version changed, in the words the director's step wrote down."""
    designed = [e for e in audit.entries_for(session, "ad", ad.id) if e.action == "easier.designed"]
    return str(designed[-1].data["change"]) if designed else None


def easier_out(
    session: SessionDep, storage: StorageDep, settings: SettingsDep, base: Ad
) -> EasierOut:
    stats = stats_for(session, [base.id]).get(base.id, GameStats())
    reason = too_hard(stats, settings)
    found = suggestion_for(session, base)
    version = None
    if found is not None:
        build = latest_build_of(session, found)
        version = EasierVersion(
            id=found.id,
            status=found.status,
            state=found.suggestion,
            change=change_of(session, found),
            play_url=storage.signed_url(build.html_key)
            if build and found.status == AdStatus.READY
            else None,
        )
    return EasierOut(hard=reason is not None, reason=reason, stats=stats.as_json(), version=version)


def owned(session: SessionDep, ad_id: uuid.UUID, key: str | None) -> tuple[Ad, Ad]:
    """The live game and its easier version, if this browser is the shop's."""
    shop = current_shop(session, key)
    base = session.get(Ad, ad_id)
    if base is None or base.shop_id != shop.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ad not found")
    found = suggestion_for(session, base)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no easier version yet.")
    return base, found


@router.get("/{ad_id}/easier")
def get_easier(
    ad_id: uuid.UUID, session: SessionDep, storage: StorageDep, settings: SettingsDep
) -> EasierOut:
    base = session.get(Ad, ad_id)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ad not found")
    return easier_out(session, storage, settings, base)


@router.post("/{ad_id}/easier/use", status_code=status.HTTP_202_ACCEPTED)
def choose_easier(
    ad_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    x_shop_key: Annotated[str | None, Header()] = None,
) -> EasierOut:
    base, found = owned(session, ad_id, x_shop_key)
    try:
        use_easier(session, found)
    except SuggestionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    audit.record(
        session,
        actor="shop",
        action="easier.chosen",
        subject_type="ad",
        subject_id=base.id,
        data={"message": "The owner chose the easier version.", "easier": str(found.id)},
    )
    return easier_out(session, storage, settings, base)


@router.post("/{ad_id}/easier/dismiss")
def put_away(
    ad_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    x_shop_key: Annotated[str | None, Header()] = None,
) -> EasierOut:
    base, found = owned(session, ad_id, x_shop_key)
    try:
        dismiss_easier(found)
    except SuggestionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    audit.record(
        session,
        actor="shop",
        action="easier.dismissed",
        subject_type="ad",
        subject_id=base.id,
        data={"message": "The owner kept the live game as it is.", "easier": str(found.id)},
    )
    return easier_out(session, storage, settings, base)
