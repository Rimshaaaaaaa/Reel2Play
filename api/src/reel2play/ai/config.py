"""Role and endpoint configuration, loaded from roles.toml and resolved against settings."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr

from reel2play.settings import Settings

ROLES_FILE = Path(__file__).with_name("roles.toml")


class Role(StrEnum):
    DIRECTOR = "director"
    CRITIC = "critic"
    TESTER = "tester"
    CAPTIONS = "captions"


class ReasoningStyle(StrEnum):
    REASONING_EFFORT = "reasoning_effort"  # top-level request field
    SYSTEM_PROMPT = "system_prompt"  # "Reasoning strength: <level>" line in the system prompt


class EndpointConfig(BaseModel):
    label: str
    base_url_setting: str
    api_key_setting: str
    model_setting: str
    reasoning_style: ReasoningStyle
    timeout_s: float = 120
    usd_per_m_input: Decimal = Decimal(0)
    usd_per_m_output: Decimal = Decimal(0)
    usd_per_second: Decimal = Decimal(0)


class RoleConfig(BaseModel):
    description: str
    endpoints: list[str] = Field(min_length=1)
    reasoning: str = "medium"
    max_tokens: int = 2048
    temperature: float | None = None


class RolesConfig(BaseModel):
    endpoints: dict[str, EndpointConfig]
    roles: dict[Role, RoleConfig]

    def check(self) -> RolesConfig:
        for role, cfg in self.roles.items():
            unknown = [name for name in cfg.endpoints if name not in self.endpoints]
            if unknown:
                raise ValueError(f"role {role} uses unknown endpoints {unknown}")
        missing = [role for role in Role if role not in self.roles]
        if missing:
            raise ValueError(f"roles.toml has no config for {missing}")
        return self


@lru_cache(maxsize=4)
def load_roles(path: Path = ROLES_FILE) -> RolesConfig:
    with path.open("rb") as handle:
        return RolesConfig.model_validate(tomllib.load(handle)).check()


@dataclass(frozen=True)
class ResolvedEndpoint:
    name: str
    config: EndpointConfig
    base_url: str
    api_key: str
    model: str

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


def resolve_endpoint(name: str, config: EndpointConfig, settings: Settings) -> ResolvedEndpoint:
    def setting(attr: str) -> str:
        value = getattr(settings, attr)
        return value.get_secret_value() if isinstance(value, SecretStr) else str(value)

    return ResolvedEndpoint(
        name=name,
        config=config,
        base_url=setting(config.base_url_setting),
        api_key=setting(config.api_key_setting),
        model=setting(config.model_setting),
    )
