"""Looks like the product: Spark Open compares the game's sprite with the key frame."""

from reel2play.gates.base import Evidence, GateResult

NAME = "looks_like_product"


def check(evidence: Evidence) -> GateResult:
    critic = evidence.critic
    if critic is None:
        return GateResult(
            NAME, False, "The product check could not run.", {}, evidence.gameplay_key
        )
    message = (
        "The product in the game looks like your real product."
        if critic.product_matches
        else f"The product in the game does not look right: {critic.product_notes}"
    )
    return GateResult(
        NAME,
        critic.product_matches,
        message,
        {"notes": critic.product_notes},
        evidence.gameplay_key,
    )
