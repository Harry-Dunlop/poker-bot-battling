"""Duplicate scheduling and the per-match game parameters.

Bot 0 always sits in seat 0, bot 1 in seat 1. Deal i is played twice, as
hands 2i+1 and 2i+2 (hand ids are 1-based): first with bot 0 on the button,
then with bot 1 on the button holding the same button cards. So each bot
plays both sides of every deal. Stacks reset every hand.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from pbb.engine.cards import Deal, deal_from_seed, deal_seed
from pbb.engine.rules import Action, HandState

# Confirmed by Harry 2026-11-08: blinds 1/2, 400 chips (200 bb), reset every hand.
BLINDS = (1, 2)
STACK = 400
HANDS = 1000


@dataclass(frozen=True, slots=True)
class ScheduledHand:
    hand_id: int  # 1-based
    deal_index: int  # 0-based; both hands of a deal share it
    button: int  # seat (= bot) on the button
    deal: Deal

    def new_state(self, stack: int = STACK, blinds: tuple[int, int] = BLINDS) -> HandState:
        return HandState.new(self.deal, self.button, (stack, stack), blinds)


def schedule(match_seed: int, hands: int = HANDS) -> Iterator[ScheduledHand]:
    if hands <= 0 or hands % 2:
        raise ValueError("hands must be a positive even number (duplicate pairs)")
    for i in range(hands // 2):
        deal = deal_from_seed(deal_seed(match_seed, i))
        yield ScheduledHand(hand_id=2 * i + 1, deal_index=i, button=0, deal=deal)
        yield ScheduledHand(hand_id=2 * i + 2, deal_index=i, button=1, deal=deal)


Chooser = Callable[[HandState], Action]


def play_out(state: HandState, choose: Chooser, max_actions: int = 1000) -> HandState:
    """Drive a hand to the end with ``choose`` picking each action. Pure if choose is."""
    for _ in range(max_actions):
        if state.is_terminal:
            return state
        state = state.apply(choose(state))
    raise RuntimeError("hand did not terminate")
