"""Safety rules decided by code (features 56 and 58).

- Prompt-injection guard: text that came from a video, a caption or a chat is data, never
  instructions. It reaches a model only inside «quote marks» it cannot close, and any of it
  that tries to give instructions is kept out of the game, with a line in the audit log.
- Blocked categories: no games for alcohol, tobacco, weapons or adult products. The
  director reports what it sees; code also checks the words, so either one blocks.
- Prizes are coupons, never cash: an offer that promises a cash prize is left out.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

DATA_OPEN, DATA_CLOSE = "«", "»"
DATA_LIMIT = 300

_INJECTION = re.compile(
    r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:instruction|prompt|rule|task)s?\b"
    r"|\byou are now\b|\bnew instructions?\b|\bsystem prompt\b|\bdeveloper mode\b|\bjailbreak"
    r"|\breveal (?:your|the) (?:prompt|instructions|system)"
    r"|</?(?:system|assistant|user|instructions?)>|\[/?(?:system|inst)\]"
    r"|ہدایات (?:کو )?نظر انداز",
    re.IGNORECASE,
)


class Restricted(StrEnum):
    NONE = "none"
    ALCOHOL = "alcohol"
    TOBACCO = "tobacco"
    WEAPONS = "weapons"
    ADULT = "adult"


# Whole words, in English, Roman Urdu and Urdu. Kitchen knives, lingerie and medicines are
# ordinary shop products and are not on these lists.
_BLOCKED_WORDS: dict[Restricted, tuple[str, ...]] = {
    Restricted.ALCOHOL: (
        "alcohol",
        "beer",
        "wine",
        "vodka",
        "whisky",
        "whiskey",
        "rum",
        "gin",
        "liquor",
        "champagne",
        "tequila",
        "sharaab",
        "sharab",
        "شراب",
    ),
    Restricted.TOBACCO: (
        "tobacco",
        "cigarette",
        "cigarettes",
        "cigar",
        "cigars",
        "vape",
        "vapes",
        "e-cigarette",
        "hookah",
        "shisha",
        "nicotine",
        "naswar",
        "gutka",
        "سگریٹ",
        "تمباکو",
        "حقہ",
        "نسوار",
    ),
    Restricted.WEAPONS: (
        "gun",
        "guns",
        "pistol",
        "pistols",
        "rifle",
        "rifles",
        "revolver",
        "firearm",
        "firearms",
        "ammunition",
        "ammo",
        "bullets",
        "bandook",
        "pistaul",
        "اسلحہ",
        "بندوق",
        "پستول",
    ),
    Restricted.ADULT: (
        "sex toy",
        "sex toys",
        "adult toy",
        "adult toys",
        "porn",
        "xxx",
        "erotic",
        "18+",
    ),
}
# A prize paid in money. "Cash on delivery" is a way to pay, not a prize, and is fine.
_CASH_PRIZE = re.compile(
    r"\bcash (?:prize|reward|back)\b|\bwin (?:rs\.?|pkr|₨)\s?\d|\bwin\b[^.\n]{0,20}\bcash\b"
    r"|\b(?:naqad|nakad|cash) inaam\b|نقد انعام|کیش پرائز|کیش انعام",
    re.IGNORECASE,
)

BLOCKED_MESSAGE = "We cannot make game ads for alcohol, tobacco, weapons or adult products."


def injection_in(text: str | None) -> bool:
    return bool(text) and _INJECTION.search(unicodedata.normalize("NFKC", text or "")) is not None


def as_data(text: str | None, limit: int = DATA_LIMIT) -> str:
    """Untrusted text for a prompt: one line, capped, inside quote marks it cannot close."""
    if not text:
        return "none"
    clean = "".join(" " if unicodedata.category(c).startswith("C") else c for c in text)
    clean = clean.replace(DATA_OPEN, '"').replace(DATA_CLOSE, '"')
    clean = re.sub(r"\s+", " ", clean).strip()[:limit]
    return f"{DATA_OPEN}{clean}{DATA_CLOSE}" if clean else "none"


def _word_pattern(word: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w-]){re.escape(word)}(?![\w-])", re.IGNORECASE)


_PATTERNS = {kind: [_word_pattern(w) for w in words] for kind, words in _BLOCKED_WORDS.items()}


@dataclass(frozen=True)
class CategoryCheck:
    restricted: Restricted
    reason: str  # "director", "words" or "" when allowed

    @property
    def blocked(self) -> bool:
        return self.restricted is not Restricted.NONE


def check_category(model_says: str, texts: list[str | None]) -> CategoryCheck:
    """Blocked if the director says so, or if any text names a blocked product."""
    if model_says in {r.value for r in Restricted} and model_says != Restricted.NONE:
        return CategoryCheck(Restricted(model_says), "director")
    joined = " \n ".join(t for t in texts if t)
    for kind, patterns in _PATTERNS.items():
        if any(p.search(joined) for p in patterns):
            return CategoryCheck(kind, "words")
    return CategoryCheck(Restricted.NONE, "")


def cash_prize_in(text: str | None) -> bool:
    return bool(text) and _CASH_PRIZE.search(text or "") is not None
