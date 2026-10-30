"""The 13 quality gates. A game reaches customers only when every one passes."""

from collections.abc import Callable

from reel2play.gates import (
    can_be_won,
    cta_works,
    finish_time,
    fits_screen,
    honest_claims,
    loads_fast,
    looks_like_product,
    no_errors,
    no_network,
    offer_shown,
    readable_text,
    rights,
    size,
)
from reel2play.gates.base import Evidence, GateResult

GATES: tuple[tuple[str, Callable[[Evidence], GateResult]], ...] = tuple(
    (module.NAME, module.check)
    for module in (
        loads_fast,
        size,
        no_network,
        can_be_won,
        finish_time,
        offer_shown,
        cta_works,
        no_errors,
        fits_screen,
        looks_like_product,
        readable_text,
        honest_claims,
        rights,
    )
)


def run_gates(evidence: Evidence) -> list[GateResult]:
    return [check(evidence) for _, check in GATES]
