"""The shop's test report (feature 30): plain words, with the screenshots behind each check."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from reel2play.analysis import LANGUAGE_NAMES, CreativeBrief
from reel2play.claims import unprovable_in
from reel2play.models import Fix, TestRun
from reel2play.pipeline.runner import StepContext
from reel2play.pipeline.state import latest_brief
from reel2play.safety import as_data

# Each gate in the shop's own words (the report never says "gate").
GATE_LABELS: dict[str, dict[str, str]] = {
    "loads_fast": {"en": "Opens quickly", "ur": "جلدی کھلتی ہے"},
    "size": {"en": "Small file", "ur": "چھوٹی فائل"},
    "no_network": {"en": "Works without internet calls", "ur": "انٹرنیٹ کالز کے بغیر چلتی ہے"},
    "can_be_won": {"en": "Can be won", "ur": "جیتی جا سکتی ہے"},
    "finish_time": {"en": "Takes 15 to 30 seconds", "ur": "15 سے 30 سیکنڈ کی ہے"},
    "offer_shown": {"en": "Shows your offer and price", "ur": "آپ کی آفر اور قیمت دکھاتی ہے"},
    "cta_works": {"en": "Order button works", "ur": "آرڈر کا بٹن کام کرتا ہے"},
    "no_errors": {"en": "No errors", "ur": "کوئی خرابی نہیں"},
    "fits_screen": {"en": "Fits small and large screens", "ur": "چھوٹی اور بڑی اسکرین پر پوری"},
    "looks_like_product": {"en": "Looks like your product", "ur": "آپ کی پراڈکٹ جیسی دکھتی ہے"},
    "readable_text": {"en": "Easy to read", "ur": "پڑھنے میں آسان"},
    "honest_claims": {"en": "Only your prices and offers", "ur": "صرف آپ کی قیمتیں اور آفرز"},
    "rights": {"en": "Your video, without its sound", "ur": "آپ کی ویڈیو، آواز کے بغیر"},
}


class ShopReport(BaseModel):
    summary: str = Field(min_length=1, max_length=600)
    next_step: str = Field(min_length=1, max_length=240)


def fix_count(ctx: StepContext) -> int:
    count = ctx.session.scalar(select(func.count(Fix.id)).where(Fix.ad_id == ctx.ad.id))
    return int(count or 0)


WARNINGS = {
    "claim": {
        "en": "Your offer says {claims}. Ads that claim what a shop cannot prove can be "
        "rejected or lose trust; say what makes your product special instead.",
        "ur": "آپ کی آفر میں {claims} لکھا ہے\u06d4 ایسے دعوے جو ثابت نہ ہو سکیں، اشتہار رد "
        "کروا سکتے ہیں\u06d4 بہتر ہے بتائیں کہ آپ کی چیز میں خاص کیا ہے\u06d4",
    },
    "price": {
        "en": "No price is shown. Shoppers often ask the price first; add it next time.",
        "ur": "گیم میں قیمت نہیں دکھائی گئی\u06d4 خریدار اکثر پہلے قیمت پوچھتے ہیں؛ اگلی بار "
        "قیمت ضرور لکھیں\u06d4",
    },
}


def claim_warnings(brief: CreativeBrief) -> list[str]:
    """Feature 31: what the shop should look at, decided by code. The owner's own words are
    theirs to keep, so they are pointed out here rather than changed."""
    language = brief.language
    warnings: list[str] = []
    claims = unprovable_in(brief.offer_text)
    if claims:
        quoted = ", ".join(f"“{c}”" for c in claims)
        warnings.append(WARNINGS["claim"][language].format(claims=quoted))
    if not brief.price:
        warnings.append(WARNINGS["price"][language])
    return warnings


def write_report(ctx: StepContext, run: TestRun, *, passed: bool) -> dict[str, Any]:
    brief = latest_brief(ctx)
    language = brief.language
    gates = [
        {
            "gate": gate["gate"],
            "label": GATE_LABELS.get(gate["gate"], {}).get(language, gate["gate"]),
            "passed": gate["passed"],
            "message": gate["message"],
            "screenshot_key": gate.get("screenshot_key"),
        }
        for gate in run.gates
    ]
    rounds = fix_count(ctx)
    checks = "\n".join(
        f"- {g['label']}: {'passed' if g['passed'] else 'failed'}. {g['message']}" for g in gates
    )
    written = ctx.ai.ask_json(
        "shop_report",
        {
            "language_name": LANGUAGE_NAMES[language],
            "shop_name": as_data(ctx.shop.name),
            "product": as_data(brief.product.name),
            "template": ctx.ad.template or "game",
            "result": "every check passed" if passed else "some checks still fail",
            "rounds": rounds,
            "checks": checks,
        },
        ShopReport,
        subject=ctx.subject,
    )
    report: dict[str, Any] = {
        "passed": passed,
        "language": language,
        "rounds": rounds,
        "summary": written.summary,
        "next_step": written.next_step,
        "gates": gates,
        "screenshots": dict(run.screenshots),
        "test_run_id": str(run.id),
        "warnings": claim_warnings(brief),
    }
    ctx.ad.report = report
    ctx.say("reporter", "report.written", written.summary, passed=passed, rounds=rounds)
    return report


def latest_test_run(ctx: StepContext) -> TestRun | None:
    return ctx.session.scalars(
        select(TestRun).where(TestRun.ad_id == ctx.ad.id).order_by(TestRun.round.desc())
    ).first()
