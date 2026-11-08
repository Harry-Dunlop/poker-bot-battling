"""One heads-up no-limit hold'em hand as an immutable state.

Seats are 0 and 1. The button posts the small blind, acts first preflop and
last on every later street. A raise ``amount`` is the total the raiser has bet
on this street after the raise ("raise to"), never the increment. A bet into
an unopened street is also a "raise".
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from pbb.engine.cards import Deal
from pbb.engine.evaluate import strength

STREETS = ("preflop", "flop", "turn", "river")
_BOARD_SIZE = (0, 3, 4, 5)
ACTION_KINDS = ("fold", "check", "call", "raise")


class IllegalAction(ValueError):
    """An action the rules don't allow in this state."""


@dataclass(frozen=True, slots=True)
class Action:
    kind: str  # one of ACTION_KINDS
    amount: int | None = None  # raise-to total; only for "raise"


@dataclass(frozen=True, slots=True)
class Legal:
    fold: bool
    check: bool
    call: bool
    to_call: int  # chips a call puts in (already capped at the stack)
    min_raise: int | None  # raise-to bounds; None when raising is not allowed
    max_raise: int | None

    @property
    def kinds(self) -> list[str]:
        flags = (self.fold, self.check, self.call, self.min_raise is not None)
        return [k for k, ok in zip(ACTION_KINDS, flags, strict=True) if ok]


Pair = tuple[int, int]


