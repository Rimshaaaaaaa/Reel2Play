"""Call to action works: the WhatsApp link opens with the order text filled in (hosted), or
FbPlayableAd.onCTAClick() is called (Meta export)."""

from urllib.parse import urlparse

from reel2play.gates.base import Evidence, GateResult, result

NAME = "cta_works"


def check(evidence: Evidence) -> GateResult:
    """Measured facts only; the shop's number and the message stay out of the audit log."""
    cta = evidence.cta
    href = urlparse(cta.get("href") or "")
    opened = bool(cta.get("popups"))
    if evidence.brief.cta.kind == "whatsapp":
        to_shop = href.path.strip("/") == evidence.brief.cta.target
        product = str(evidence.config["text"]["productName"])
        written = product in str(cta.get("message", ""))
        passed = href.netloc == "wa.me" and to_shop and written and opened
        problem = "The WhatsApp button does not open a chat with the order written in it."
        ok = "The button opens WhatsApp with the product and coupon already written."
        facts = {"to_shop_number": to_shop, "order_written": written}
    else:
        passed = href.scheme == "https" and opened
        problem = "The button does not open the shop's link."
        ok = "The button opens the shop's link."
        facts = {}
    return result(NAME, passed, ok, problem, opens=href.netloc, opened=opened, **facts)
