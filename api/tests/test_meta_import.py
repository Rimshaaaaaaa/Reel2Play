"""Instagram and Facebook import (feature 3) against a fake Graph API: sign-in, the list of
the owner's own videos, and an imported video going through the normal upload path."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play.intake.meta_import import (
    IMPORTERS,
    NO_FILE,
    SESSIONS,
    MetaImporter,
    SessionStore,
    from_meta,
    importer_error,
)
from reel2play.models import Shop, Video
from reel2play.net import ExternalServiceError
from reel2play.settings import get_settings

APP_ID = "1234567890"
IG_FILE = "https://scontent.cdninstagram.com/v/444.mp4"
FB_FILE = "https://video.xx.fbcdn.net/v/333.mp4"
BRIEF = {
    "shop_name": "Synthetic Shoes",
    "whatsapp_number": "923001234567",
    "price": "Rs 2,499",
    "rights_confirmed": True,
}


@dataclass
class FakeGraph:
    """The Graph API calls the import makes, plus Meta's file servers."""

    video: bytes = b""
    seen_tokens: list[str] = field(default_factory=list)
    page_status: int = 200
    ig_file: str = IG_FILE

    def handler(self, request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.url.query.decode())
        token = query.get("access_token", [""])[0]
        path = request.url.path
        if request.url.host == "graph.facebook.com":
            self.seen_tokens.append(token)
        if path == "/v26.0/oauth/access_token":
            assert query["client_secret"] == ["app-secret"]
            if query["code"] != ["good-code"]:
                return httpx.Response(400, json={"error": {"message": "bad code"}})
            return httpx.Response(200, json={"access_token": "user-token"})
        if path == "/v26.0/me/accounts":
            if self.page_status != 200:
                return httpx.Response(self.page_status, json={"error": {"message": "no"}})
            return httpx.Response(200, json={"data": [self.page]})
        if path == "/v26.0/111/videos":
            assert token == "page-token"
            return httpx.Response(200, json={"data": [self.fb_video]})
        if path == "/v26.0/222/media":
            return httpx.Response(200, json={"data": self.ig_media})
        if path == "/v26.0/444":
            return httpx.Response(200, json={"media_url": self.ig_file, "id": "444"})
        if path == "/v26.0/555":
            return httpx.Response(200, json={"id": "555"})
        if path == "/v26.0/333":
            assert token == "page-token"
            return httpx.Response(200, json={"source": FB_FILE, "id": "333"})
        if str(request.url) in (IG_FILE, FB_FILE):
            return httpx.Response(200, content=self.video)
        if request.url.host == "redirect.cdninstagram.com":
            return httpx.Response(302, headers={"location": "https://evil.example/file.mp4"})
        if request.url.host == "hop.cdninstagram.com":
            return httpx.Response(302, headers={"location": IG_FILE})
        if request.url.host == "loop.fbcdn.net":
            return httpx.Response(302, headers={"location": "/again"})
        assert request.url.host != "evil.example", "asked a server that is not Meta's"
        return httpx.Response(404, json={"error": "unknown"})

    page: ClassVar[dict[str, Any]] = {
        "id": "111",
        "name": "Synthetic Shoes",
        "access_token": "page-token",
        "instagram_business_account": {"id": "222", "username": "synthetic.shoes"},
    }
    fb_video: ClassVar[dict[str, Any]] = {
        "id": "333",
        "description": "New sneakers",
        "picture": "https://scontent.xx.fbcdn.net/thumb-333.jpg",
        "created_time": "2026-10-01T10:00:00+0000",
        "source": FB_FILE,
    }
    ig_media: ClassVar[list[dict[str, Any]]] = [
        {
            "id": "444",
            "caption": "Sneaker drop",
            "media_type": "VIDEO",
            "media_url": IG_FILE,
            "thumbnail_url": "https://scontent.cdninstagram.com/t/444.jpg",
            "timestamp": "2026-10-20T09:00:00+0000",
        },
        {"id": "555", "media_type": "VIDEO", "timestamp": "2026-10-10T09:00:00+0000"},
        {"id": "666", "media_type": "IMAGE", "timestamp": "2026-10-25T09:00:00+0000"},
    ]


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> FakeGraph:
    settings = get_settings()
    monkeypatch.setattr(settings, "meta_app_id", APP_ID)
    monkeypatch.setattr(settings, "meta_app_secret", SecretStr("app-secret"))
    fake = FakeGraph()
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr(
        IMPORTERS, "build", lambda s: MetaImporter(s, httpx.Client(transport=transport))
    )
    return fake


