"""Agent loop for tool-using roles (the play-tester), with actions as JSON in plain text.

Each turn the model looks at the latest observation and answers with a JSON object of up to
four actions from the tool registry. Plain-text JSON works on every OpenAI-compatible server
(Glimmer under vLLM included), unlike provider-specific tool-call formats. The caller says
when the episode is over; the model then gives a verdict, also as validated JSON.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from reel2play.ai.client import NO_SUBJECT, AIClient, Subject
from reel2play.ai.config import Role
from reel2play.ai.jsonout import JSONOutputError, parse_as, schema_instruction
from reel2play.ai.messages import Media, Message, assistant, user
from reel2play.ai.providers import CallContext
from reel2play.ai.tools import ToolRegistry

KEEP_IMAGES = 3
MAX_ACTIONS = 4


class AgentAction(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class AgentTurn(BaseModel):
    thought: str = Field(default="", max_length=400)
    actions: list[AgentAction] = Field(default_factory=list, max_length=MAX_ACTIONS)


@dataclass(frozen=True)
class Observation:
    text: str
    image: Media | None = None


@dataclass(frozen=True)
class AgentStep:
    turn: int
    tool: str
    args: dict[str, Any]
    result: str
    thought: str = ""


@dataclass
class AgentRun[M: BaseModel]:
    verdict: M
    steps: list[AgentStep] = field(default_factory=list)
    turns: int = 0
    finished: bool = False
    endpoints: set[str] = field(default_factory=set)


def trim_images(messages: list[Message], keep: int = KEEP_IMAGES) -> list[Message]:
    """Keep only the latest screenshots in context; older ones become a short note."""
    seen = 0
    trimmed: list[Message] = []
    for message in reversed(messages):
        if message.media and message.role == "user" and seen >= keep:
            note = f"{message.text} [earlier screenshot removed]"
            trimmed.append(Message(role="user", text=note))
            continue
        if message.media:
            seen += 1
        trimmed.append(message)
    return list(reversed(trimmed))


def tools_instruction(tools: ToolRegistry) -> str:
    listing = "\n".join(
        f"- {spec['function']['name']}: {spec['function']['description']} "
        f"Arguments (JSON Schema): {json.dumps(spec['function']['parameters'])}"
        for spec in tools.specs()
    )
    shape = '{"thought": "<one short sentence>", "actions": [{"tool": "<name>", "args": {...}}]}'
    return (
        f"Tools:\n{listing}\n\nEach turn, answer with one JSON object and nothing else: "
        f"{shape} with 1 to {MAX_ACTIONS} actions, done in order."
    )


def _observe(observation: Observation, prefix: str) -> Message:
    media = [observation.image] if observation.image else []
    return user(f"{prefix}\n{observation.text}".strip(), media)


def _ask[M: BaseModel](
    client: AIClient,
    role: Role,
    messages: list[Message],
    schema: type[M],
    ctx: CallContext,
    subject: Subject,
    repairs: int = 1,
) -> tuple[M, str, str]:
    for attempt in range(repairs + 1):
        request = client.request_for(role, trim_images(messages))
        response = client.chat(role, request, ctx, subject)
        try:
            return parse_as(response.text, schema), response.text, response.endpoint
        except JSONOutputError as exc:
            if attempt == repairs:
                raise
            messages.append(assistant(response.text))
            messages.append(
                user(f"That answer could not be used ({exc}). Reply with the JSON object only.")
            )
    raise AssertionError("unreachable")  # pragma: no cover


def run_agent[M: BaseModel](
    client: AIClient,
    prompt_name: str,
    variables: dict[str, object],
    tools: ToolRegistry,
    verdict: type[M],
    *,
    observe: Callable[[], Observation],
    finished: Callable[[], bool],
    media: Sequence[Media] = (),
    subject: Subject = NO_SUBJECT,
    max_turns: int = 40,
) -> AgentRun[M]:
    prompt = client.prompt(prompt_name)
    system_text, user_text = prompt.render(variables)
    messages: list[Message] = [
        Message(role="system", text=f"{system_text}\n\n{tools_instruction(tools)}"),
        user(user_text, list(media)),
        _observe(observe(), "The game now:"),
    ]
    ctx = CallContext(prompt_name=prompt_name, fixture_key=subject.fixture_key)
    steps: list[AgentStep] = []
    endpoints: set[str] = set()
    turns = 0
    while turns < max_turns and not finished():
        turns += 1
        turn, raw, endpoint = _ask(client, prompt.role, messages, AgentTurn, ctx, subject)
        endpoints.add(endpoint)
        results = []
        for action in turn.actions:
            output = tools.call(action.tool, json.dumps(action.args))
            steps.append(AgentStep(turns, action.tool, action.args, output.text, turn.thought))
            results.append(f"{action.tool}: {output.text}")
            if finished():
                break
        messages.append(assistant(raw))
        messages.append(_observe(observe(), "Results: " + "; ".join(results or ["no actions"])))
    messages.append(user(f"The run is over. Judge it. {schema_instruction(verdict)}"))
    final_ctx = CallContext(prompt_name=f"{prompt_name}_verdict", fixture_key=subject.fixture_key)
    judged, _, endpoint = _ask(client, prompt.role, messages, verdict, final_ctx, subject)
    endpoints.add(endpoint)
    done = finished()
    return AgentRun(judged, steps=steps, turns=turns, finished=done, endpoints=endpoints)
