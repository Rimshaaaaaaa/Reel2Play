"""No errors: no console errors or uncaught exceptions during any run."""

from reel2play.gates.base import Evidence, GateResult, result

NAME = "no_errors"


def check(evidence: Evidence) -> GateResult:
    errors = list(evidence.log.get("console_errors", []))
    return result(
        NAME,
        not errors,
        "No errors appeared while the game ran.",
        f"{len(errors)} error(s) appeared while the game ran.",
        errors=errors[:10],
    )
