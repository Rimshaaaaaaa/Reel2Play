"""Claims in text, checked the same way everywhere: game words, gates and captions.

A claim is honest when every number in it is one the shop owner gave. Digits in Urdu and
other scripts count as the same numbers as 0 to 9. Some claims cannot be proved by a small
shop at all ("best in Pakistan", "100% guaranteed", "cures"): feature 31 finds those.
"""

from __future__ import annotations

import re
import unicodedata

_DIGITS = re.compile(r"\d+")
MONEY = re.compile(r"(?:rs\.?|pkr|₨|\$|£|€)\s?\d", re.IGNORECASE)


def numbers_in(text: str | None) -> set[str]:
    return {
        "".join(str(unicodedata.digit(char)) for char in run) for run in _DIGITS.findall(text or "")
    }


def only_owner_numbers(text: str | None, *owner_texts: str | None) -> bool:
    allowed: set[str] = set()
    for owner_text in owner_texts:
        allowed |= numbers_in(owner_text)
    return numbers_in(text) <= allowed


# Claims a small shop cannot prove, in English, Roman Urdu and Urdu (feature 31).
_UNPROVABLE = re.compile(
    r"\bbest\b[^.!?\n]{0,30}?\bin\s+(?:pakistan|the\s+world|the\s+city|town|lahore|karachi"
    r"|islamabad|rawalpindi|faisalabad|peshawar|multan)\b"
    r"|\bbest\s+(?:quality|price|prices|rates?)\b"
    r"|\bno\.?\s?1\b|\bnumber\s+(?:one|1)\b|#1\b"
    r"|\b100\s?%\s+(?:original|pure|guaranteed|natural|safe|genuine)"
    r"|\bguarantee(?:d|s)?\b|\bguaranty\b"
    r"|\bcheapest\b|\blowest\s+price"
    r"|\b(?:world|pakistan)'?s\s+(?:best|finest|first|biggest|largest|only)"
    r"|\bonly\s+(?:shop|store|brand)\s+in\b"
    r"|\bcures?\b|\bheals?\b|\bmiracle\b|\bclinically\s+proven\b|\bdoctor\s+recommended\b"
    r"|\bsab\s+se\s+(?:behtareen|behtarin|acha|sasta|best)\b|\bgarant[ie]e?\b"
    r"|سب سے بہترین|سب سے سستا|نمبر ون|گارنٹی",
    re.IGNORECASE,
)


def unprovable_in(text: str | None) -> list[str]:
    """Phrases in ``text`` that claim what a small shop cannot prove, as written."""
    return [match.group(0).strip() for match in _UNPROVABLE.finditer(text or "")]
