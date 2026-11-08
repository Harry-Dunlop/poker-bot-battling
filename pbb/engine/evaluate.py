"""Hand strength. The only module that imports eval7."""

from __future__ import annotations

from collections.abc import Iterable

import eval7

_CARDS = {}


def _card(c: str) -> eval7.Card:
    card = _CARDS.get(c)
    if card is None:
        card = _CARDS[c] = eval7.Card(c)
    return card


def strength(cards: Iterable[str]) -> int:
    """Best 5-card strength of 5-7 cards. Higher is better; equal means a tie."""
    return eval7.evaluate([_card(c) for c in cards])
