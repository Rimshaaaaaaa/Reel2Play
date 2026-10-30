"""Import a Reel or video from the shop's own Instagram account or Facebook Page (feature 3).

Official Graph API only, through Facebook Login for Business: the owner signs in, picks one
of their own posts, confirms it is theirs, and the video goes through the normal upload path.
Instagram does not hand out the file of a Reel that uses music from its library; such posts
are shown, marked, and the owner is asked to upload the file instead.

Tokens stay in this process's memory for half an hour. They are never logged, stored in the
database, or put in a link.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from pydantic import BaseModel

from reel2play.net import ExternalServiceError, make_client, raise_for_status, with_retries
from reel2play.settings import Settings, get_settings

SERVICE = "Meta Graph API"
SCOPES = "pages_show_list,pages_read_engagement,instagram_basic"
SESSION_TTL_S = 30 * 60
STATE_TTL_S = 10 * 60
POSTS_PER_ACCOUNT = 12
IG_FIELDS = "id,caption,media_type,media_product_type,media_url,thumbnail_url,timestamp"
FB_FIELDS = "id,description,picture,created_time,source"
# Files are only fetched from Meta's own servers, whatever address the Graph API returns.
META_HOSTS = (".fbcdn.net", ".cdninstagram.com", ".facebook.com", ".instagram.com")
CHUNK = 256 * 1024
MAX_REDIRECTS = 3
NOT_META = "Facebook sent an address we do not download from."


class ImportPost(BaseModel):
    id: str  # "ig:<media id>" or "fb:<page id>:<video id>"
    source: str  # "instagram" or "facebook"
    account: str
    caption: str
    thumbnail_url: str | None
    created_at: str | None
    downloadable: bool


class PostNotImportableError(ValueError):
    """The post cannot be imported; the message is safe to show to the shop."""


NO_FILE = (
    "Instagram does not share this video's file, usually because it uses music from "
    "Instagram's library. Upload the video from your phone instead."
)


@dataclass
class ImportSession:
    user_token: str
    page_tokens: dict[str, str] = field(default_factory=dict)
    expires_at: float = 0.0


class SessionStore:
    """Short-lived sign-in states and sessions, in memory only."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._states: dict[str, float] = {}
        self._sessions: dict[str, ImportSession] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def _sweep(self) -> None:
        now = self._clock()
        self._states = {s: t for s, t in self._states.items() if t > now}
        self._sessions = {k: v for k, v in self._sessions.items() if v.expires_at > now}

    def new_state(self) -> str:
        state = secrets.token_urlsafe(24)
        with self._lock:
            self._sweep()
            self._states[state] = self._clock() + STATE_TTL_S
        return state

    def take_state(self, state: str) -> bool:
        """True once for a state this server handed out in the last ten minutes."""
        with self._lock:
            expires = self._states.pop(state, 0.0)
        return expires > self._clock()

    def open(self, user_token: str) -> str:
        sid = secrets.token_urlsafe(24)
        with self._lock:
            self._sweep()
            self._sessions[sid] = ImportSession(
                user_token, expires_at=self._clock() + SESSION_TTL_S
            )
        return sid

    def get(self, sid: str) -> ImportSession | None:
        with self._lock:
            found = self._sessions.get(sid)
            if found is not None and found.expires_at <= self._clock():
                del self._sessions[sid]
                return None
            return found

    def close(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)


SESSIONS = SessionStore()


def from_meta(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host.endswith(suffix) for suffix in META_HOSTS)


