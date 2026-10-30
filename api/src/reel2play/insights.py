"""What happened on the hosted game pages (feature 39), counted without personal data.

Plays, finishes, wins, time to finish and order-button taps per ad and variant. The events
carry no IP address, device or person, so the numbers can only ever be totals.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Float, case, cast, func, select
from sqlalchemy.orm import Session

from reel2play.models import Event, EventKind, EventSource


@dataclass(frozen=True)
class GameStats:
    plays: int = 0
    finishes: int = 0
    wins: int = 0
    cta_taps: int = 0
    median_seconds: float | None = None
    poster_plays: int = 0  # feature 36: plays opened from the counter poster's QR code
    website_plays: int = 0  # feature 37: plays on the shop's own website
    shares: int = 0  # feature 42: players who challenged a friend
    challenge_plays: int = 0  # feature 42: plays opened from a friend's challenge

    @property
    def completion(self) -> float | None:
        """Share of plays that reached the end card."""
        return round(self.finishes / self.plays, 3) if self.plays else None

    @property
    def cta_rate(self) -> float | None:
        """Order-button taps per finished game."""
        return round(self.cta_taps / self.finishes, 3) if self.finishes else None

    def as_json(self) -> dict[str, float | int | None]:
        return {
            "plays": self.plays,
            "finishes": self.finishes,
            "wins": self.wins,
            "cta_taps": self.cta_taps,
            "median_seconds": self.median_seconds,
            "completion": self.completion,
            "cta_rate": self.cta_rate,
            "poster_plays": self.poster_plays,
            "website_plays": self.website_plays,
            "shares": self.shares,
            "challenge_plays": self.challenge_plays,
        }


def _count(kind: EventKind) -> ColumnElement[int]:
    return func.count(case((Event.kind == kind, 1)))


def _from(source: EventSource) -> ColumnElement[int]:
    return func.count(case(((Event.kind == EventKind.PLAY) & (Event.source == source), 1)))


def stats_for(session: Session, ad_ids: list[uuid.UUID]) -> dict[uuid.UUID, GameStats]:
    if not ad_ids:
        return {}
    finish_seconds = case((Event.kind == EventKind.FINISH, Event.seconds))
    rows = session.execute(
        select(
            Event.ad_id,
            _count(EventKind.PLAY),
            _count(EventKind.FINISH),
            func.count(case(((Event.kind == EventKind.FINISH) & Event.won.is_(True), 1))),
            _count(EventKind.CTA),
            cast(func.percentile_cont(0.5).within_group(finish_seconds), Float),
            _from(EventSource.QR),
            _from(EventSource.EMBED),
            _count(EventKind.SHARE),
            _from(EventSource.SHARE),
        )
        .where(Event.ad_id.in_(ad_ids))
        .group_by(Event.ad_id)
    )
    return {
        ad_id: GameStats(
            plays=plays,
            finishes=finishes,
            wins=wins,
            cta_taps=taps,
            median_seconds=round(median, 1) if median is not None else None,
            poster_plays=poster,
            website_plays=website,
            shares=shares,
            challenge_plays=challenged,
        )
        for ad_id, plays, finishes, wins, taps, median, poster, website, shares, challenged in rows
    }


# --- reading an A/B test (feature 19) --------------------------------------------------------

MIN_PLAYS = 20
CLEAR_LEAD = 0.05


def leader(stats: dict[str, GameStats]) -> tuple[str | None, str]:
    """Which version is ahead, judged by order-button taps per finished game, then by how
    many players finish; with a plain reason. Nobody leads until every version has had
    enough plays and one is clearly ahead."""
    if len(stats) < 2:
        return None, "Make the other versions to start the test."
    short = [v for v, s in stats.items() if s.plays < MIN_PLAYS]
    if short:
        return (
            None,
            f"Waiting for {MIN_PLAYS} plays of each version ({', '.join(short)} need more).",
        )

    def ahead(measure: str) -> str | None:
        ranked = sorted(stats, key=lambda v: getattr(stats[v], measure) or 0.0, reverse=True)
        first, second = (getattr(stats[v], measure) or 0.0 for v in ranked[:2])
        return ranked[0] if first - second >= CLEAR_LEAD else None

    if best := ahead("cta_rate"):
        return best, f"Version {best} gets the most order taps per finished game."
    if best := ahead("completion"):
        return best, f"Version {best} is finished by the most players; order taps are close."
    return None, "Too close to call so far; keep sharing the test link."