def fragment(response: httpx.Response) -> dict[str, str]:
    assert response.status_code == 303, response.text
    location = urlsplit(response.headers["location"])
    web = urlsplit(get_settings().web_base_url).netloc
    assert (location.netloc, location.path, location.query) == (web, "/import", "")
    return {k: v[0] for k, v in parse_qs(location.fragment).items()}


def sign_in(client: TestClient) -> str:
    start = client.get("/api/import/meta/start", follow_redirects=False)
    assert start.status_code == 303
    login = urlsplit(start.headers["location"])
    assert (login.netloc, login.path) == ("www.facebook.com", "/v26.0/dialog/oauth")
    query = parse_qs(login.query)
    assert query["client_id"] == [APP_ID]
    assert query["scope"] == ["pages_show_list,pages_read_engagement,instagram_basic"]
    api = get_settings().api_base_url
    assert query["redirect_uri"] == [f"{api}/api/import/meta/callback"]
    back = client.get(
        "/api/import/meta/callback",
        params={"code": "good-code", "state": query["state"][0]},
        follow_redirects=False,
    )
    return fragment(back)["session"]


def test_the_import_is_off_without_a_meta_app(client: TestClient) -> None:
    assert client.get("/api/import/meta/status").json() == {"enabled": False}
    for path in ("/api/import/meta/start", "/api/import/meta/posts"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 503
        assert "not set up" in response.json()["detail"]


def test_sign_in_lists_only_the_owners_videos(client: TestClient, graph: FakeGraph) -> None:
    assert client.get("/api/import/meta/status").json() == {"enabled": True}
    sid = sign_in(client)
    response = client.get("/api/import/meta/posts", headers={"X-Import-Session": sid})
    assert response.status_code == 200, response.text
    posts = response.json()
    assert [p["id"] for p in posts] == ["ig:444", "ig:555", "fb:111:333"]
    reel, music, page_video = posts
    assert (reel["source"], reel["account"], reel["downloadable"]) == (
        "instagram",
        "@synthetic.shoes",
        True,
    )
    assert music["downloadable"] is False  # library music: Instagram keeps the file
    assert (page_video["source"], page_video["account"], page_video["caption"]) == (
        "facebook",
        "Synthetic Shoes",
        "New sneakers",
    )
    assert "user-token" not in response.text
    assert "page-token" not in response.text


def test_sign_in_problems_go_back_to_the_page(client: TestClient, graph: FakeGraph) -> None:
    callback = "/api/import/meta/callback"
    denied = client.get(callback, params={"error": "access_denied"}, follow_redirects=False)
    assert fragment(denied) == {"error": "denied"}
    forged = client.get(
        callback, params={"code": "good-code", "state": "made-up"}, follow_redirects=False
    )
    assert fragment(forged) == {"error": "expired"}

    start = client.get("/api/import/meta/start", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    bad = client.get(callback, params={"code": "bad", "state": state}, follow_redirects=False)
    assert fragment(bad) == {"error": "failed"}
    again = client.get(
        callback, params={"code": "good-code", "state": state}, follow_redirects=False
    )
    assert fragment(again) == {"error": "expired"}  # each state works once

    for headers in ({}, {"X-Import-Session": "not-a-session"}):
        response = client.get("/api/import/meta/posts", headers=headers)
        assert response.status_code == 401
        assert "Sign in again" in response.json()["detail"]


def test_an_imported_reel_goes_through_the_upload_path(
    client: TestClient, session: Session, graph: FakeGraph, sample_media: dict[str, Path]
) -> None:
    graph.video = sample_media["product_video"].read_bytes()
    sid = sign_in(client)
    headers = {"X-Import-Session": sid}
    assert len(client.get("/api/import/meta/posts", headers=headers).json()) == 3
    response = client.post(
        "/api/import/meta/use", headers=headers, json={"post_id": "ig:444", **BRIEF}
    )
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["shop_key"]  # a new shop gets its studio key, as with a web upload
    video = session.scalars(select(Video)).one()
    assert (video.source, video.rights_confirmed, video.owner_price) == (
        "instagram",
        True,
        "Rs 2,499",
    )

    # A Facebook Page video, into the same shop, with that shop's key.
    shop = session.scalars(select(Shop)).one()
    page_video = {"post_id": "fb:111:333", **BRIEF, "shop_id": str(shop.id)}
    keyed = {**headers, "X-Shop-Key": out["shop_key"]}
    assert client.post("/api/import/meta/use", headers=keyed, json=page_video).status_code == 201
    assert client.post("/api/import/meta/use", headers=headers, json=page_video).status_code == 403
    sources = session.scalars(select(Video.source).order_by(Video.created_at)).all()
    assert sources == ["instagram", "facebook"]


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"post_id": "ig:555"}, NO_FILE),
        ({"post_id": "fb:999:333"}, "not one of yours"),
        ({"post_id": "fb:111:abc"}, "not one of yours"),
        ({"post_id": "ig:../me"}, "not one of yours"),
        ({"post_id": "x:1"}, "not one of yours"),
        ({"post_id": "ig:444", "rights_confirmed": False}, "confirm the video is yours"),
        ({"post_id": "ig:444", "shop_url": "http://shop"}, "must start with https://"),
    ],
)
def test_posts_that_cannot_be_used_are_explained(
    client: TestClient, graph: FakeGraph, body: dict[str, Any], detail: str
) -> None:
    graph.video = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64
    sid = sign_in(client)
    client.get("/api/import/meta/posts", headers={"X-Import-Session": sid})  # learns the Page
    response = client.post(
        "/api/import/meta/use", headers={"X-Import-Session": sid}, json={**BRIEF, **body}
    )
    assert response.status_code == 422, response.text
    assert detail in response.json()["detail"]


