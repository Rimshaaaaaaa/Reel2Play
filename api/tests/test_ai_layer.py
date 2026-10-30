"""Provider layer: wire format, failover, reasoning settings, JSON validation, cost."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, SecretStr
from sqlalchemy.orm import Session

from reel2play.ai.client import AIClient, AIUnavailableError, Subject, build_ai, build_routes
from reel2play.ai.config import (
    EndpointConfig,
    ReasoningStyle,
    Role,
    RolesConfig,
    load_roles,
    resolve_endpoint,
)
from reel2play.ai.cost import DbRecorder, MemoryRecorder, summarize, to_pkr, usd_cost
from reel2play.ai.jsonout import JSONOutputError, extract_json_object, parse_as
from reel2play.ai.messages import (
    ChatRequest,
    ChatResponse,
    Media,
    MediaKind,
    Usage,
    assistant,
    system,
    user,
)
from reel2play.ai.prompts import PromptError, available_prompts, parse_prompt
from reel2play.ai.providers import (
    CallContext,
    MissingFixtureError,
    MockProvider,
    OpenAICompatibleProvider,
    parse_completion,
)
from reel2play.net import ExternalServiceError
from reel2play.settings import AIMode, Settings
from tests.helpers import PROMPT, Scripted, make_client


class Answer(BaseModel):
    product: str
    score: int


# --- messages -----------------------------------------------------------------------------


def test_messages_to_wire() -> None:
    msg = user(
        "look",
        [
            Media(MediaKind.IMAGE, "https://x/a.png"),
            Media(MediaKind.VIDEO, "https://x/v.mp4"),
            Media(MediaKind.AUDIO, "data:audio/mpeg;base64,AA=="),
        ],
    )
    wire = msg.to_wire()
    assert wire["content"][0] == {"type": "text", "text": "look"}
    assert [p["type"] for p in wire["content"][1:]] == ["image_url", "video_url", "audio_url"]
    assert wire["content"][3]["audio_url"]["url"].startswith("data:audio/mpeg")
    assert assistant("done").to_wire() == {"role": "assistant", "content": "done"}
    assert system("s").to_wire() == {"role": "system", "content": "s"}


# --- config -------------------------------------------------------------------------------


def test_roles_file_is_valid_and_complete() -> None:
    roles = load_roles()
    assert set(roles.roles) == set(Role)
    assert roles.roles[Role.TESTER].endpoints[0] == "modal_glimmer"
    assert roles.endpoints["modal_glimmer"].reasoning_style is ReasoningStyle.SYSTEM_PROMPT


def test_roles_config_rejects_unknown_endpoint() -> None:
    raw: dict[str, Any] = {
        "endpoints": {},
        "roles": {r.value: {"description": "d", "endpoints": ["nope"]} for r in Role},
    }
    with pytest.raises(ValueError, match="unknown endpoints"):
        RolesConfig.model_validate(raw).check()
    raw["roles"] = {}
    with pytest.raises(ValueError, match="no config"):
        RolesConfig.model_validate(raw).check()


def test_resolve_endpoint_reads_settings() -> None:
    cfg = load_roles().endpoints["baseten_spark"]
    settings = Settings(baseten_api_key="k")  # type: ignore[arg-type]
    endpoint = resolve_endpoint("baseten_spark", cfg, settings)
    assert endpoint.configured
    assert endpoint.model == "meta-models/muse-spark-open"
    assert not resolve_endpoint("baseten_spark", cfg, Settings()).configured


# --- providers ----------------------------------------------------------------------------


def _endpoint(style: ReasoningStyle) -> Any:
    cfg = EndpointConfig(
        label="Test EP",
        base_url_setting="baseten_base_url",
        api_key_setting="baseten_api_key",
        model_setting="spark_model_baseten",
        reasoning_style=style,
    )
    return resolve_endpoint("ep", cfg, Settings(baseten_api_key="key"))  # type: ignore[arg-type]


def test_reasoning_effort_goes_in_the_body() -> None:
    provider = OpenAICompatibleProvider(_endpoint(ReasoningStyle.REASONING_EFFORT))
    body = provider.build_body(
        ChatRequest([system("s"), user("u")], reasoning="high", temperature=0.5)
    )
    assert body["reasoning_effort"] == "high"
    assert body["temperature"] == 0.5
    assert body["messages"][0]["content"] == "s"


def test_reasoning_strength_goes_in_the_system_prompt() -> None:
    provider = OpenAICompatibleProvider(_endpoint(ReasoningStyle.SYSTEM_PROMPT))
    body = provider.build_body(
        ChatRequest([system("You test games."), user("u")], reasoning="xhigh")
    )
    assert "reasoning_effort" not in body
    assert body["messages"][0]["content"].endswith("Reasoning strength: xhigh")
    no_system = provider.build_body(ChatRequest([user("u")], reasoning="low"))
    assert no_system["messages"][0] == {"role": "system", "content": "Reasoning strength: low"}


def test_provider_posts_and_parses() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": [{"type": "text", "text": "hello"}],
                            "reasoning_content": "thinking",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        )

    provider = OpenAICompatibleProvider(
        _endpoint(ReasoningStyle.REASONING_EFFORT),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = provider.chat(ChatRequest([user("hi")]), CallContext("p"))
    assert seen[0].url == "https://inference.baseten.co/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer key"
    assert json.loads(seen[0].content)["model"] == "meta-models/muse-spark-open"
    assert response.text == "hello"
    assert response.reasoning_text == "thinking"
    assert response.usage == Usage(12, 3)
    assert response.endpoint == "ep"


def test_provider_errors_are_clear() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(429, text="slow down"))
    )
    provider = OpenAICompatibleProvider(_endpoint(ReasoningStyle.REASONING_EFFORT), client=client)
    with pytest.raises(ExternalServiceError, match="Test EP: HTTP 429") as info:
        provider.chat(ChatRequest([user("hi")]), CallContext("p"))
    assert info.value.retryable
    with pytest.raises(ExternalServiceError, match="no choices"):
        parse_completion("svc", {"choices": []})
    assert parse_completion("svc", {"choices": [{"message": {"content": None}}]}).text == ""


def test_mock_provider_uses_fixtures(tmp_path: Path) -> None:
    (tmp_path / "game.json").write_text(
        json.dumps(
            {
                "default": {"text": {"product": "shoe", "score": 1}},
                "bakery": {"text": "cake"},
                "agent": [{"text": "first"}, {"text": "done"}],
            }
        )
    )
    mock = MockProvider(tmp_path)
    first = mock.chat(ChatRequest([user("u")]), CallContext("game"))
    assert json.loads(first.text) == {"product": "shoe", "score": 1}
    assert first.usage.output_tokens > 0
    assert mock.chat(ChatRequest([user("u")]), CallContext("game", "bakery")).text == "cake"
    step_one = mock.chat(ChatRequest([user("u")]), CallContext("game", "agent"))
    assert step_one.text == "first"
    step_two = mock.chat(ChatRequest([user("u"), assistant("")]), CallContext("game", "agent"))
    assert step_two.text == "done"
    with pytest.raises(MissingFixtureError):
        mock.chat(ChatRequest([user("u")]), CallContext("absent"))
    (tmp_path / "nodefault.json").write_text("{}")
    with pytest.raises(MissingFixtureError, match="no 'x' or default"):
        mock.chat(ChatRequest([user("u")]), CallContext("nodefault", "x"))


# --- prompts ------------------------------------------------------------------------------


def test_prompt_parse_and_render() -> None:
    prompt = parse_prompt("p", PROMPT)
    assert prompt.role is Role.DIRECTOR
    assert prompt.version == 3
    assert prompt.render({"shop": "Ali Shoes", "product": "sneakers"}) == (
        "You direct games for Ali Shoes.",
        "Look at the video of sneakers.",
    )
    with pytest.raises(PromptError, match="needs variable 'product'"):
        prompt.render({"shop": "x"})


@pytest.mark.parametrize("source", ["no front matter", "---\nrole: director\n---\n[system]\nx"])
def test_prompt_format_errors(source: str) -> None:
    with pytest.raises(PromptError):
        parse_prompt("bad", source)


def test_every_prompt_file_parses() -> None:
    from reel2play.ai.prompts import load_prompt

    for name in available_prompts():
        assert load_prompt(name).system
    with pytest.raises(PromptError, match="no prompt file"):
        load_prompt("does-not-exist")


# --- JSON output --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        '{"product": "shoe", "score": 2}',
        'Sure!\n```json\n{"product": "shoe", "score": 2}\n```',
        'note {not json} then {"product": "shoe", "score": 2} trailing',
        '{"product": "a \\"quoted\\" {brace}", "score": 2}',
    ],
)
def test_extract_json_object(text: str) -> None:
    assert parse_as(text, Answer).score == 2


def test_json_errors_are_explained() -> None:
    with pytest.raises(JSONOutputError, match="no JSON object"):
        extract_json_object("nothing here [1, 2]")
    with pytest.raises(JSONOutputError, match="score"):
        parse_as('{"product": "shoe"}', Answer)
    with pytest.raises(JSONOutputError):
        extract_json_object("{broken")


# --- client: failover, JSON repair, cost --------------------------------------------------


def _ok(text: str, tokens: tuple[int, int] = (1000, 200)) -> ChatResponse:
    return ChatResponse(text=text, usage=Usage(*tokens))


def test_failover_moves_to_the_next_endpoint() -> None:
    recorder = MemoryRecorder()
    primary = Scripted(
        "baseten_spark",
        [
            ExternalServiceError("Baseten", "down", status=503),
            ExternalServiceError("Baseten", "down", status=503),
        ],
    )
    backup = Scripted("fireworks_spark", [_ok('{"product": "shoe", "score": 7}')])
    client = make_client(primary, backup, recorder=recorder)
    answer = client.ask_json(
        "demo", {"shop": "S", "product": "P"}, Answer, subject=Subject(fixture_key="k")
    )
    assert answer == Answer(product="shoe", score=7)
    assert [c.endpoint for c in recorder.calls] == ["baseten_spark", "fireworks_spark"]
    assert [c.ok for c in recorder.calls] == [False, True]
    assert recorder.calls[1].usd == Decimal("0.002100")
    assert recorder.calls[1].pkr == Decimal("0.59")
    sent = backup.requests[0]
    assert sent.reasoning == "high"
    assert sent.max_tokens == 6000
    assert "JSON Schema" in sent.messages[0].text


def test_invalid_json_gets_one_repair_round() -> None:
    provider = Scripted(
        "baseten_spark", [_ok('{"product": "shoe"}'), _ok('{"product": "shoe", "score": 1}')]
    )
    client = make_client(provider)
    assert client.ask_json("demo", {"shop": "S", "product": "P"}, Answer).score == 1
    repair = provider.requests[1].messages
    assert repair[-2].role == "assistant"
    assert "could not be used" in repair[-1].text


def test_invalid_json_twice_raises() -> None:
    client = make_client(Scripted("baseten_spark", [_ok("no"), _ok("still no")]))
    with pytest.raises(JSONOutputError):
        client.ask_json("demo", {"shop": "S", "product": "P"}, Answer)


def test_all_endpoints_failing_raises_with_details() -> None:
    client = make_client(Scripted("baseten_spark", [ValueError("bad"), ValueError("bad")]))
    with pytest.raises(AIUnavailableError, match="baseten_spark: bad"):
        client.ask_text("demo", {"shop": "S", "product": "P"})
    empty = AIClient(load_roles(), {}, MemoryRecorder(), 280)
    with pytest.raises(AIUnavailableError, match="no endpoint is configured"):
        empty.chat(Role.DIRECTOR, ChatRequest([user("x")]), CallContext("p"))


def test_ask_text_strips_and_passes_media() -> None:
    provider = Scripted("baseten_spark", [_ok("  a caption  ")])
    client = make_client(provider)
    media = [Media(MediaKind.IMAGE, "https://x/a.png")]
    assert client.ask_text("demo", {"shop": "S", "product": "P"}, media=media) == "a caption"
    assert provider.requests[0].messages[1].media == media


def test_build_routes_mock_and_live() -> None:
    roles = load_roles()
    mock_routes = build_routes(roles, Settings(ai_mode=AIMode.MOCK))
    assert all(r[0].endpoint == "mock" for r in mock_routes.values())
    live = build_routes(roles, Settings(ai_mode=AIMode.LIVE, fireworks_api_key="fw"))  # type: ignore[arg-type]
    assert [r.endpoint for r in live[Role.DIRECTOR]] == ["fireworks_spark"]
    assert [r.endpoint for r in live[Role.TESTER]] == ["fireworks_spark"]
    with_glimmer = build_routes(
        roles,
        Settings(
            ai_mode=AIMode.LIVE,
            baseten_api_key=SecretStr("b"),
            glimmer_base_url="https://g.modal.run/v1",
            glimmer_api_key=SecretStr("g"),
        ),
    )
    assert [r.endpoint for r in with_glimmer[Role.TESTER]] == ["modal_glimmer", "baseten_spark"]


def test_cost_maths() -> None:
    glimmer = load_roles().endpoints["modal_glimmer"]
    assert usd_cost(glimmer, Usage(10_000, 10_000), 2000) == Decimal("0.002200")
    assert usd_cost(None, Usage(10, 10), 10) == Decimal(0)
    assert to_pkr(Decimal("1"), 280.5) == Decimal("280.50")


def test_db_recorder_and_summary(session: Session) -> None:
    client = build_ai(Settings(ai_mode=AIMode.MOCK), recorder=DbRecorder())
    import uuid

    ad_id = uuid.uuid4()
    request = client.request_for(Role.CAPTIONS, [user("Reply with the single word: ready")])
    client.chat(Role.CAPTIONS, request, CallContext("model_check"), Subject(ad_id=ad_id))
    total = summarize(session, ad_id=ad_id)
    assert total.calls == 1
    assert total.output_tokens >= 1
    assert summarize(session, video_id=uuid.uuid4()).calls == 0
