from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from reel2play.media.storage import (
    InvalidKeyError,
    LocalStorage,
    SupabaseStorage,
    build_storage,
    check_key,
    data_url,
    sign,
    verify_signature,
)
from reel2play.net import ExternalServiceError
from reel2play.settings import Settings, StorageBackend


@pytest.fixture
def local(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path, "http://api.test/", "s3cret", 60)


def test_local_round_trip(local: LocalStorage) -> None:
    local.put("videos/a/x.mp4", b"abc", "video/mp4")
    assert local.exists("videos/a/x.mp4")
    assert not local.exists("videos/a/x.mp4", public=True)
    assert local.get("videos/a/x.mp4") == b"abc"
    local.delete("videos/a/x.mp4")
    assert not local.exists("videos/a/x.mp4")


def test_local_links(local: LocalStorage) -> None:
    url = local.signed_url("videos/a/x.mp4", 30)
    assert url.startswith("http://api.test/media/videos/a/x.mp4?exp=")
    exp = int(url.split("exp=")[1].split("&")[0])
    sig = url.split("sig=")[1]
    assert verify_signature("s3cret", "videos/a/x.mp4", exp, sig)
    assert not verify_signature("other", "videos/a/x.mp4", exp, sig)
    assert not verify_signature("s3cret", "videos/a/x.mp4", exp, sig, now=exp + 1)
    assert local.public_url("games/g.html") == "http://api.test/public/games/g.html"


@pytest.mark.parametrize("key", ["../etc/passwd", "/abs", "a//b", "a b", "", "x/../y"])
def test_bad_keys_are_rejected(key: str) -> None:
    with pytest.raises(InvalidKeyError):
        check_key(key)


def test_data_url(local: LocalStorage) -> None:
    local.put("p.png", b"\x89PNG", "image/png")
    assert data_url(local, "p.png", "image/png") == "data:image/png;base64,iVBORw=="


def test_sign_is_deterministic() -> None:
    assert sign("k", "a", 1) == sign("k", "a", 1) != sign("k", "a", 2)


class FakeSupabase:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/storage/v1")
        assert request.headers["apikey"] == "svc"
        assert request.headers["authorization"] == "Bearer svc"
        if request.method == "POST" and path.startswith("/object/sign/"):
            body = json.loads(request.content)
            target = path.removeprefix("/object/sign/")
            return httpx.Response(
                200, json={"signedURL": f"/object/sign/{target}?token=t{body['expiresIn']}"}
            )
        if request.method == "POST" and path.startswith("/object/"):
            self.objects[path.removeprefix("/object/")] = request.content
            return httpx.Response(200, json={"Key": path})
        if request.method in {"GET", "HEAD"} and path.startswith("/object/"):
            data = self.objects.get(path.removeprefix("/object/"))
            return (
                httpx.Response(200, content=data)
                if data is not None
                else httpx.Response(404, json={"error": "not found"})
            )
        if request.method == "DELETE":
            for prefix in json.loads(request.content)["prefixes"]:
                self.objects.pop(f"{path.removeprefix('/object/')}/{prefix}", None)
            return httpx.Response(200, json=[])
        return httpx.Response(500, text="unexpected")


@pytest.fixture
def fake() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def supabase(fake: FakeSupabase) -> SupabaseStorage:
    client = httpx.Client(transport=httpx.MockTransport(fake.handler))
    return SupabaseStorage("https://proj.supabase.co/", "svc", "priv", "pub", 120, client=client)


def test_supabase_round_trip(supabase: SupabaseStorage, fake: FakeSupabase) -> None:
    supabase.put("videos/v/original.mp4", b"data", "video/mp4")
    upload = fake.requests[-1]
    assert upload.headers["x-upsert"] == "true"
    assert upload.headers["content-type"] == "video/mp4"
    assert supabase.get("videos/v/original.mp4") == b"data"
    assert supabase.exists("videos/v/original.mp4")
    supabase.put("games/g.html", b"<html>", "text/html", public=True)
    assert "pub/games/g.html" in fake.objects
    supabase.delete("videos/v/original.mp4")
    assert not supabase.exists("videos/v/original.mp4")


def test_supabase_links(supabase: SupabaseStorage) -> None:
    assert supabase.signed_url("videos/v/a.mp4") == (
        "https://proj.supabase.co/storage/v1/object/sign/priv/videos/v/a.mp4?token=t120"
    )
    assert supabase.public_url("games/g.html") == (
        "https://proj.supabase.co/storage/v1/object/public/pub/games/g.html"
    )


def test_supabase_errors_are_clear(supabase: SupabaseStorage) -> None:
    with pytest.raises(ExternalServiceError, match="Supabase Storage: HTTP 404"):
        supabase.get("missing.mp4")


def test_build_storage_picks_backend(tmp_path: Path) -> None:
    local = build_storage(Settings(storage_backend=StorageBackend.LOCAL, local_media_dir=tmp_path))
    assert isinstance(local, LocalStorage)
    remote = build_storage(
        Settings(storage_backend=StorageBackend.SUPABASE, supabase_url="https://p.supabase.co")
    )
    assert isinstance(remote, SupabaseStorage)


def test_signed_url_expiry_is_in_future(local: LocalStorage) -> None:
    exp = int(local.signed_url("a.mp4").split("exp=")[1].split("&")[0])
    assert exp > time.time()
