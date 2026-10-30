"""Custom mechanics (feature 24): the director writes a small script for a new mechanic; code
checks it, the play-tester plays it in the sandbox, and only then is it published."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play.ai.providers import FIXTURES_DIR
from reel2play.builder.mechanic import MechanicRejectedError, check_script, mechanic_head
from reel2play.models import AdStatus, Build, Export, ExportKind, Video
from reel2play.pipeline import build as build_step
from reel2play.routes.game_page import PAGES
from tests.helpers import OWNER_FIELDS, ad_for, drain, trail

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = (ROOT / "templates/custom/example-mechanic.txt").read_text(encoding="utf-8")
REST = "function update(s, api, dt) {} function draw(s, api) {}"
HOOKS = "function setup(api) { return {}; } " + REST


def test_the_example_mechanic_passes_and_the_mock_director_writes_it() -> None:
    assert check_script(EXAMPLE) == []
    fixture = json.loads((FIXTURES_DIR / "director_mechanic.json").read_text(encoding="utf-8"))
    assert fixture["default"]["text"]["mechanic"] == EXAMPLE
    assert "Synthetic" in fixture["_note"]
    head = mechanic_head(EXAMPLE)
    assert head.startswith('<script>Object.defineProperty(Function.prototype, "constructor"')
    assert '"use strict";' in head
    assert head.endswith("})();</script>")
    assert head.count("</script>") == 1


@pytest.mark.parametrize(
    ("script", "problem"),
    [
        ("function setup(api) { return window.location; }", "'window' is not available"),
        ("function setup(api) { fetch('https://x.example'); }", "'fetch' is not available"),
        ("function setup(api) { return document.cookie; }", "'document' is not available"),
        ("function setup(api) { return globalThis; }", "'globalThis' is not available"),
        ("function setup(api) { return api.circle.constructor('x'); }", "'constructor'"),
        ("function setup(api) { return api['construc' + 'tor']; }", "'constructor'"),
        ("function setup(api) { const k = `__proto__`; return api[k]; }", "'__proto__'"),
        ("function setup(api) { return this; }", "ThisExpression is not allowed"),
        ("function setup(api) { return new Image(); }", "NewExpression is not allowed"),
        ("function setup(api) { return '</script><b>'; }", "contains '</'"),
        ("function setup(api) { return /a+/.test('a'); }", "regular expressions"),
        ("async function setup(api) {}", "generators and async functions"),
        ("function* setup(api) {}", "generators and async functions"),
        ("class Game {} function setup(api) {}", "ClassDeclaration is not allowed"),
        ("function setup(api) { try { x(); } catch (e) {} }", "TryStatement is not allowed"),
        ("function setup(api) { delete api.score; }", "delete is not allowed"),
        ("function setup({ score }) {}", "parameters must be plain names"),
        ("function setup(api) { const { a } = api; }", "variables must be plain names"),
        ("const r = api.rng(); function setup(api) {}", "top-level values must be plain"),
        ("api.win(); function setup(api) {}", "only functions and constants"),
        ("function setup(api) { for (const k in api) {} }", "ForInStatement is not allowed"),
        ("function setup(api) { return api.__lookupGetter__; }", "'__lookup"),
        ("function setup(api) {", "does not parse"),
        ("   ", "the script is empty"),
    ],
)
def test_scripts_that_could_reach_the_page_are_refused(script: str, problem: str) -> None:
    problems = check_script(script if not script.strip() else f"{script}\n{REST}")
    assert any(problem in p for p in problems), problems


def test_a_mechanic_needs_its_three_functions_and_a_sane_size() -> None:
    assert check_script("function setup(api) { return {}; }") == [
        "the script must define function update",
        "the script must define function draw",
    ]
    huge = HOOKS + "\nconst PAD = '" + "x" * 6000 + "';"
    assert "longer than 6000 characters" in check_script(huge)[0]
    with pytest.raises(MechanicRejectedError) as refused:
        mechanic_head("function setup() { return window; }")
    assert "window" in str(refused.value)


def lab_upload(client: TestClient, video: Path) -> uuid.UUID:
    data = {
        "shop_name": "Synthetic Shoes",
        "rights_confirmed": "true",
        "lab": "true",
        **OWNER_FIELDS,
    }
    response = client.post(
        "/api/uploads", data=data, files=[("files", (video.name, video.read_bytes()))]
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def test_an_experimental_game_is_checked_tested_and_published(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = lab_upload(client, sample_media["product_video"])
    assert session.get(Video, video_id).lab is True  # type: ignore[union-attr]
    drain()
    ad = ad_for(session, video_id)
    actions = trail(session, ad)
    assert ad.status == AdStatus.PUBLISHED, (ad.error, actions[-5:])
    assert ad.template == "custom", actions
    assert "mechanic.checked" in actions
    assert "test.passed" in actions
    assert "publish.meta_skipped" in actions
    build = session.scalars(select(Build).where(Build.ad_id == ad.id)).first()
    assert build is not None
    assert build.config["content"]["mechanic"] == EXAMPLE
    kinds = {e.kind for e in session.scalars(select(Export).where(Export.ad_id == ad.id))}
    assert ExportKind.META_HTML not in kinds
    assert ExportKind.POSTER in kinds
    PAGES.clear()
    page = client.get(f"/g/{ad.slug}")
    assert "window.__r2pMechanic" in page.text
    policy = page.headers["content-security-policy"]
    assert "unsafe-eval" not in policy
    assert "sandbox allow-scripts" in policy


def test_a_script_that_may_not_run_falls_back_to_the_templates(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    stop_after_build: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_step, "check_script", lambda _: ["'window' is not available"])
    video_id = lab_upload(client, sample_media["product_video"])
    drain()
    ad = ad_for(session, video_id)
    actions = trail(session, ad)
    assert "mechanic.refused" in actions
    assert ad.template != "custom"
