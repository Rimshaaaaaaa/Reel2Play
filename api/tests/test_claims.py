"""Claim check (feature 31): the game never claims what a small shop cannot prove; the
owner's own claims and a missing price are pointed out in the report."""

from __future__ import annotations

import pytest

from reel2play.claims import unprovable_in
from reel2play.gates import honest_claims
from reel2play.gates.base import CriticReview
from reel2play.pipeline.report import claim_warnings
from reel2play.publish.captions import CaptionDraft, honest
from tests.test_gates import BRIEF, evidence


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Best shoes in Pakistan", ["Best shoes in Pakistan"]),
        ("The best cake in Lahore!", ["best cake in Lahore"]),
        ("Best quality and best prices", ["Best quality", "best prices"]),
        ("No.1 bakery", ["No.1"]),
        ("Number one choice", ["Number one"]),
        ("100% original leather", ["100% original"]),
        ("Guaranteed fresh", ["Guaranteed"]),
        ("Cures dry skin", ["Cures"]),
        ("Pakistan's first", ["Pakistan's first"]),
        ("sab se sasta", ["sab se sasta"]),
        ("سب سے بہترین جوتے", ["سب سے بہترین"]),
        ("Catch the best deal", []),
        ("Best wishes", []),
        ("بہترین آفر", []),
        ("Fresh every morning", []),
        (None, []),
    ],
)
def test_unprovable_claims_are_found(text: str | None, found: list[str]) -> None:
    assert unprovable_in(text) == found


def config_with(**text: str) -> dict[str, object]:
    base = evidence().config
    return {**base, "text": {**base["text"], **text}}


def test_the_games_own_words_may_not_make_claims() -> None:
    result = honest_claims.check(evidence(config=config_with(title="Best shoes in Pakistan")))
    assert not result.passed
    assert "the title claims 'Best shoes in Pakistan'" in result.measured["problems"]
    assert honest_claims.check(evidence()).passed
    assert "claims nothing it cannot prove" in honest_claims.check(evidence()).message


def test_the_owners_own_claim_is_theirs_to_make() -> None:
    owner = BRIEF.model_copy(update={"offer_text": "No.1 shop, 20% off"})
    shown = evidence(brief=owner, config=config_with(win="No.1 shop says thanks"))
    assert honest_claims.check(shown).passed


def test_the_critic_can_point_at_a_claim_code_missed() -> None:
    critic = CriticReview(
        product_matches=True,
        offer_visible=True,
        price_matches=True,
        text_readable=True,
        language_ok=True,
        claims=["Unbeatable", "Loved by everyone"],
    )
    found = honest_claims.check(evidence(critic=critic, config=config_with(title="Unbeatable!")))
    assert found.measured["problems"] == ["the game claims 'Unbeatable'"]  # quoted, and present


def test_the_report_points_out_the_owners_claims_and_a_missing_price() -> None:
    owner = BRIEF.model_copy(update={"offer_text": "Best price in town, guaranteed", "price": None})
    warnings = claim_warnings(owner)
    assert len(warnings) == 2
    assert warnings[0].startswith("Your offer says “Best price in town”, “guaranteed”.")
    assert warnings[1].startswith("No price is shown")
    urdu = claim_warnings(owner.model_copy(update={"language": "ur"}))
    assert urdu[1].startswith("گیم میں قیمت نہیں")
    assert claim_warnings(BRIEF) == []


def test_captions_with_claims_fall_back_to_code() -> None:
    draft = CaptionDraft(
        instagram="The best sneakers in Pakistan!",
        facebook="Play and win",
        whatsapp_status="Play",
        hashtags=["sneakers"],
    )
    assert not honest(draft, ["Rs 2,499", "20% off"])
    owners = ["Best sneakers in Pakistan, 20% off"]
    assert honest(draft.model_copy(update={"instagram": "Best sneakers in Pakistan"}), owners)
