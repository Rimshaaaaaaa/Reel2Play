"""Shared FastAPI dependencies."""

from __future__ import annotations

import hmac
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from reel2play.ai import AIClient, get_ai
from reel2play.db import get_session
from reel2play.media.storage import MediaStorage, build_storage
from reel2play.settings import Settings, get_settings


@lru_cache(maxsize=1)
def get_storage() -> MediaStorage:
    return build_storage(get_settings())


def require_cron_secret(
    x_cron_secret: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),  # noqa: B008 - FastAPI dependency
) -> None:
    expected = settings.cron_secret.get_secret_value()
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or wrong cron secret")


SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[MediaStorage, Depends(get_storage)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
AIDep = Annotated[AIClient, Depends(get_ai)]
CronGuard = Depends(require_cron_secret)
