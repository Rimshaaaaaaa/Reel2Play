"""Model providers: one OpenAI-compatible client for every live endpoint, and the mock.

Baseten and Fireworks serve Muse Spark Open, and our Modal app serves Muse Glimmer through
vLLM's OpenAI-compatible server, so one client covers all three.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from reel2play.ai.config import ReasoningStyle, ResolvedEndpoint
from reel2play.ai.messages import ChatRequest, ChatResponse, Message, Usage
from reel2play.net import ExternalServiceError, auth_headers, make_client, raise_for_status

FIXTURES_DIR = Path(__file__).with_name("fixtures")


@dataclass(frozen=True)
class CallContext:
    """Why a call is made: which prompt, and (for the mock) which recorded fixture to use."""

    prompt_name: str
    fixture_key: str = "default"


class Provider(Protocol):
    name: str
    model: str

    def chat(self, request: ChatRequest, ctx: CallContext) -> ChatResponse: ...


def _with_reasoning_line(messages: list[Message], level: str) -> list[Message]:
    line = f"Reasoning strength: {level}"
    if messages and messages[0].role == "system":
        first = messages[0]
        return [Message(role="system", text=f"{first.text}\n\n{line}"), *messages[1:]]
    return [Message(role="system", text=line), *messages]


class OpenAICompatibleProvider:
    def __init__(self, endpoint: ResolvedEndpoint, client: httpx.Client | None = None) -> None:
        self.name = endpoint.name
        self.model = endpoint.model
        self._endpoint = endpoint
        self._client = client or make_client(httpx.Timeout(endpoint.config.timeout_s, connect=10))

    def build_body(self, request: ChatRequest) -> dict[str, Any]:
        messages = request.messages
        style = self._endpoint.config.reasoning_style
        if request.reasoning and style is ReasoningStyle.SYSTEM_PROMPT:
            messages = _with_reasoning_line(messages, request.reasoning)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_wire() for m in messages],
            "max_tokens": request.max_tokens,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.reasoning and style is ReasoningStyle.REASONING_EFFORT:
            body["reasoning_effort"] = request.reasoning
        return body

    def chat(self, request: ChatRequest, ctx: CallContext) -> ChatResponse:
        started = time.monotonic()
        response = self._client.post(
            self._endpoint.base_url.rstrip("/") + "/chat/completions",
            json=self.build_body(request),
            headers=auth_headers(self._endpoint.api_key),
        )
        raise_for_status(self._endpoint.config.label, response)
        parsed = parse_completion(self._endpoint.config.label, response.json())
        parsed.endpoint = self.name
        parsed.model = self.model
        parsed.latency_ms = int((time.monotonic() - started) * 1000)
        return parsed


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def parse_completion(service: str, payload: dict[str, Any]) -> ChatResponse:
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ExternalServiceError(
            service, "response has no choices[0].message", status=502
        ) from exc
    usage = payload.get("usage") or {}
    return ChatResponse(
        text=_content_text(message.get("content")),
        reasoning_text=message.get("reasoning_content"),
        usage=Usage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        ),
    )


class MissingFixtureError(LookupError):
    pass


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockProvider:
    """Answers from recorded fixtures in ai/fixtures/<prompt>.json, so everything runs offline.

    A fixture file maps a fixture key to one response, or to a list of responses for
    multi-turn runs (picked by how many assistant turns the request already holds).
    """

    name = "mock"
    model = "mock"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._dir = fixtures_dir or FIXTURES_DIR

    def _load(self, prompt_name: str) -> dict[str, Any]:
        path = self._dir / f"{prompt_name}.json"
        if not path.is_file():
            raise MissingFixtureError(f"no mock fixture for prompt {prompt_name!r} ({path.name})")
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def chat(self, request: ChatRequest, ctx: CallContext) -> ChatResponse:
        fixtures = self._load(ctx.prompt_name)
        entry = fixtures.get(ctx.fixture_key, fixtures.get("default"))
        if entry is None:
            raise MissingFixtureError(f"{ctx.prompt_name}: no {ctx.fixture_key!r} or default")
        if isinstance(entry, list):
            turn = sum(1 for m in request.messages if m.role == "assistant")
            entry = entry[min(turn, len(entry) - 1)]
        text = entry.get("text", "")
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        prompt_text = " ".join(m.text for m in request.messages)
        return ChatResponse(
            text=text,
            usage=Usage(
                input_tokens=estimate_tokens(prompt_text), output_tokens=estimate_tokens(text)
            ),
            endpoint=self.name,
            model=self.model,
        )