class MetaImporter:
    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        self._settings = settings
        self._graph = f"{settings.graph_base_url.rstrip('/')}/{settings.graph_api_version}"
        self._http = http or make_client()

    @property
    def redirect_uri(self) -> str:
        return f"{self._settings.api_base_url.rstrip('/')}/api/import/meta/callback"

    def login_url(self, state: str) -> str:
        asks = (
            {"config_id": self._settings.meta_login_config_id}
            if self._settings.meta_login_config_id
            else {"scope": SCOPES}
        )
        query = urlencode(
            {
                "client_id": self._settings.meta_app_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
                "response_type": "code",
                **asks,
            }
        )
        return f"https://www.facebook.com/{self._settings.graph_api_version}/dialog/oauth?{query}"

    def _get(self, path: str, token: str, **params: str | int) -> dict[str, Any]:
        def call() -> dict[str, Any]:
            response = self._http.get(
                f"{self._graph}/{path}", params={**params, "access_token": token}
            )
            raise_for_status(SERVICE, response)
            data: dict[str, Any] = response.json()
            return data

        return with_retries(call)

    def exchange(self, code: str) -> str:
        """Swap the sign-in code for the owner's access token."""

        def call() -> str:
            response = self._http.get(
                f"{self._graph}/oauth/access_token",
                params={
                    "client_id": self._settings.meta_app_id,
                    "client_secret": self._settings.meta_app_secret.get_secret_value(),
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                },
            )
            raise_for_status(SERVICE, response)
            return str(response.json()["access_token"])

        return with_retries(call)

    def posts(self, session: ImportSession) -> list[ImportPost]:
        """The latest videos on every Page the owner manages and its Instagram account."""
        accounts = self._get(
            "me/accounts",
            session.user_token,
            fields="id,name,access_token,instagram_business_account{id,username}",
        )
        found: list[ImportPost] = []
        for page in accounts.get("data", []):
            token = str(page.get("access_token") or session.user_token)
            session.page_tokens[str(page["id"])] = token
            found += self._page_videos(page, token)
            instagram = page.get("instagram_business_account")
            if instagram:
                found += self._instagram_videos(instagram, session.user_token)
        return sorted(found, key=lambda p: p.created_at or "", reverse=True)

    def _page_videos(self, page: dict[str, Any], token: str) -> list[ImportPost]:
        videos = self._get(f"{page['id']}/videos", token, fields=FB_FIELDS, limit=POSTS_PER_ACCOUNT)
        return [
            ImportPost(
                id=f"fb:{page['id']}:{video['id']}",
                source="facebook",
                account=str(page.get("name") or "Facebook Page"),
                caption=str(video.get("description") or ""),
                thumbnail_url=video.get("picture"),
                created_at=video.get("created_time"),
                downloadable=bool(video.get("source")),
            )
            for video in videos.get("data", [])
        ]

    def _instagram_videos(self, account: dict[str, Any], token: str) -> list[ImportPost]:
        media = self._get(
            f"{account['id']}/media", token, fields=IG_FIELDS, limit=POSTS_PER_ACCOUNT
        )
        return [
            ImportPost(
                id=f"ig:{item['id']}",
                source="instagram",
                account=f"@{account.get('username') or 'instagram'}",
                caption=str(item.get("caption") or ""),
                thumbnail_url=item.get("thumbnail_url"),
                created_at=item.get("timestamp"),
                downloadable=bool(item.get("media_url")),
            )
            for item in media.get("data", [])
            if item.get("media_type") == "VIDEO"
        ]

    def file_url(self, session: ImportSession, post_id: str) -> str:
        """A fresh download address for one of the owner's posts (these addresses expire)."""
        kind, _, rest = post_id.partition(":")
        if kind == "ig" and rest.isdigit():
            url = self._get(rest, session.user_token, fields="media_url").get("media_url")
        elif kind == "fb" and rest.partition(":")[0] in session.page_tokens:
            page_id, _, video_id = rest.partition(":")
            if not video_id.isdigit():
                raise PostNotImportableError("That post is not one of yours.")
            url = self._get(video_id, session.page_tokens[page_id], fields="source").get("source")
        else:
            raise PostNotImportableError("That post is not one of yours.")
        if not url:
            raise PostNotImportableError(NO_FILE)
        if not from_meta(str(url)):
            raise PostNotImportableError(NOT_META)
        return str(url)

    def download(self, url: str, max_bytes: int) -> bytes:
        """The file from Meta's own servers, stopping as soon as it is too large.

        Redirects are followed by hand so that every address is checked before it is asked.
        """
        too_big = PostNotImportableError(
            f"The video is larger than {max_bytes // (1024 * 1024)} MB."
        )

        def call() -> bytes:
            address = url
            for _ in range(MAX_REDIRECTS + 1):
                if not from_meta(address):
                    raise PostNotImportableError(NOT_META)
                with self._http.stream("GET", address) as response:
                    if response.is_redirect:
                        address = str(response.url.join(response.headers["location"]))
                        continue
                    if not response.is_success:
                        response.read()
                        raise_for_status(SERVICE, response)
                    data = bytearray()
                    for chunk in response.iter_bytes(CHUNK):
                        data += chunk
                        if len(data) > max_bytes:
                            raise too_big
                    return bytes(data)
            raise PostNotImportableError("Facebook kept sending the file somewhere else.")

        return with_retries(call)


def importer_error(exc: ExternalServiceError) -> str:
    """What to tell the owner when the Graph API says no."""
    if exc.status in (400, 401, 403):
        return "Facebook did not allow that. Sign in again and allow access to your Pages."
    return "Facebook did not answer. Try again in a minute."


@dataclass
class ImporterFactory:
    """Builds the importer; tests swap ``build`` for one with a fake transport."""

    build: Callable[[Settings], MetaImporter] = field(default=lambda s: MetaImporter(s))

    def __call__(self) -> MetaImporter:
        return self.build(get_settings())


IMPORTERS = ImporterFactory()
