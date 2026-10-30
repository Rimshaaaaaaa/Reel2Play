"""Shared test helpers: scripted providers, uploads, and real compiled games."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.ai.client import AIClient, Route
from reel2play.ai.config import Role, load_roles
from reel2play.ai.cost import MemoryRecorder
from reel2play.ai.messages import ChatRequest, ChatResponse
from reel2play.ai.prompts import PromptTemplate, parse_prompt
from reel2play.ai.providers import CallContext
from reel2play.models import Ad, TestRun

PROMPT = """---
role: director
version: 3
---
[system]
You direct games for $shop.
[user]
Look at the video of $product.
"""


def loader(name: str) -> PromptTemplate:
    return parse_prompt(name, PROMPT)


class Scripted:
    """A provider that replays responses or raises errors, in order."""

    def __init__(self, name: str, outcomes: list[ChatResponse | Exception]) -> None:
        self.name = name
        self.model = f"{name}-model"
        self.outcomes = outcomes
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest, ctx: CallContext) -> ChatResponse:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        outcome.endpoint = self.name
        outcome.model = self.model
        return outcome


def make_client(
    *providers: Scripted,
    recorder: MemoryRecorder | None = None,
    prompt_loader: Callable[[str], PromptTemplate] = loader,
) -> AIClient:
    roles = load_roles()
    configs = {p.name: roles.endpoints.get(p.name) for p in providers}
    routes = {role: [Route(p.name, p, configs[p.name]) for p in providers] for role in Role}
    return AIClient(
        roles,
        routes,
        recorder or MemoryRecorder(),
        usd_to_pkr=280,
        sleep=lambda _: None,
        prompt_loader=prompt_loader,
    )


# --- uploads and the pipeline -------------------------------------------------------------


def upload(client: TestClient, path: Path, **fields: str) -> uuid.UUID:
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **fields}
    response = client.post(
        "/api/uploads", data=data, files=[("files", (path.name, path.read_bytes()))]
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def ad_for(session: Session, video_id: uuid.UUID) -> Ad:
    session.expire_all()
    return session.scalars(select(Ad).where(Ad.video_id == video_id)).one()


def trail(session: Session, ad: Ad) -> list[str]:
    return [e.action for e in audit.entries_for(session, "ad", ad.id)]


OWNER_FIELDS = {"price": "Rs 3,200", "offer": "20% off", "whatsapp_number": "923001234567"}


def drain() -> int:
    """Run every queued job, pipeline steps included, until the queue is empty."""
    from reel2play.jobs.queue import run_due

    return run_due("test", max_jobs=200, time_budget_s=1200)


def runs_for(session: Session, ad: Ad) -> list[TestRun]:
    return list(
        session.scalars(select(TestRun).where(TestRun.ad_id == ad.id).order_by(TestRun.round))
    )


# --- games for play-test tests -------------------------------------------------------------


def game_html(
    template: str = "catch", seed: int = 3, platform: str = "hosted", **text_changes: str
) -> bytes:
    """A real compiled game from the synthetic fixtures."""
    from reel2play.analysis import CreativeBrief
    from reel2play.builder.assets import photo_data_url, sprite_data_url
    from reel2play.builder.html import compile_game
    from reel2play.builder.proposal import AssetInputs, GameProposal, assemble
    from reel2play.builder.templates import load_templates
    from reel2play.settings import get_settings

    fixtures = Path(__file__).resolve().parents[2] / "fixtures/synthetic"
    settings = get_settings()
    brief = CreativeBrief.model_validate(
        {
            "product": {
                "name": "Sneaker",
                "category": "shoes",
                "description": "",
                "segment_prompt": "shoe",
            },
            "palette": ["#c8243a", "#f2b705"],
            "mood": "bright",
            "audience": "all",
            "tone_of_voice": "friendly",
            "language": "en",
            "price": "Rs 2,499",
            "offer_text": "20% off",
            "offer_source": "owner",
            "cod_available": False,
            "free_delivery": False,
            "seen_price": None,
            "cta": {"kind": "whatsapp", "target": "923001234567"},
            "key_frames": [{"index": 0, "time_s": 0, "key": "k", "reason": "r"}],
        }
    )
    proposal = GameProposal.model_validate(
        {
            "template": template,
            "reason": "test",
            "title": "Play!",
            "instruction": "Tap.",
            "win_text": "You won!",
            "lose_text": "So close!",
            "cta_label": "Order",
            "product_label": "Sneaker",
            "offer_line": "20% off",
            **text_changes,
        }
    )
    assets = AssetInputs(
        product=sprite_data_url((fixtures / "synthetic-sprite.png").read_bytes()),
        product_photo=photo_data_url((fixtures / "synthetic-photo.jpg").read_bytes(), None),
        logo=None,
    )
    config = assemble(
        ad_id=uuid.uuid4(),
        shop_name="Synthetic Shoes",
        brief=brief,
        proposal=proposal,
        templates=load_templates(settings.templates_dir),
        assets=assets,
        seed=seed,
    ).config.model_copy(update={"platform": platform})
    return compile_game(config, settings.engine_dist_dir, settings.max_game_bytes).html
