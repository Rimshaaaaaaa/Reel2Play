"""The MCP endpoint (feature 52) and the safe fetch it uses for a shop's video."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play.intake.fetch import FETCHERS, Fetcher, FetchError, public_address, system_resolver
from reel2play.models import Ad, AdStatus, Shop, Video
from reel2play.routes.mcp import MAKERS
from reel2play.settings import get_settings
from tests.helpers import drain

PUBLIC_IP = "93.184.215.14"


def resolver(table: dict[str, list[str]]) -> Any:
    return lambda host: table.get(host, [PUBLIC_IP])


def fetcher_serving(files: dict[str, bytes], seen: list[httpx.Request] | None = None) -> Fetcher:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        path = request.url.path
        if path.startswith("/moved"):
            return httpx.Response(302, headers={"location": "https://cdn.example/clip.mp4"})
        if path in files:
            return httpx.Response(200, content=files[path])
        return httpx.Response(404)

    return Fetcher(transport=httpx.MockTransport(handle), resolve=resolver({}))


@pytest.fixture
def served(sample_media: dict[str, Path]) -> Iterator[list[httpx.Request]]:
    seen: list[httpx.Request] = []
    files = {"/clip.mp4": sample_media["product_video"].read_bytes()}
    original = FETCHERS.build
    FETCHERS.build = lambda: fetcher_serving(files, seen)
    MAKERS.clear()
    yield seen
    FETCHERS.build = original


def rpc(
    client: TestClient, method: str, params: dict[str, Any] | None = None, **headers: str
) -> Any:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": 7, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers)


def call(client: TestClient, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = rpc(client, "tools/call", {"name": tool, "arguments": arguments})
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()["result"]
    return result


ORDER = {
    "video_url": "https://shop.example/clip.mp4",
    "shop_name": "Synthetic Shoes",
    "rights_confirmed": True,
    "whatsapp_number": "923001234567",
    "price": "Rs 3,200",
    "offer": "20% off",
}


def test_an_assistant_connects_and_lists_what_it_can_do(client: TestClient) -> None:
    hello = rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    result = hello.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["serverInfo"]["name"] == "reel2play"
    assert "Built with Muse Spark Open" in result["instructions"]
    newer = rpc(client, "initialize", {"protocolVersion": "2099-01-01"}).json()["result"]
    assert newer["protocolVersion"] == "2025-11-25"
    note = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert note.status_code == 202
    assert rpc(client, "ping").json()["result"] == {}
    tools = rpc(client, "tools/list").json()["result"]["tools"]
    assert [t["name"] for t in tools] == [
        "list_game_templates",
        "make_playable_ad",
        "get_playable_ad",
    ]
    assert tools[1]["inputSchema"]["required"] == ["video_url", "shop_name", "rights_confirmed"]
    templates = call(client, "list_game_templates", {})
    assert len(templates["structuredContent"]["templates"]) == 9
    assert "Catch" in templates["content"][0]["text"]


def test_bad_messages_get_json_rpc_errors(client: TestClient) -> None:
    assert client.post("/mcp", content="{").json()["error"]["code"] == -32700
    assert client.post("/mcp", json=[{"jsonrpc": "2.0"}]).status_code == 400
    assert rpc(client, "resources/list").json()["error"]["code"] == -32601
    assert client.get("/mcp").status_code == 405
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "result": {}}).status_code == 202
    assert rpc(client, "ping", Origin="https://evil.example").status_code == 403
    assert rpc(client, "ping", Origin=get_settings().web_base_url).status_code == 200
    old = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"MCP-Protocol-Version": "1999-01-01"},
    )
    assert old.status_code == 400
    assert client.post("/mcp", content="x" * 70_000).status_code == 413
    unknown = rpc(client, "tools/call", {"name": "launch", "arguments": {}}).json()
    assert unknown["error"]["code"] == -32602
    bad_args = rpc(client, "tools/call", {"name": "get_playable_ad", "arguments": [1]}).json()
    assert bad_args["error"]["code"] == -32602


def test_an_assistant_orders_an_ad_and_follows_it(
    client: TestClient,
    session: Session,
    served: list[httpx.Request],
    stop_after_build: None,
) -> None:
    ordered = call(client, "make_playable_ad", ORDER)
    assert ordered["isError"] is False
    found = ordered["structuredContent"]
    video_id = found["video_id"]
    assert found["shop_key"]
    assert found["shop_key"] in ordered["content"][0]["text"]
    video = session.get(Video, uuid.UUID(video_id))
    assert video is not None
    assert (video.source, video.owner_price, video.rights_confirmed) == ("mcp", "Rs 3,200", True)

    # The video was fetched from the address that was checked, by its host's name.
    [request] = served
    assert request.url.host == PUBLIC_IP
    assert request.headers["host"] == "shop.example"
    assert request.extensions["sni_hostname"] == "shop.example"

    early = call(client, "get_playable_ad", {"video_id": video_id})
    assert early["structuredContent"]["status"] == "uploaded"
    drain()
    following = call(client, "get_playable_ad", {"video_id": video_id})["structuredContent"]
    assert following["status"] == "building"
    assert following["page"].endswith(f"/ads/{following['ad_id']}")
    session.execute(update(Ad).values(status=AdStatus.PUBLISHED, slug="AbC1234"))
    session.commit()
    live = call(client, "get_playable_ad", {"ad_id": following["ad_id"]})
    assert live["structuredContent"]["game_link"] == "http://testserver/g/AbC1234"
    assert live["content"][0]["text"] == "Published: http://testserver/g/AbC1234"

    # The same shop, with its key; a wrong key is refused.
    again = call(client, "make_playable_ad", {**ORDER, "shop_key": found["shop_key"]})
    assert "shop_key" not in again["structuredContent"]
    assert len(session.scalars(select(Shop)).all()) == 1
    wrong = call(client, "make_playable_ad", {**ORDER, "shop_key": "nope"})
    assert wrong["isError"] is True


def test_the_shop_must_own_the_video_and_say_where_to_order(
    client: TestClient,
    session: Session,
    served: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused = call(client, "make_playable_ad", {**ORDER, "rights_confirmed": False})
    assert refused["isError"] is True
    assert "only uses videos the shop owns" in refused["content"][0]["text"]
    no_contact = call(client, "make_playable_ad", {**ORDER, "whatsapp_number": None})
    assert "whatsapp_number or shop_link" in no_contact["content"][0]["text"]
    bad_phone = call(client, "make_playable_ad", {**ORDER, "whatsapp_number": "12"})
    assert bad_phone["isError"] is True
    missing = call(client, "make_playable_ad", {**ORDER, "video_url": "https://shop.example/x.mp4"})
    assert "answered with an error (404)" in missing["content"][0]["text"]
    assert call(client, "get_playable_ad", {})["isError"] is True
    assert call(client, "get_playable_ad", {"video_id": str(uuid.uuid4())})["isError"] is True
    assert call(client, "get_playable_ad", {"ad_id": str(uuid.uuid4())})["isError"] is True
    assert len(served) == 1  # only the missing file was asked for; refused orders fetch nothing
    assert session.scalars(select(Video)).first() is None

    monkeypatch.setattr(get_settings(), "mcp_ads_per_hour", 1)
    assert call(client, "make_playable_ad", ORDER)["isError"] is False
    busy = call(client, "make_playable_ad", ORDER)
    assert "Too many ads" in busy["content"][0]["text"]


# --- the safe fetch ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "192.168.1.4", "169.254.169.254", "::1", "fd00::1", "224.0.0.1"],
)
def test_links_inside_the_network_are_never_fetched(address: str) -> None:
    with pytest.raises(FetchError, match="public internet"):
        public_address("inside.example", resolver({"inside.example": [address]}))
    with pytest.raises(FetchError, match="public internet"):
        public_address(address, resolver({}))
    mixed = resolver({"both.example": [PUBLIC_IP, address]})
    with pytest.raises(FetchError):
        public_address("both.example", mixed)
    with pytest.raises(FetchError, match="does not exist"):
        public_address("none.example", resolver({"none.example": []}))


def test_only_plain_https_links_are_fetched_and_redirects_are_checked() -> None:
    files = {"/clip.mp4": b"x" * 100}
    fetcher = fetcher_serving(files)
    for link, reason in (
        ("http://shop.example/clip.mp4", "Only https"),
        ("https://user:pw@shop.example/clip.mp4", "user name"),
        ("https://shop.example:8443/clip.mp4", "standard https port"),
        ("https://", "Only https"),
    ):
        with pytest.raises(FetchError, match=reason):
            fetcher.fetch(link, 1000)
    assert fetcher.fetch("https://shop.example/moved", 1000) == b"x" * 100
    with pytest.raises(FetchError, match="larger than"):
        fetcher.fetch("https://shop.example/clip.mp4", 50)

    inside = Fetcher(transport=fetcher.transport, resolve=resolver({"cdn.example": ["10.1.2.3"]}))
    with pytest.raises(FetchError, match="public internet"):
        inside.fetch("https://shop.example/moved", 1000)  # the redirect points inside

    def loop(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    looping = Fetcher(transport=httpx.MockTransport(loop), resolve=resolver({}))
    with pytest.raises(FetchError, match="somewhere else"):
        looping.fetch("https://shop.example/a", 1000)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    broken = Fetcher(transport=httpx.MockTransport(down), resolve=resolver({}))
    with pytest.raises(FetchError, match="could not be reached"):
        broken.fetch("https://shop.example/a", 1000)
    with pytest.raises(FetchError, match="does not exist"):
        system_resolver("no-such-host.invalid")


def test_tool_results_are_json_both_ways(client: TestClient) -> None:
    result = call(client, "list_game_templates", {})
    assert json.dumps(result["structuredContent"])
