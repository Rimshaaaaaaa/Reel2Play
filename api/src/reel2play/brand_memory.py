"""Memory per brand (feature 53): what worked for this shop before.

Code gathers the facts from the shop's own games: which templates it had, how many people
played, how many finished and how many tapped the order button; which version won an A/B
test; which games players found hard. The director reads them when it designs the next
game and decides; nothing here forces a template. Only anonymous play numbers are used.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from reel2play.insights import GameStats, leader, stats_for
from reel2play.models import Ad, AdStatus, Shop, Suggestion

MIN_PLAYS = 20  # fewer plays than this say little about a template
SEEN = (AdStatus.PUBLISHED, AdStatus.REPLACED)


@dataclass
class TemplateRecord:
    template: str
    games: int = 0
    plays: int = 0
    finishes: int = 0
    cta_taps: int = 0
    ab_wins: int = 0
    made_easier: int = 0

    @property
    def completion(self) -> float | None:
        return self.finishes / self.plays if self.plays else None

    @property
    def cta_rate(self) -> float | None:
        return self.cta_taps / self.finishes if self.finishes else None

    @property
    def enough(self) -> bool:
        return self.plays >= MIN_PLAYS


@dataclass
class BrandMemory:
    records: list[TemplateRecord] = field(default_factory=list)

    @property
    def best(self) -> TemplateRecord | None:
        ranked = [r for r in self.records if r.enough]
        ranked.sort(key=lambda r: (r.cta_rate or 0.0, r.completion or 0.0), reverse=True)
        return ranked[0] if ranked else None

    def lines(self) -> list[str]:
        """One plain line per template, the best first."""
        best = self.best
        ordered = sorted(
            self.records,
            key=lambda r: (r is not best, -(r.cta_rate or 0.0), -r.plays),
        )
        out = []
        for r in ordered:
            parts = [f"{r.template}: {r.games} game{'s' if r.games != 1 else ''}, {r.plays} plays"]
            if r.completion is not None:
                parts.append(f"{r.completion:.0%} finished")
            if r.cta_rate is not None:
                parts.append(f"{r.cta_rate:.0%} of finishers tapped order")
            if r.ab_wins:
                parts.append(f"won {r.ab_wins} A/B test{'s' if r.ab_wins != 1 else ''}")
            if r.made_easier:
                parts.append("players found it hard (an easier version was made)")
            if not r.enough:
                parts.append("too few plays to judge")
            if r is best:
                parts.append("the best so far")
            out.append(", ".join(parts))
        return out

    def for_director(self) -> str:
        if not self.records:
            return "none yet: this is the shop's first game."
        return "\n".join(f"- {line}" for line in self.lines())


def remember(session: Session, shop: Shop, exclude: uuid.UUID | None = None) -> BrandMemory:
    ads = list(
        session.scalars(
            select(Ad).where(
                Ad.shop_id == shop.id,
                Ad.status.in_(SEEN),
                Ad.template.is_not(None),
                or_(Ad.easier_for.is_(None), Ad.suggestion == Suggestion.USED),
            )
        )
    )
    ads = [ad for ad in ads if ad.id != exclude]
    stats = stats_for(session, [ad.id for ad in ads])
    records: dict[str, TemplateRecord] = {}
    groups: dict[uuid.UUID, list[Ad]] = defaultdict(list)
    for ad in ads:
        template = str(ad.template)
        record = records.setdefault(template, TemplateRecord(template))
        numbers = stats.get(ad.id, GameStats())
        record.games += 1
        record.plays += numbers.plays
        record.finishes += numbers.finishes
        record.cta_taps += numbers.cta_taps
        groups[ad.group_id].append(ad)
    eased = set(
        session.scalars(select(Ad.easier_for).where(Ad.easier_for.in_([ad.id for ad in ads])))
    )
    for ad in ads:
        if ad.id in eased:
            records[str(ad.template)].made_easier += 1
    for members in groups.values():
        if len(members) < 2:
            continue
        found, _ = leader({m.variant: stats.get(m.id, GameStats()) for m in members})
        winner = next((m for m in members if m.variant == found), None)
        if winner is not None:
            records[str(winner.template)].ab_wins += 1
    return BrandMemory(list(records.values()))
