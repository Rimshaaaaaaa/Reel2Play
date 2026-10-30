"""Provider-neutral chat messages, converted to the OpenAI-compatible wire format."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


# Content-part names per media kind. Images and audio follow Baseten's documented
# `image_url` / `audio_url` parts; video uses the matching `video_url` part.
_PART_TYPE = {
    MediaKind.IMAGE: "image_url",
    MediaKind.VIDEO: "video_url",
    MediaKind.AUDIO: "audio_url",
}


@dataclass(frozen=True)
class Media:
    kind: MediaKind
    url: str  # https link or data: URL

    def to_wire(self) -> dict[str, Any]:
        part = _PART_TYPE[self.kind]
        return {"type": part, part: {"url": self.url}}


@dataclass
class Message:
    role: str  # system | user | assistant
    text: str = ""
    media: list[Media] = field(default_factory=list)

    def to_wire(self) -> dict[str, Any]:
        wire: dict[str, Any] = {"role": self.role}
        if self.media:
            parts: list[dict[str, Any]] = [{"type": "text", "text": self.text}] if self.text else []
            parts.extend(m.to_wire() for m in self.media)
            wire["content"] = parts
        else:
            wire["content"] = self.text
        return wire


def system(text: str) -> Message:
    return Message(role="system", text=text)


def user(text: str, media: list[Media] | None = None) -> Message:
    return Message(role="user", text=text, media=list(media or []))


def assistant(text: str) -> Message:
    return Message(role="assistant", text=text)


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ChatRequest:
    messages: list[Message]
    max_tokens: int = 2048
    temperature: float | None = None
    reasoning: str | None = None  # low | medium | high | xhigh


@dataclass
class ChatResponse:
    text: str
    reasoning_text: str | None = None
    usage: Usage = field(default_factory=Usage)
    endpoint: str = ""
    model: str = ""
    latency_ms: int = 0
