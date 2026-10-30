"""No network: no requests after load and no JavaScript redirects."""

from reel2play.gates.base import Evidence, GateResult, result

NAME = "no_network"


def check(evidence: Evidence) -> GateResult:
    requests = list(evidence.log.get("requests", []))
    redirects = list(evidence.log.get("navigations", []))
    passed = not requests and not redirects
    return result(
        NAME,
        passed,
        "The game made no network requests and no redirects.",
        f"The game tried {len(requests)} request(s) and {len(redirects)} redirect(s).",
        requests=requests[:10],
        redirects=redirects[:10],
    )
