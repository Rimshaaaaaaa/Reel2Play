"""AIClient: the single entry point for model calls.

Picks the endpoint for a role, fails over in order, applies the role's reasoning setting,
validates JSON answers against Pydantic schemas (with one repair round), and records the
tokens and cost of every attempt.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache, partial

from pydantic import BaseModel

from reel2play.ai.config import EndpointConfig, Role, RolesConfig, load_roles, resolve_endpoint
from reel2play.ai.cost import CallRecord, DbRecorder, Recorder, to_pkr, usd_cost
from reel2play.ai.jsonout import JSONOutputError, parse_as, schema_instruction
from reel2play.ai.messages import ChatRequest, ChatResponse, Media, Message, Usage, assistant
from reel2play.ai.messages import system as system_message
from reel2play.ai.messages import user as user_message
from reel2play.ai.prompts import PromptTemplate, load_prompt
from reel2play.ai.providers import (
    CallContext,
    MockProvider,
    OpenAICompatibleProvider,
    Provider,
)
from reel2play.net import with_retries
from reel2play.settings import AIMode, Settings, get_settings


@dataclass(frozen=True)
class Subject:
    """What a call is for: the cost meter groups calls by ad and video; the mock by fixture."""

    ad_id: uuid.UUID | None = None
    video_id: uuid.UUID | None = None
    fixture_key: str = "default"


NO_SUBJECT = Subject()


@dataclass(frozen=True)
class Route:
    endpoint: str
    provider: Provider
    config: EndpointConfig | None


@dataclass
class AIUnavailableError(RuntimeError):
    role: str
    attempts: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        tried = "; ".join(self.attempts) or "no endpoint is configured"
        return f"no model endpoint answered for role {self.role!r}: {tried}"


class AIClient:
    def __init__(
        self,
        roles: RolesConfig,
        routes: dict[Role, list[Route]],
        recorder: Recorder,
        usd_to_pkr: float,
        *,
        attempts_per_endpoint: int = 2,
        json_repairs: int = 1,
        sleep: Callable[[float], None] = time.sleep,
        prompt_loader: Callable[[str], PromptTemplate] = load_prompt,
    ) -> None:
        self._roles = roles
        self.prompt = prompt_loader
        self._routes = routes
        self._recorder = recorder
        self._usd_to_pkr = usd_to_pkr
        self._attempts = attempts_per_endpoint
        self._json_repairs = json_repairs
        self._sleep = sleep

    def request_for(self, role: Role, messages: list[Message]) -> ChatRequest:
        cfg = self._roles.roles[role]
        return ChatRequest(
            messages=messages,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            reasoning=cfg.reasoning,
        )

    def chat(
        self, role: Role, request: ChatRequest, ctx: CallContext, subject: Subject = NO_SUBJECT
    ) -> ChatResponse:
        routes = self._routes.get(role, [])
        failures: list[str] = []
        for route in routes:
            started = time.monotonic()
            try:
                response = with_retries(
                    partial(route.provider.chat, request, ctx),
                    attempts=self._attempts,
                    sleep=self._sleep,
                )
            except Exception as exc:
                latency = int((time.monotonic() - started) * 1000)
                failures.append(f"{route.endpoint}: {exc}")
                self._record(role, route, ctx, subject, Usage(), latency, error=str(exc))
                continue
            self._record(role, route, ctx, subject, response.usage, response.latency_ms)
            return response
        raise AIUnavailableError(role=role.value, attempts=failures)

    def _record(
        self,
        role: Role,
        route: Route,
        ctx: CallContext,
        subject: Subject,
        usage: Usage,
        latency_ms: int,
        error: str | None = None,
    ) -> None:
        usd = usd_cost(route.config, usage, latency_ms)
        self._recorder.record(
            CallRecord(
                role=role.value,
                endpoint=route.endpoint,
                model=route.provider.model,
                prompt_name=ctx.prompt_name,
                usage=usage,
                usd=usd,
                pkr=to_pkr(usd, self._usd_to_pkr),
                latency_ms=latency_ms,
                ok=error is None,
                error=error[:1000] if error else None,
                ad_id=subject.ad_id,
                video_id=subject.video_id,
            )
        )

    def _prompt_messages(
        self,
        prompt_name: str,
        variables: dict[str, object],
        media: Sequence[Media],
        extra_system: str,
    ) -> tuple[Role, list[Message]]:
        prompt = self.prompt(prompt_name)
        system_text, user_text = prompt.render(variables)
        if extra_system:
            system_text = f"{system_text}\n\n{extra_system}"
        return prompt.role, [system_message(system_text), user_message(user_text, list(media))]

    def ask_text(
        self,
        prompt_name: str,
        variables: dict[str, object],
        *,
        media: Sequence[Media] = (),
        subject: Subject = NO_SUBJECT,
    ) -> str:
        role, messages = self._prompt_messages(prompt_name, variables, media, "")
        ctx = CallContext(prompt_name=prompt_name, fixture_key=subject.fixture_key)
        return self.chat(role, self.request_for(role, messages), ctx, subject).text.strip()

    def ask_json[M: BaseModel](
        self,
        prompt_name: str,
        variables: dict[str, object],
        schema: type[M],
        *,
        media: Sequence[Media] = (),
        subject: Subject = NO_SUBJECT,
    ) -> M:
        role, messages = self._prompt_messages(
            prompt_name, variables, media, schema_instruction(schema)
        )
        ctx = CallContext(prompt_name=prompt_name, fixture_key=subject.fixture_key)
        for repair in range(self._json_repairs + 1):
            response = self.chat(role, self.request_for(role, messages), ctx, subject)
            try:
                return parse_as(response.text, schema)
            except JSONOutputError as exc:
                if repair == self._json_repairs:
                    raise
                messages = [
                    *messages,
                    assistant(response.text),
                    user_message(
                        f"That answer could not be used ({exc}). Reply again with the corrected "
                        "JSON object only."
                    ),
                ]
        raise AssertionError("unreachable")  # pragma: no cover


def build_routes(roles: RolesConfig, settings: Settings) -> dict[Role, list[Route]]:
    if settings.ai_mode is AIMode.MOCK:
        mock = MockProvider()
        return {role: [Route("mock", mock, None)] for role in roles.roles}
    providers: dict[str, Route] = {}
    for name, config in roles.endpoints.items():
        endpoint = resolve_endpoint(name, config, settings)
        if endpoint.configured:
            providers[name] = Route(name, OpenAICompatibleProvider(endpoint), config)
    return {
        role: [providers[n] for n in cfg.endpoints if n in providers]
        for role, cfg in roles.roles.items()
    }


def build_ai(settings: Settings, recorder: Recorder | None = None) -> AIClient:
    roles = load_roles()
    return AIClient(
        roles, build_routes(roles, settings), recorder or DbRecorder(), settings.usd_to_pkr
    )


@lru_cache(maxsize=1)
def get_ai() -> AIClient:
    return build_ai(get_settings())
