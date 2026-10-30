"""Honest claims: prices come only from the owner, offers keep the owner's numbers, and the
game's own words claim nothing a small shop cannot prove (feature 31). Claims in the owner's
own offer are the owner's to make; the report points them out instead (pipeline/report.py).
"""

from reel2play.claims import MONEY, only_owner_numbers, unprovable_in
from reel2play.gates.base import Evidence, GateResult

NAME = "honest_claims"
SCANNED = ("title", "instruction", "win", "lose", "ctaLabel", "productName")


def owner_words(evidence: Evidence) -> str:
    """What the owner wrote; a claim they made themselves is theirs to make."""
    return " ".join(w for w in (evidence.brief.offer_text,) if w).casefold()


def check(evidence: Evidence) -> GateResult:
    text = evidence.config["text"]
    brief = evidence.brief
    problems: list[str] = []
    if text.get("price") != brief.price:
        problems.append("the game's price is not the owner's price")
    offer = text.get("offer")
    if offer and not only_owner_numbers(offer, brief.offer_text):
        problems.append("the offer has numbers the owner did not give")
    for key in SCANNED:
        words = str(text.get(key, ""))
        if MONEY.search(words):
            problems.append(f"the {key} mentions a price")
        claims = [c for c in unprovable_in(words) if c.casefold() not in owner_words(evidence)]
        if claims:
            problems.append(f"the {key} claims {', '.join(repr(c) for c in claims)}")
    # The critic may see a claim code missed; code keeps it only if it is really in the game.
    seen = " ".join(str(text.get(key, "")) for key in SCANNED).casefold()
    for claim in evidence.critic.claims if evidence.critic else []:
        quoted = claim.strip().casefold()
        if quoted and quoted in seen and quoted not in owner_words(evidence):
            problems.append(f"the game claims {claim.strip()!r}")
    if problems:
        return GateResult(
            NAME, False, "Claims need fixing: " + "; ".join(problems) + ".", {"problems": problems}
        )
    return GateResult(
        NAME,
        True,
        "Prices and offers come only from the shop owner, and the game claims nothing it "
        "cannot prove.",
        {},
    )
