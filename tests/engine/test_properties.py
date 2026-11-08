"""Random legal play: chips conserved, no negative stacks, always terminates."""

from hypothesis import given, settings
from hypothesis import strategies as st

from pbb.engine.cards import deal_from_seed
from pbb.engine.rules import Action, HandState


def _invariants(s):
    for p in (0, 1):
        assert s.stacks[p] >= 0
        assert s.stacks[p] + s.contrib[p] == s.start_stacks[p]
        assert 0 <= s.bets[p] <= s.contrib[p]
    if not s.is_terminal:
        leg = s.legal_actions()
        assert leg.kinds, "non-terminal state with no legal action"
        assert leg.check != leg.call
        if leg.min_raise is not None:
            assert max(s.bets) < leg.min_raise <= leg.max_raise


@st.composite
def played_hands(draw):
    deal = deal_from_seed(draw(st.integers(0, 2**63)))
    button = draw(st.integers(0, 1))
    stacks = (draw(st.integers(1, 1000)), draw(st.integers(1, 1000)))
    sb = draw(st.integers(1, 5))
    bb = draw(st.integers(sb, 10))
    state = HandState.new(deal, button, stacks, (sb, bb))
    _invariants(state)
    for _ in range(200):
        if state.is_terminal:
            return state
        leg = state.legal_actions()
        kind = draw(st.sampled_from(leg.kinds))
        if kind == "raise":
            state = state.apply(Action("raise", draw(st.integers(leg.min_raise, leg.max_raise))))
        else:
            state = state.apply(Action(kind))
        _invariants(state)
    raise AssertionError("hand did not terminate")


@settings(max_examples=500, deadline=None)
@given(played_hands())
def test_random_hands_conserve_chips(s):
    assert s.is_terminal and s.to_act is None
    pay = s.payoffs
    assert sum(pay) == 0
    for p in (0, 1):
        assert -s.contrib[p] <= pay[p] <= s.contrib[1 - p]
    if s.showdown:
        assert len(s.board) == 5
