"""MCP endpoint (feature 52): any AI assistant that speaks the Model Context Protocol can
order a playable ad and follow it until it is live.

Streamable HTTP, stateless: each ``POST /mcp`` carries one JSON-RPC message and gets one
JSON answer. Three tools:

- ``list_game_templates``: the games Reel2Play can make.
- ``make_playable_ad``: a public https link to a video the shop owns, the shop's details and
  its offer. The video is fetched safely (public internet only), checked like any upload,
  and goes through the same agents, tests and safety rules as one from the web page.
- ``get_playable_ad``: where the ad is, and once it is live, the game link, the Reel, the
  poster and the Meta playable files.

What an assistant passes in is data, never instructions to our agents: it goes through the
same prompt-injection guard as a video's own text. A browser page may not call the endpoint
from another site (the Origin header is checked).
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Header, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select

from reel2play import audit
from reel2play.builder.templates import buildable, load_templates
from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.intake.fetch import FETCHERS, FetchError
from reel2play.intake.upload import (
    Brief,
    UploadLimits,
    UploadRejectedError,
    accept_upload,
    classify,
)
from reel2play.models import Ad, Shop, Video
from reel2play.ratelimit import RateLimiter, caller_key
from reel2play.routes.ads import get_ad
from reel2play.settings import Settings
from reel2play.shops import issue_key, shop_for_key

router = APIRouter(tags=["mcp"])

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
SERVER = {"name": "reel2play", "title": "Reel2Play", "version": "0.1.0"}
INSTRUCTIONS = (
    "Reel2Play turns a shop's own product video into a short, tested mini-game ad that ends "
    "on the shop's offer. Call make_playable_ad with a public https link to a video the shop "
    "owns (the shop must confirm it), then call get_playable_ad every minute or so until the "
    "status is published (usually a few minutes). Built with Muse Spark Open."
)
MAX_BODY_BYTES = 64 * 1024
MAKERS: dict[int, RateLimiter] = {}


def makers(per_hour: int) -> RateLimiter:
    return MAKERS.setdefault(per_hour, RateLimiter(per_hour, 3600))


# --- tool arguments ------------------------------------------------------------------------


class MakeAdArgs(BaseModel):
    video_url: str = Field(max_length=2000)
    shop_name: str = Field(min_length=1, max_length=120)
    rights_confirmed: bool
    whatsapp_number: str | None = None
    shop_link: str | None = Field(default=None, max_length=500)
    price: str | None = Field(default=None, max_length=40)
    offer: str | None = Field(default=None, max_length=200)
    product_name: str | None = Field(default=None, max_length=60)
    language: Literal["auto", "ur", "en"] = "auto"
    occasion: Literal[
        "none", "ramzan", "eid", "independence_day", "wedding_season", "winter_sale"
    ] = "none"
    shop_key: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _contact(self) -> MakeAdArgs:
        if not self.whatsapp_number and not self.shop_link:
            raise ValueError("give whatsapp_number or shop_link, where customers will order")
        return self


class GetAdArgs(BaseModel):
    video_id: uuid.UUID | None = None
    ad_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one(self) -> GetAdArgs:
        if self.video_id is None and self.ad_id is None:
            raise ValueError("give video_id (from make_playable_ad) or ad_id")
        return self


TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_game_templates",
        "title": "List game templates",
        "description": "The kinds of mini-game Reel2Play can make, and what each suits.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "make_playable_ad",
        "title": "Make a playable ad",
        "description": (
            "Turn a shop's own product video (or photo) into a tested 15-30 second mini-game ad "
            "that ends on the shop's offer and a WhatsApp order button. The shop must own the "
            "video; its sound is removed. Returns a video_id to follow with get_playable_ad."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_url": {
                    "type": "string",
                    "description": "Public https link to an MP4, MOV or WebM video, or a photo",
                },
                "shop_name": {"type": "string"},
                "rights_confirmed": {
                    "type": "boolean",
                    "description": "True only if the shop owns this video and agrees to its use",
                },
                "whatsapp_number": {
                    "type": "string",
                    "description": "Where customers order, with country code: 923001234567",
                },
                "shop_link": {"type": "string", "description": "Or an https shop page"},
                "price": {"type": "string", "description": "Shown exactly as given: Rs 2,499"},
                "offer": {"type": "string", "description": "Like: 20% off this week"},
                "product_name": {"type": "string"},
                "language": {"type": "string", "enum": ["auto", "ur", "en"]},
                "occasion": {
                    "type": "string",
                    "enum": [
                        "none",
                        "ramzan",
                        "eid",
                        "independence_day",
                        "wedding_season",
                        "winter_sale",
                    ],
                },
                "shop_key": {
                    "type": "string",
                    "description": "The studio key from an earlier ad, to add this one to it",
                },
            },
            "required": ["video_url", "shop_name", "rights_confirmed"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    },
    {
        "name": "get_playable_ad",
        "title": "Follow a playable ad",
        "description": (
            "Where an ad is: its status and latest step, and once published the game link, the "
            "gameplay Reel, the counter poster, captions and the Meta playable files."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id": {"type": "string", "description": "From make_playable_ad"},
                "ad_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
]


# --- JSON-RPC plumbing -----------------------------------------------------------------------


class ToolError(Exception):
    """A tool could not do what was asked; the message goes back to the assistant."""


def rpc_result(message_id: Any, result: dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": message_id, "result": result})


def rpc_error(
    message_id: Any, code: int, message: str, http: int = status.HTTP_200_OK
) -> JSONResponse:
    body = {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}
    return JSONResponse(body, status_code=http)


def tool_result(data: dict[str, Any], text: str, *, error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": data,
        "isError": error,
    }


def origin_allowed(origin: str | None, settings: Settings) -> bool:
    """Browsers send Origin; a page on another site must not drive the endpoint."""
    if origin is None:
        return True
    allowed = {settings.web_base_url.rstrip("/"), *settings.cors_origin_list}
    return origin.rstrip("/") in allowed


@router.post("/mcp")
async def mcp(
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    origin: str | None = Header(default=None),
    mcp_protocol_version: str | None = Header(default=None),
) -> Response:
    if not origin_allowed(origin, settings):
        return rpc_error(None, -32600, "This origin may not use the endpoint.", 403)
    if mcp_protocol_version and mcp_protocol_version not in PROTOCOL_VERSIONS:
        return rpc_error(None, -32600, "Unsupported MCP-Protocol-Version.", 400)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return rpc_error(None, -32600, "Message too large.", 413)
    try:
        message = json.loads(body)
    except ValueError:
        return rpc_error(None, -32700, "Parse error.", 400)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return rpc_error(None, -32600, "Send one JSON-RPC 2.0 message.", 400)
    method = message.get("method")
    if not isinstance(method, str):  # a response or a stray message: nothing to answer
        return Response(status_code=status.HTTP_202_ACCEPTED)
    if "id" not in message:  # notifications (initialized, cancelled) need no answer
        return Response(status_code=status.HTTP_202_ACCEPTED)
    message_id = message["id"]
    params = message.get("params") or {}
    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return rpc_result(
            message_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER,
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "ping":
        return rpc_result(message_id, {})
    if method == "tools/list":
        return rpc_result(message_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return rpc_error(message_id, -32602, "arguments must be an object")
        caller = request.client.host if request.client else "unknown"
        try:
            if name == "list_game_templates":
                result = list_templates(settings)
            elif name == "make_playable_ad":
                result = make_ad(session, storage, settings, arguments, caller)
            elif name == "get_playable_ad":
                result = follow_ad(session, storage, settings, arguments)
            else:
                return rpc_error(message_id, -32602, f"Unknown tool: {name}")
        except ToolError as exc:
            result = tool_result({"error": str(exc)}, str(exc), error=True)
        return rpc_result(message_id, result)
    return rpc_error(message_id, -32601, f"Method not found: {method}")


@router.get("/mcp")
def mcp_stream() -> Response:
    """No server-to-client stream: every answer comes back on its own POST."""
    return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": "POST"})


# --- the tools ---------------------------------------------------------------------------------


def problem_of(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: "
        f"{str(e['msg']).removeprefix('Value error, ')}"
        for e in exc.errors()
    )


def list_templates(settings: Settings) -> dict[str, Any]:
    templates = [
        {
            "id": spec.id,
            "name": spec.name,
            "what_happens": spec.description,
            "control": spec.control,
            "good_for": [c.replace("_", " ") for c in spec.good_for],
        }
        for spec in buildable(load_templates(settings.templates_dir)).values()
    ]
    text = "\n".join(f"- {t['name']}: {t['what_happens']}" for t in templates)
    return tool_result({"templates": templates}, text)


def make_ad(
    session: SessionDep,
    storage: StorageDep,
    settings: Settings,
    arguments: dict[str, Any],
    caller: str,
) -> dict[str, Any]:
    try:
        args = MakeAdArgs.model_validate(arguments)
    except ValidationError as exc:
        raise ToolError(problem_of(exc)) from exc
    if not args.rights_confirmed:
        raise ToolError(
            "Reel2Play only uses videos the shop owns. Ask the shop to confirm, then set "
            "rights_confirmed to true."
        )
    shop: Shop | None = None
    if args.shop_key:
        shop = shop_for_key(session, args.shop_key)
        if shop is None:
            raise ToolError("That shop_key is not known. Leave it out to start a new shop.")
    if not makers(settings.mcp_ads_per_hour).allow(caller_key(caller, "mcp")):
        raise ToolError("Too many ads from here this hour. Try again later.")
    try:
        brief = Brief(
            shop_name=args.shop_name,
            shop_id=shop.id if shop else None,
            language=args.language,
            whatsapp_number=args.whatsapp_number,
            shop_url=args.shop_link,
            price=args.price,
            offer=args.offer,
            rights_confirmed=True,
            occasion=args.occasion,
            product_name=args.product_name,
        )
        data = FETCHERS().fetch(args.video_url, settings.max_upload_bytes)
        files = classify([data], UploadLimits(settings.max_upload_bytes, settings.max_photos))
        video = accept_upload(session, storage, brief, files, source="mcp")
    except ValidationError as exc:
        raise ToolError(problem_of(exc)) from exc
    except (FetchError, UploadRejectedError) as exc:
        raise ToolError(str(exc)) from exc
    owner = session.get(Shop, video.shop_id)
    key = issue_key(owner) if shop is None and owner is not None else None
    audit.record(
        session,
        actor="assistant",
        action="mcp.ordered",
        subject_type="video",
        subject_id=video.id,
        data={"message": "An AI assistant ordered a playable ad over MCP."},
    )
    found = {
        "video_id": str(video.id),
        "status": "received",
        "next": "Call get_playable_ad with this video_id in about a minute.",
        "studio_url": f"{settings.web_base_url.rstrip('/')}/studio",
    }
    if key:
        found["shop_key"] = key
    text = (
        f"Received. The agents are making and testing the game; follow it with "
        f"get_playable_ad(video_id={video.id})."
        + (f" Keep this shop_key to add more ads to the same shop: {key}" if key else "")
    )
    return tool_result(found, text)


def follow_ad(
    session: SessionDep, storage: StorageDep, settings: Settings, arguments: dict[str, Any]
) -> dict[str, Any]:
    try:
        args = GetAdArgs.model_validate(arguments)
    except ValidationError as exc:
        raise ToolError(problem_of(exc)) from exc
    ad_id = args.ad_id
    if ad_id is None:
        video = session.get(Video, args.video_id)
        if video is None:
            raise ToolError("No upload with that video_id.")
        ad_id = session.scalars(
            select(Ad.id)
            .where(Ad.video_id == video.id, Ad.variant == "A", Ad.easier_for.is_(None))
            .order_by(Ad.created_at)
        ).first()
        if ad_id is None:
            message = (
                f"The upload could not be used: {video.error}"
                if video.status == "failed"
                else "The video is being prepared (its sound removed); ask again in a minute."
            )
            return tool_result({"status": video.status, "message": message}, message)
    if session.get(Ad, ad_id) is None:
        raise ToolError("No ad with that ad_id.")
    ad = get_ad(ad_id, session, storage, settings)
    latest = ad.progress[-1].message if ad.progress else None
    found: dict[str, Any] = {
        "ad_id": str(ad.id),
        "status": ad.status,
        "step": ad.step,
        "latest": latest,
        "page": f"{settings.web_base_url.rstrip('/')}/ads/{ad.id}",
    }
    if ad.error:
        found["error"] = ad.error
    if ad.report:
        found["report"] = {
            "passed": ad.report.passed,
            "summary": ad.report.summary,
            "worth_checking": ad.report.warnings,
        }
    if ad.share:
        found["game_link"] = ad.share.link
        found["reel_url"] = ad.share.reel_url
        found["poster_url"] = ad.share.poster_url
        found["captions"] = ad.share.captions
        found["meta_playable_url"] = ad.share.meta_html_url
    text = (
        f"Published: {ad.share.link}"
        if ad.share
        else f"Status: {ad.status}" + (f". {latest}" if latest else "")
    )
    return tool_result(found, text)
