"""Serve local media: private files only with a valid signature, public files openly.

Only used with the local storage backend; Supabase serves its own signed and public links.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from reel2play.deps import SettingsDep, StorageDep
from reel2play.media.storage import InvalidKeyError, LocalStorage, verify_signature

router = APIRouter(tags=["media"])

GAME_CSP = (
    "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox; "
    "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; media-src data:"
)


def _local(storage: object) -> LocalStorage:
    if not isinstance(storage, LocalStorage):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not served here")
    return storage


def _file(storage: LocalStorage, key: str, *, public: bool) -> FileResponse:
    try:
        path = storage.path_for(key, public=public)
    except InvalidKeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found") from exc
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = {"X-Content-Type-Options": "nosniff"}
    if media_type == "text/html":
        # Game pages run sandboxed: their own inline code only, no network, no API origin.
        headers["Content-Security-Policy"] = GAME_CSP
    return FileResponse(path, media_type=media_type, headers=headers)


@router.get("/media/{key:path}")
def private_media(
    key: str, exp: int, sig: str, storage: StorageDep, settings: SettingsDep
) -> FileResponse:
    local = _local(storage)
    if not verify_signature(settings.secret_key.get_secret_value(), key, exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "link expired or invalid")
    return _file(local, key, public=False)


@router.get("/public/{key:path}")
def public_media(key: str, storage: StorageDep) -> FileResponse:
    return _file(_local(storage), key, public=True)
