"""Cards as two-char strings ("Ah", "Td") and seeded deals.

Never touches the global RNG: every deal comes from ``random.Random(seed)``.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

RANKS = "23456789TJQKA"
SUITS = "cdhs"
DECK: tuple[str, ...] = tuple(r + s for r in RANKS for s in SUITS)
_DECK_SET = frozenset(DECK)


def parse_card(text: str) -> str:
    """Validate and normalise a card string. Raises ValueError."""
    if not isinstance(text, str) or len(text) != 2:
        raise ValueError(f"bad card {text!r}")
    card = text[0].upper() + text[1].lower()
    if card not in _DECK_SET:
        raise ValueError(f"bad card {text!r}")
    return card


@dataclass(frozen=True, slots=True)
class Deal:
    """Cards for one deal, by position: button hole, big-blind hole, full board."""

    button_hole: tuple[str, str]
    bb_hole: tuple[str, str]
    board: tuple[str, str, str, str, str]


def shuffled_deck(seed: int) -> list[str]:
    deck = list(DECK)
    random.Random(seed).shuffle(deck)
    return deck


def deal_from_seed(seed: int) -> Deal:
    d = shuffled_deck(seed)
    return Deal(button_hole=(d[0], d[1]), bb_hole=(d[2], d[3]), board=tuple(d[4:9]))


def deal_seed(match_seed: int, deal_index: int) -> int:
    """Stable 64-bit seed for deal i of a match (not Python's salted hash())."""
    digest = hashlib.sha256(f"pbb-deal:{match_seed}:{deal_index}".encode()).digest()
    return int.from_bytes(digest[:8], "big")
