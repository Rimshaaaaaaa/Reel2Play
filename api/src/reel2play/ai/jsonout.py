"""JSON answers from models that have no JSON mode: find the object, validate it with Pydantic."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError


class JSONOutputError(ValueError):
    """The model's answer was not a valid object for the expected schema."""


def schema_instruction(schema: type[BaseModel]) -> str:
    body = json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
    return (
        "Answer with exactly one JSON object and nothing else: no prose, no code fence. "
        f"It must match this JSON Schema:\n{body}"
    )


def extract_json_object(text: str) -> dict[str, Any]:
    """Return the first complete top-level JSON object in ``text``."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(value, dict):
                        return value
                    break
        start = text.find("{", start + 1)
    raise JSONOutputError("no JSON object found in the answer")


def parse_as[M: BaseModel](text: str, schema: type[M]) -> M:
    try:
        return schema.model_validate(extract_json_object(text))
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()[:8]
        )
        raise JSONOutputError(problems) from exc
