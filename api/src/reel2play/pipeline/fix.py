"""Fix step (feature 29): a failed gate goes back to the director with its evidence and
screenshot; the game is rebuilt from the revised proposal and tested again.
"""

from __future__ import annotations

import json
from typing import Any

from reel2play.ai.media import media_part
from reel2play.ai.messages import MediaKind
from reel2play.analysis import LANGUAGE_NAMES
from reel2play.builder.proposal import GameProposal
from reel2play.builder.templates import buildable, load_templates
from reel2play.models import AdStatus, Fix
from reel2play.pipeline.build import compile_and_store
from reel2play.pipeline.report import fix_count, latest_test_run
from reel2play.pipeline.runner import PIPELINE, StepContext, StepFailedError
from reel2play.pipeline.state import latest_brief, latest_build
from reel2play.pipeline.variants import make_different, sibling_builds
from reel2play.safety import as_data

PROMPT = "director_fix"
TEXT_FIELDS = ("title", "instruction", "win_text", "lose_text", "cta_label", "offer_line")


def describe_change(before: dict[str, Any], after: GameProposal) -> str:
    """The proposal's changes in plain words, for the audit trail and the report."""
    new = after.model_dump(mode="json")
    changes: list[str] = []
    if before.get("template") != new["template"]:
        changes.append(f"switched to the {new['template']} template")
    if before.get("difficulty") != new["difficulty"]:
        changes.append(f"difficulty {before.get('difficulty')} to {new['difficulty']}")
    if before.get("difficulty_overrides", {}) != new["difficulty_overrides"]:
        changes.append(f"tuned {', '.join(sorted(new['difficulty_overrides'])) or 'difficulty'}")
    rewritten = [f for f in TEXT_FIELDS if before.get(f) != new[f]]
    if rewritten:
        changes.append("rewrote " + ", ".join(f.replace("_", " ") for f in rewritten))
    if (before.get("primary_color"), before.get("accent_color")) != (
        new["primary_color"],
        new["accent_color"],
    ):
        changes.append("changed the colours")
    return "; ".join(changes) or "rebuilt with the same proposal"


@PIPELINE.add("fix", AdStatus.FIXING, "director", "The director is fixing what the tester found.")
def fix(ctx: StepContext) -> str:
    run = latest_test_run(ctx)
    build = latest_build(ctx)
    if run is None or build is None:
        raise StepFailedError("there is no failed test to fix")
    brief = latest_brief(ctx)
    failed = [gate for gate in run.gates if not gate["passed"]]
    shot_key = next(
        (g["screenshot_key"] for g in failed if g.get("screenshot_key")),
        run.screenshots.get("phone-played-end"),
    )
    shot = (
        media_part(ctx.storage, ctx.settings, shot_key, MediaKind.IMAGE, "image/png")
        if shot_key
        else None
    )
    templates = load_templates(ctx.settings.templates_dir)
    catalog = "\n".join(
        spec.catalog_line() + " " + spec.ranges_line() for spec in buildable(templates).values()
    )
    failures = "\n".join(
        f"- {g['gate']}: {g['message']} Measured: {json.dumps(g['measured'], ensure_ascii=False)}"
        for g in failed
    )
    proposal = ctx.ai.ask_json(
        PROMPT,
        {
            "shop_name": as_data(ctx.shop.name),
            "product": as_data(brief.product.name),
            "palette": ", ".join(brief.palette),
            "offer": as_data(brief.offer_text),
            "language_name": LANGUAGE_NAMES[brief.language],
            "failures": failures,
            "previous": json.dumps(build.proposal, ensure_ascii=False),
            "catalog": catalog,
        },
        GameProposal,
        media=[shot] if shot else [],
        subject=ctx.subject,
    )
    if ctx.ad.variant != "A":  # feature 19: a fix must not turn a version into another's copy
        siblings = sibling_builds(ctx.session, ctx.ad)
        proposal, notes = make_different(proposal, siblings, brief, templates)
        for note in notes:
            ctx.say("builder", "variant.changed", f"Code kept this version different: {note}.")
    change = describe_change(build.proposal, proposal)
    new_build = compile_and_store(ctx, brief, proposal)
    round_number = fix_count(ctx) + 1
    ctx.session.add(
        Fix(
            ad_id=ctx.ad.id,
            round=round_number,
            failed_gates=[g["gate"] for g in failed],
            change=change,
            build_id=new_build.id,
        )
    )
    ctx.say(
        "director",
        "fix.done",
        f"Fix round {round_number}: {change}.",
        round=round_number,
        failed=[g["gate"] for g in failed],
    )
    return "test"
