"""Media storage: private objects behind signed links, public objects for finished games.

Two backends share one interface: the local filesystem (development and tests) and
Supabase Storage (production).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from reel2play.net import make_client, raise_for_status, with_retries
from reel2play.settings import Settings, StorageBackend

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.\-]{0,299}$")


class InvalidKeyError(ValueError):
    pass


def check_key(key: str) -> str:
    """Object keys are plain relative paths: no traversal, no odd characters."""
    if not _KEY_PATTERN.match(key) or ".." in key or "//" in key:
        raise InvalidKeyError(f"invalid media key: {key!r}")
    return key


class MediaStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str, *, public: bool = False) -> None: ...

    def get(self, key: str, *, public: bool = False) -> bytes: ...

    def exists(self, key: str, *, public: bool = False) -> bool: ...

    def delete(self, key: str, *, public: bool = False) -> None: ...

    def signed_url(self, key: str, ttl_seconds: int | None = None) -> str: ...

    def public_url(self, key: str) -> str: ...


def data_url(storage: MediaStorage, key: str, content_type: str) -> str:
    """Inline an object as a data URL, for models that cannot reach our storage."""
    encoded = base64.b64encode(storage.get(key)).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


# --- signed links for the local backend -------------------------------------------------


def sign(secret: str, key: str, expires_at: int) -> str:
    message = f"{key}:{expires_at}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str, key: str, expires_at: int, signature: str, now: float | None = None
) -> bool:
    if expires_at < int(now if now is not None else time.time()):
        return False
    return hmac.compare_digest(sign(secret, key, expires_at), signature)


class LocalStorage:
    """Files on disk; links point at this API's /media (signed) and /public routes."""

    def __init__(self, root: Path, api_base_url: str, secret: str, default_ttl: int) -> None:
        self._root = root
        self._api_base_url = api_base_url.rstrip("/")
        self._secret = secret
        self._default_ttl = default_ttl

    def path_for(self, key: str, *, public: bool = False) -> Path:
        return self._root / ("public" if public else "private") / check_key(key)

    def put(self, key: str, data: bytes, content_type: str, *, public: bool = False) -> None:
        path = self.path_for(key, public=public)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str, *, public: bool = False) -> bytes:
        return self.path_for(key, public=public).read_bytes()

    def exists(self, key: str, *, public: bool = False) -> bool:
        return self.path_for(key, public=public).is_file()

    def delete(self, key: str, *, public: bool = False) -> None:
        self.path_for(key, public=public).unlink(missing_ok=True)

    def signed_url(self, key: str, ttl_seconds: int | None = None) -> str:
        expires_at = int(time.time()) + (ttl_seconds or self._default_ttl)
        signature = sign(self._secret, check_key(key), expires_at)
        return f"{self._api_base_url}/media/{quote(key)}?exp={expires_at}&sig={signature}"

    def public_url(self, key: str) -> str:
        return f"{self._api_base_url}/public/{quote(check_key(key))}"


class SupabaseStorage:
    """Supabase Storage over its REST API, with one private and one public bucket."""

    service = "Supabase Storage"

    def __init__(
        self,
        base_url: str,
        service_key: str,
        private_bucket: str,
        public_bucket: str,
        default_ttl: int,
        client: httpx.Client | None = None,
    ) -> None:
        self._base = base_url.rstrip("/") + "/storage/v1"
        self._private = private_bucket
        self._public = public_bucket
        self._default_ttl = default_ttl
        self._client = client or make_client()
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def _bucket(self, public: bool) -> str:
        return self._public if public else self._private

    def _object_url(self, key: str, public: bool) -> str:
        return f"{self._base}/object/{self._bucket(public)}/{quote(check_key(key))}"

    def put(self, key: str, data: bytes, content_type: str, *, public: bool = False) -> None:
        headers = {
            **self._headers,
            "content-type": content_type,
            "x-upsert": "true",
            "cache-control": "max-age=3600",
        }

        def call() -> None:
            raise_for_status(
                self.service,
                self._client.post(self._object_url(key, public), content=data, headers=headers),
            )

        with_retries(call)

    def get(self, key: str, *, public: bool = False) -> bytes:
        def call() -> bytes:
            response = self._client.get(self._object_url(key, public), headers=self._headers)
            raise_for_status(self.service, response)
            return response.content

        return with_retries(call)

    def exists(self, key: str, *, public: bool = False) -> bool:
        response = self._client.head(self._object_url(key, public), headers=self._headers)
        return response.is_success

    def delete(self, key: str, *, public: bool = False) -> None:
        url = f"{self._base}/object/{self._bucket(public)}"
        response = self._client.request(
            "DELETE", url, headers=self._headers, json={"prefixes": [check_key(key)]}
        )
        raise_for_status(self.service, response)

    def signed_url(self, key: str, ttl_seconds: int | None = None) -> str:
        url = f"{self._base}/object/sign/{self._private}/{quote(check_key(key))}"

        def call() -> str:
            response = self._client.post(
                url, headers=self._headers, json={"expiresIn": ttl_seconds or self._default_ttl}
            )
            raise_for_status(self.service, response)
            return str(response.json()["signedURL"])

        return f"{self._base}{with_retries(call)}"

    def public_url(self, key: str) -> str:
        return f"{self._base}/object/public/{self._public}/{quote(check_key(key))}"


def build_storage(settings: Settings, client: httpx.Client | None = None) -> MediaStorage:
    if settings.storage_backend is StorageBackend.SUPABASE:
        return SupabaseStorage(
            settings.supabase_url,
            settings.supabase_service_key.get_secret_value(),
            settings.supabase_private_bucket,
            settings.supabase_public_bucket,
            settings.signed_url_ttl_seconds,
            client=client,
        )
    return LocalStorage(
        settings.local_media_dir,
        settings.api_base_url,
        settings.secret_key.get_secret_value(),
        settings.signed_url_ttl_seconds,
    )
