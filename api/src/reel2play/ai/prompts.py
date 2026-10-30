"""Prompt files under version control: ai/prompts/<name>.md.

Format: a front-matter block (role, version), then a ``[system]`` section and a ``[user]``
section. ``$name`` placeholders are filled with string.Template; a missing value is an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

from reel2play.ai.config import Role

PROMPTS_DIR = Path(__file__).with_name("prompts")
_FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_SECTION = re.compile(r"^\[(system|user)\]\s*$", re.MULTILINE)


class PromptError(ValueError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    role: Role
    version: int
    system: str
    user: str

    def render(self, variables: dict[str, object]) -> tuple[str, str]:
        values = {key: str(value) for key, value in variables.items()}
        try:
            return (
                Template(self.system).substitute(values),
                Template(self.user).substitute(values),
            )
        except KeyError as exc:
            raise PromptError(f"prompt {self.name!r} needs variable {exc.args[0]!r}") from exc


def parse_prompt(name: str, source: str) -> PromptTemplate:
    match = _FRONT_MATTER.match(source)
    if not match:
        raise PromptError(f"prompt {name!r} has no front matter")
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    body = source[match.end() :]
    parts = _SECTION.split(body)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    if "system" not in sections or "user" not in sections:
        raise PromptError(f"prompt {name!r} needs [system] and [user] sections")
    return PromptTemplate(
        name=name,
        role=Role(meta["role"]),
        version=int(meta.get("version", 1)),
        system=sections["system"],
        user=sections["user"],
    )


@lru_cache(maxsize=64)
def load_prompt(name: str, directory: Path = PROMPTS_DIR) -> PromptTemplate:
    path = directory / f"{name}.md"
    if not path.is_file():
        raise PromptError(f"no prompt file {path.name}")
    return parse_prompt(name, path.read_text(encoding="utf-8"))


def available_prompts(directory: Path = PROMPTS_DIR) -> list[str]:
    return sorted(p.stem for p in directory.glob("*.md"))
