"""Model check: ask every role's endpoint chain for a one-word answer.

Used by /internal/model-check and `reel2play model-check` to verify keys and failover.
"""

from __future__ import annotations

from pydantic import BaseModel

from reel2play.ai.client import AIClient, AIUnavailableError, Subject
from reel2play.ai.config import Role
from reel2play.ai.messages import system, user
from reel2play.ai.providers import CallContext


class RoleCheck(BaseModel):
    role: str
    ok: bool
    endpoint: str | None = None
    model: str | None = None
    answer: str | None = None
    error: str | None = None


def check_roles(ai: AIClient) -> list[RoleCheck]:
    results: list[RoleCheck] = []
    for role in Role:
        request = ai.request_for(
            role, [system("You are a health check."), user("Reply with the single word: ready")]
        )
        request.max_tokens = 64
        try:
            answer = ai.chat(role, request, CallContext(prompt_name="model_check"), Subject())
        except AIUnavailableError as exc:
            results.append(RoleCheck(role=role.value, ok=False, error=str(exc)))
            continue
        results.append(
            RoleCheck(
                role=role.value,
                ok=True,
                endpoint=answer.endpoint,
                model=answer.model,
                answer=answer.text[:40],
            )
        )
    return results
