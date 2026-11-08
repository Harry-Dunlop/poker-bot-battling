import pytest

from pbb.engine.match import BLINDS, STACK, play_out, schedule
from pbb.engine.rules import Action


def _shove(s):
    leg = s.legal_actions()
    return Action("raise", leg.max_raise) if leg.max_raise else Action("call")


def test_params_confirmed():
    assert BLINDS == (1, 2) and STACK == 400


def test_duplicate_pairs_share_deal_and_swap_button():
    hands = list(schedule(42, 10))
    assert [h.hand_id for h in hands] == list(range(1, 11))
    for a, b in zip(hands[::2], hands[1::2], strict=True):
        assert a.deal == b.deal and a.deal_index == b.deal_index
        assert (a.button, b.button) == (0, 1)
        sa, sb = a.new_state(), b.new_state()
        assert sa.holes[0] == sb.holes[1] == a.deal.button_hole  # each bot gets both sides


def test_schedule_is_deterministic_and_seed_dependent():
    assert list(schedule(1, 20)) == list(schedule(1, 20))
    assert [h.deal for h in schedule(1, 20)] != [h.deal for h in schedule(2, 20)]


def test_deals_differ_across_pairs():
    assert len({h.deal for h in schedule(3, 1000)}) == 500


@pytest.mark.parametrize("hands", [0, 3, -2])
def test_hands_must_be_positive_even(hands):
    with pytest.raises(ValueError):
        list(schedule(1, hands))


def test_stacks_reset_every_hand():
    for h in schedule(9, 6):
        s = h.new_state()
        assert s.start_stacks == (400, 400)
        end = play_out(s, _shove)
        assert end.is_terminal and sum(end.payoffs) == 0


def test_duplicate_cancels_card_luck_for_identical_bots():
    # Same strategy on both sides of a deal -> the pair sums to zero for each bot.
    total = [0, 0]
    for h in schedule(5, 200):
        pay = play_out(h.new_state(), _shove).payoffs
        total[0] += pay[0]
        total[1] += pay[1]
    assert total == [0, 0]


def test_play_out_raises_if_hand_does_not_end():
    s = next(schedule(1, 2)).new_state()
    with pytest.raises(RuntimeError):
        play_out(s, lambda st: Action("call"), max_actions=1)