def test_files_only_come_from_meta_and_stay_under_the_limit(
    client: TestClient, graph: FakeGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid = sign_in(client)
    headers = {"X-Import-Session": sid}
    use = {"post_id": "ig:444", **BRIEF}

    graph.ig_file = "https://evil.example/file.mp4"
    response = client.post("/api/import/meta/use", headers=headers, json=use)
    assert (response.status_code, response.json()["detail"]) == (
        422,
        "Facebook sent an address we do not download from.",
    )
    graph.ig_file = "https://redirect.cdninstagram.com/file.mp4"
    assert client.post("/api/import/meta/use", headers=headers, json=use).status_code == 422
    graph.ig_file = "https://loop.fbcdn.net/file.mp4"
    response = client.post("/api/import/meta/use", headers=headers, json=use)
    assert "somewhere else" in response.json()["detail"]

    graph.ig_file = "https://hop.cdninstagram.com/file.mp4"  # one hop within Meta is fine
    graph.video = b"\x00" * (1024 * 1024 + 1)
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    response = client.post("/api/import/meta/use", headers=headers, json=use)
    assert (response.status_code, response.json()["detail"]) == (
        422,
        "The video is larger than 1 MB.",
    )


def test_facebook_refusing_is_explained(client: TestClient, graph: FakeGraph) -> None:
    sid = sign_in(client)
    graph.page_status = 403
    response = client.get("/api/import/meta/posts", headers={"X-Import-Session": sid})
    assert response.status_code == 502
    assert response.json()["detail"].startswith("Facebook did not allow that.")


def test_use_needs_a_session_and_reports_graph_errors(
    client: TestClient, graph: FakeGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    use = {"post_id": "ig:444", **BRIEF}
    assert client.post("/api/import/meta/use", json=use).status_code == 401
    sid = sign_in(client)

    def refuse(self: MetaImporter, session: object, post_id: str) -> str:
        raise ExternalServiceError("Meta Graph API", "HTTP 401", status=401)

    monkeypatch.setattr(MetaImporter, "file_url", refuse)
    response = client.post("/api/import/meta/use", headers={"X-Import-Session": sid}, json=use)
    assert response.status_code == 502
    assert "Sign in again" in response.json()["detail"]


# --- small pieces ---------------------------------------------------------------------------


def test_sessions_and_states_expire() -> None:
    now = [1000.0]
    store = SessionStore(clock=lambda: now[0])
    state = store.new_state()
    sid = store.open("token")
    assert store.get(sid) is not None
    now[0] += 11 * 60
    assert store.take_state(state) is False
    assert store.get(sid) is not None
    now[0] += 20 * 60
    assert store.get(sid) is None
    other = store.open("token")
    store.close(other)
    assert store.get(other) is None
    assert SESSIONS.get("nothing") is None


def test_a_login_configuration_replaces_the_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "meta_app_id", APP_ID)
    monkeypatch.setattr(settings, "meta_login_config_id", "987654")
    query = parse_qs(urlsplit(MetaImporter(settings).login_url("s")).query)
    assert query["config_id"] == ["987654"]
    assert "scope" not in query


def test_small_helpers() -> None:
    assert from_meta("https://scontent-lhr8-1.cdninstagram.com/v/a.mp4")
    assert from_meta("https://video.xx.fbcdn.net/v/a.mp4")
    assert not from_meta("http://video.xx.fbcdn.net/v/a.mp4")
    assert not from_meta("https://fbcdn.net.evil.example/a.mp4")
    assert importer_error(ExternalServiceError("x", "y", status=503)).startswith(
        "Facebook did not answer"
    )