@dataclass(frozen=True, slots=True)
class HandState:
    button: int
    holes: tuple[tuple[str, str], tuple[str, str]]  # by seat
    full_board: tuple[str, ...]  # all five cards; only ``board`` is visible
    big_blind: int
    start_stacks: Pair
    street: int  # index into STREETS
    stacks: Pair  # chips behind
    bets: Pair  # chips put in on this street
    contrib: Pair  # chips put in this hand
    acted: tuple[bool, bool]  # acted voluntarily on this street
    last_raise: int  # size of the last full raise on this street (min raise increment)
    to_act: int | None
    folded: int | None
    showdown: bool
    history: tuple[tuple[int, int, Action], ...]  # (street, seat, action)

    # --- construction --------------------------------------------------------

    @classmethod
    def new(
        cls,
        deal: Deal,
        button: int,
        stacks: Pair = (400, 400),
        blinds: Pair = (1, 2),
    ) -> HandState:
        if button not in (0, 1):
            raise ValueError("button must be 0 or 1")
        sb, bb = blinds
        if not 0 < sb <= bb:
            raise ValueError("need 0 < small blind <= big blind")
        if min(stacks) <= 0:
            raise ValueError("stacks must be positive")
        holes = [deal.bb_hole, deal.bb_hole]
        holes[button] = deal.button_hole
        bets = [0, 0]
        bets[button] = min(sb, stacks[button])
        bets[1 - button] = min(bb, stacks[1 - button])
        state = cls(
            button=button,
            holes=(holes[0], holes[1]),
            full_board=deal.board,
            big_blind=bb,
            start_stacks=(stacks[0], stacks[1]),
            street=0,
            stacks=(stacks[0] - bets[0], stacks[1] - bets[1]),
            bets=(bets[0], bets[1]),
            contrib=(bets[0], bets[1]),
            acted=(False, False),
            last_raise=bb,
            to_act=None,
            folded=None,
            showdown=False,
            history=(),
        )
        return state._next_turn(first=button)

    # --- queries -------------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        return self.folded is not None or self.showdown

    @property
    def board(self) -> tuple[str, ...]:
        if self.showdown:
            return self.full_board
        return self.full_board[: _BOARD_SIZE[self.street]]

    @property
    def street_name(self) -> str:
        return STREETS[self.street]

    @property
    def pot(self) -> int:
        return self.contrib[0] + self.contrib[1]

    def legal_actions(self) -> Legal:
        if self.to_act is None:
            raise IllegalAction("hand is over")
        p, o = self.to_act, 1 - self.to_act
        top = max(self.bets)
        to_call = min(top - self.bets[p], self.stacks[p])
        # Can't raise past what the opponent can cover; can't raise an all-in player.
        cap = min(self.bets[p] + self.stacks[p], self.bets[o] + self.stacks[o])
        if self.stacks[o] > 0 and cap > top:
            hi = cap
            lo = min(top + max(self.last_raise, self.big_blind), hi)  # short all-in allowed
        else:
            lo = hi = None
        return Legal(
            fold=to_call > 0,
            check=to_call == 0,
            call=to_call > 0,
            to_call=to_call,
            min_raise=lo,
            max_raise=hi,
        )

    @property
    def payoffs(self) -> Pair:
        """Net chips won by each seat. Zero-sum. Uncalled chips go back to their owner."""
        if not self.is_terminal:
            raise ValueError("hand not finished")
        if self.folded is not None:
            lost = self.contrib[self.folded]
            return (-lost, lost) if self.folded == 0 else (lost, -lost)
        matched = min(self.contrib)
        s0 = strength(self.holes[0] + self.full_board)
        s1 = strength(self.holes[1] + self.full_board)
        if s0 == s1:
            return (0, 0)
        return (matched, -matched) if s0 > s1 else (-matched, matched)

    # --- transitions ---------------------------------------------------------

    def apply(self, action: Action) -> HandState:
        legal = self.legal_actions()
        p = self.to_act
        assert p is not None
        stacks, bets, contrib = list(self.stacks), list(self.bets), list(self.contrib)
        last_raise = self.last_raise

        def put(chips: int) -> None:
            stacks[p] -= chips
            bets[p] += chips
            contrib[p] += chips

        kind = action.kind
        if kind not in ACTION_KINDS:
            raise IllegalAction(f"unknown action {kind!r}")
        if kind != "raise" and action.amount is not None:
            raise IllegalAction("amount only allowed on raise")
        if kind == "fold":
            if not legal.fold:
                raise IllegalAction("fold not allowed when you can check")
            return replace(
                self,
                folded=p,
                to_act=None,
                history=self.history + ((self.street, p, action),),
            )
        if kind == "check":
            if not legal.check:
                raise IllegalAction("can't check facing a bet")
        elif kind == "call":
            if not legal.call:
                raise IllegalAction("nothing to call")
            put(legal.to_call)
        else:  # raise
            amt = action.amount
            if legal.min_raise is None:
                raise IllegalAction("raising not allowed")
            if not isinstance(amt, int) or isinstance(amt, bool):
                raise IllegalAction("raise needs an integer amount")
            if not legal.min_raise <= amt <= legal.max_raise:
                raise IllegalAction(f"raise to {amt} outside {legal.min_raise}..{legal.max_raise}")
            top = max(bets)
            put(amt - bets[p])
            if amt - top >= last_raise:  # a short all-in doesn't change the min raise
                last_raise = amt - top

        acted = list(self.acted)
        acted[p] = True
        state = replace(
            self,
            stacks=(stacks[0], stacks[1]),
            bets=(bets[0], bets[1]),
            contrib=(contrib[0], contrib[1]),
            acted=(acted[0], acted[1]),
            last_raise=last_raise,
            history=self.history + ((self.street, p, action),),
        )
        return state._next_turn(first=1 - p)

    # --- internals -----------------------------------------------------------

    def _needs_action(self, p: int) -> bool:
        if self.stacks[p] == 0:
            return False
        if self.bets[p] < max(self.bets):
            return True
        return not self.acted[p] and self.stacks[1 - p] > 0

    def _next_turn(self, first: int) -> HandState:
        for p in (first, 1 - first):
            if self._needs_action(p):
                return replace(self, to_act=p)
        # Street is closed.
        if self.street == len(STREETS) - 1 or 0 in self.stacks:
            return replace(self, to_act=None, showdown=True)
        nxt = replace(
            self,
            street=self.street + 1,
            bets=(0, 0),
            acted=(False, False),
            last_raise=self.big_blind,
            to_act=None,
        )
        return nxt._next_turn(first=1 - self.button)
