"""Offer shown: the end card shows the offer and exactly the price the owner entered.

Checked in the page's text first, then by Spark Open on the end-card screenshot.
"""

from reel2play.gates.base import Evidence, GateResult

NAME = "offer_shown"


def check(evidence: Evidence) -> GateResult:
    screen = evidence.screens["phone"]
    parts = screen.end_card.get("parts", {})
    brief = evidence.brief
    problems: list[str] = []
    if not screen.end_card.get("visible"):
        problems.append("the end card did not appear")
    if brief.offer_text and not parts.get("offer", {}).get("visible"):
        problems.append("the offer is not on the end card")
    if brief.price is not None:
        shown = parts.get("price", {}).get("text")
        if shown != brief.price:
            problems.append(f"the price shows as {shown!r}, not {brief.price!r}")
    critic = evidence.critic
    if critic is not None:
        if brief.offer_text and not critic.offer_visible:
            problems.append("the critic could not read the offer on screen")
        if brief.price is not None and not critic.price_matches:
            problems.append(f"the critic read the price as {critic.price_seen!r}")
    measured = {
        "offer": brief.offer_text,
        "price": brief.price,
        "page_price": parts.get("price", {}).get("text"),
        "critic_price": critic.price_seen if critic else None,
    }
    if problems:
        return GateResult(
            NAME,
            False,
            "On the end card, " + "; ".join(problems) + ".",
            measured,
            screen.screenshot_key,
        )
    return GateResult(
        NAME,
        True,
        "The end card shows the offer and your exact price.",
        measured,
        screen.screenshot_key,
    )
