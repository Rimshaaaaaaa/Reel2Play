"""Template marketplace for designers (feature 49)."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from reel2play.builder.templates import load_templates
from reel2play.marketplace import check_submission
from reel2play.playtest.session import LocalHarness
from reel2play.routes.marketplace import SENDERS
from reel2play.settings import get_settings

SPEC: dict[str, Any] = {
    "id": "kite",
    "name": "Kite",
    "plan": "Later",
    "description": "A synthetic test template: steer a kite carrying the product.",
    "control": "Drag",
    "product_role": "Tied to the kite",
    "ends_when": "The goal, or the time limit",
    "good_for": ["other"],
    "uses_photo": False,
    "params": {"goal": {"easy": 8, "normal": 10, "hard": 12, "min": 5, "max": 14}},
    "designer": "Synthetic Studio",
}
GAME = b"""import { param, startGame, type TemplateGame } from "../../engine/src/index";

export function createKite(): TemplateGame {
  let goal = 10;
  return {
    id: "kite",
    init(ctx) { goal = param(ctx.config.difficulty, "goal"); },
    update() {},
    draw() {},
    pointer() {},
    progress: () => ({ score: 0, goal }),
    outcome: () => "playing",
    debugState: () => ({ goal }),
  };
}
void startGame(createKite);
"""


def spec_bytes(**changes: Any) -> bytes:
    return json.dumps({**SPEC, **changes}).encode()


def test_the_gallery_shows_every_template_with_a_live_demo(client: TestClient) -> None:
    cards = client.get("/api/marketplace/templates").json()
    assert len(cards) == 9
    assert {c["designer"] for c in cards} == {"Reel2Play"}
    catch = next(c for c in cards if c["id"] == "catch")
    assert catch["demo_url"] == "http://testserver/templates/catch/demo"
    page = client.get("/templates/catch/demo")
    assert page.status_code == 200
    assert "sandbox allow-scripts" in page.headers["content-security-policy"]
    assert "Gift parcel (synthetic)" in page.text
    assert client.get("/templates/custom/demo").status_code == 404  # not a public template
    assert client.get("/templates/nope/demo").status_code == 404


@pytest.mark.parametrize("template", ["quiz", "puzzle", "spots"])
def test_demos_load_in_a_browser_without_errors(client: TestClient, template: str) -> None:
    page = client.get(f"/templates/{template}/demo").content
    harness = LocalHarness()
    try:
        opened = harness.call(
            "open", html_b64=base64.b64encode(page).decode(), width=360, height=640
        )
        assert opened["phase"] == "intro"
        assert harness.call("log")["console_errors"] == []
    finally:
        harness.close()


def test_code_checks_a_template_before_any_person_does() -> None:
    existing = set(load_templates(get_settings().templates_dir))
    assert check_submission(spec_bytes(), GAME, existing).problems == []
    taken = check_submission(spec_bytes(id="catch"), GAME, existing)
    assert taken.problems == ["a template called 'catch' already exists"]
    bad_range = check_submission(
        spec_bytes(params={"goal": {"easy": 1, "normal": 10, "hard": 12, "min": 5, "max": 14}}),
        GAME,
        existing,
    )
    assert bad_range.problems[0].startswith("template.json: params.goal")
    assert check_submission(b"{", GAME, existing).problems == ["template.json is not valid JSON"]
    assert (
        "at least one difficulty parameter"
        in check_submission(spec_bytes(params={}), GAME, existing).problems[0]
    )
    for snippet, problem in (
        ('fetch("https://x.example");', "network calls (fetch)"),
        ("localStorage.setItem('a', 'b');", "browser storage"),
        ("eval('1');", "eval"),
        ("new Function('x');", "running text as code"),
        ("window.open('https://x.example');", "leaving the page"),
        ("document.body.innerHTML = 'x';", "writing HTML"),
        ("const w = new Worker('w.js');", "workers"),
    ):
        found = check_submission(spec_bytes(), GAME + snippet.encode(), existing)
        assert any(problem in p for p in found.problems), (snippet, found.problems)
    other_import = b'import { x } from "https://cdn.example/x.js";\n' + GAME
    assert (
        "may import only the shared engine"
        in check_submission(spec_bytes(), other_import, existing).problems[0]
    )
    bare = b"export const nothing = 1;\n"
    assert len(check_submission(spec_bytes(), bare, existing).problems) == 3
    huge = check_submission(spec_bytes(), GAME + b"//" + b"x" * 70_000, existing)
    assert "game.ts is larger than 60 KB" in huge.problems
    assert check_submission(spec_bytes(), b"\xff\xfe", existing).problems == ["game.ts is not text"]


def send(client: TestClient, spec: bytes, game: bytes, **form: str) -> Any:
    data = {"designer_name": "Synthetic Studio", "designer_contact": "studio@example.com",
            "license_confirmed": "true", **form}  # fmt: skip
    return client.post(
        "/api/marketplace/submissions",
        data=data,
        files=[("template_json", ("template.json", spec)), ("game_ts", ("game.ts", game))],
    )


def test_a_designer_submits_and_the_team_reviews(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    SENDERS.clear()
    assert send(client, spec_bytes(), GAME, license_confirmed="false").status_code == 422
    sent = send(client, spec_bytes(), GAME)
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert (body["status"], body["template_id"], body["problems"]) == ("waiting", "kite", [])
    token = body["token"]
    status = client.get(f"/api/marketplace/submissions/{body['id']}", params={"token": token})
    assert status.json()["status"] == "waiting"
    wrong = client.get(f"/api/marketplace/submissions/{body['id']}", params={"token": "nope"})
    assert wrong.status_code == 404
    # The same id cannot be taken twice while waiting.
    twice = send(client, spec_bytes(), GAME).json()
    assert twice["status"] == "checks_failed"
    failed = send(client, spec_bytes(id="balloon"), GAME + b"fetch('x');").json()
    assert failed["status"] == "checks_failed"

    # Review needs the team's key.
    assert client.get("/api/marketplace/review").status_code == 401
    monkeypatch.setattr(get_settings(), "admin_key", SecretStr("team-key"))
    team = {"X-Admin-Key": "team-key"}
    assert client.get("/api/marketplace/review", headers={"X-Admin-Key": "x"}).status_code == 401
    waiting = client.get("/api/marketplace/review", headers=team).json()
    assert [w["template_id"] for w in waiting] == ["kite"]
    code = client.get(f"/api/marketplace/submissions/{body['id']}/files/game.ts", headers=team)
    assert code.headers["content-type"].startswith("text/plain")
    assert "startGame" in code.text
    assert (
        client.get(
            f"/api/marketplace/submissions/{body['id']}/files/x.sh", headers=team
        ).status_code
        == 404
    )
    approved = client.post(
        f"/api/marketplace/submissions/{body['id']}/review",
        json={"decision": "approve", "note": "Lovely kite."},
        headers=team,
    ).json()
    assert (approved["status"], approved["review_note"]) == ("approved", "Lovely kite.")
    again = client.post(
        f"/api/marketplace/submissions/{body['id']}/review",
        json={"decision": "reject"},
        headers=team,
    )
    assert again.status_code == 409
    rejected = client.post(
        f"/api/marketplace/submissions/{failed['id']}/review",
        json={"decision": "approve"},
        headers=team,
    )
    assert rejected.status_code == 409  # code's checks failed: nothing goes to a person

    for _ in range(5):
        send(client, spec_bytes(id="lamp"), GAME)
    assert send(client, spec_bytes(id="lamp"), GAME).status_code == 429
