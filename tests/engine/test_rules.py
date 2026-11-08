import pytest

from pbb.engine.cards import Deal
from pbb.engine.rules import Action, HandState, IllegalAction

FOLD, CHECK, CALL = Action("fold"), Action("check"), Action("call")


def R(n):
    return Action("raise", n)


# Button: aces. BB: 7-2. Nothing on the board helps 7-2.
DEAL = Deal(("Ah", "Ad"), ("7c", "2d"), ("Ks", "9h", "4c", "Jd", "3s"))
# Both play the board (royal flush) -> split.
SPLIT = Deal(("2c", "3d"), ("4c", "5d"), ("As", "Ks", "Qs", "Js", "Ts"))


def new(button=0, deal=DEAL, stacks=(400, 400), blinds=(1, 2)):
    return HandState.new(deal, button, stacks, blinds)


def play(state, *actions):
    for a in actions:
        state = state.apply(a)
    return state


# --- blinds and order ---------------------------------------------------------


@pytest.mark.parametrize("button", [0, 1])
def test_button_posts_small_blind_and_acts_first_preflop(button):
    s = new(button)
    bb = 1 - button
    assert s.bets[button] == 1 and s.bets[bb] == 2
    assert s.stacks[button] == 399 and s.stacks[bb] == 398
    assert s.to_act == button
    assert s.holes[button] == DEAL.button_hole and s.holes[bb] == DEAL.bb_hole
    assert s.pot == 3 and s.board == ()


@pytest.mark.parametrize("button", [0, 1])
def test_big_blind_acts_first_postflop(button):
    s = play(new(button), CALL, CHECK)
    assert s.street_name == "flop" and len(s.board) == 3
    assert s.to_act == 1 - button
    s = play(s, CHECK)
    assert s.to_act == button
    s = play(s, CHECK)
    assert s.street_name == "turn" and s.to_act == 1 - button


def test_big_blind_gets_option_after_limp():
    s = play(new(), CALL)
    assert s.street_name == "preflop" and s.to_act == 1
    leg = s.legal_actions()
    assert leg.check and not leg.call and not leg.fold
    assert leg.min_raise == 4


def test_check_down_reaches_showdown():
    s = play(new(), CALL, CHECK, *[CHECK] * 6)
    assert s.is_terminal and s.showdown and s.board == DEAL.board
    assert s.payoffs == (2, -2)  # aces win the blinds


# --- raise sizing -------------------------------------------------------------


def test_preflop_min_raise_is_to_four():
    leg = new().legal_actions()
    assert leg.kinds == ["fold", "call", "raise"]
    assert (leg.to_call, leg.min_raise, leg.max_raise) == (1, 4, 400)


def test_amount_is_raise_to_total():
    s = play(new(), R(10))
    assert s.bets == (10, 2) and s.stacks == (390, 398)


def test_min_reraise_is_last_raise_size():
    s = play(new(), R(10))  # raise of 8
    assert s.legal_actions().min_raise == 18
    s = play(s, R(30))  # raise of 20
    assert s.legal_actions().min_raise == 50


def test_raise_outside_range_is_illegal():
    s = play(new(), R(10))
    with pytest.raises(IllegalAction):
        s.apply(R(17))
    with pytest.raises(IllegalAction):
        s.apply(R(401))


def test_postflop_min_bet_is_big_blind():
    s = play(new(), CALL, CHECK)
    leg = s.legal_actions()
    assert leg.kinds == ["check", "raise"] and leg.min_raise == 2 and leg.max_raise == 398
    s = play(s, R(2))
    assert s.legal_actions().min_raise == 4


def test_all_in_under_min_raise_allowed_and_does_not_reopen():
    s = play(new(), R(300))  # raise of 298
    leg = s.legal_actions()
    assert leg.min_raise == leg.max_raise == 400  # all-in short of a full re-raise
    s = play(s, R(400))
    assert s.last_raise == 298  # a short all-in doesn't change the min raise
    assert s.legal_actions().kinds == ["fold", "call"]  # opponent all-in: no raising


def test_raise_capped_by_opponent_stack():
    assert new(stacks=(400, 100)).legal_actions().max_raise == 100


@pytest.mark.parametrize("bad", [R(None), R(True), R(4.0), Action("raise", "4"), Action("bet", 4)])
def test_malformed_actions_rejected(bad):
    with pytest.raises(IllegalAction):
        new().apply(bad)


def test_amount_on_non_raise_rejected():
    with pytest.raises(IllegalAction):
        new().apply(Action("call", 1))


def test_cannot_fold_when_check_available():
    with pytest.raises(IllegalAction):
        play(new(), CALL).apply(FOLD)


def test_cannot_check_facing_bet():
    with pytest.raises(IllegalAction):
        new().apply(CHECK)


# --- endings ------------------------------------------------------------------


def test_fold_ends_hand_and_pays_contribution():
    s = play(new(button=1), FOLD)  # button (seat 1) folds its small blind
    assert s.is_terminal and s.folded == 1 and s.to_act is None
    assert s.payoffs == (1, -1)
    with pytest.raises(IllegalAction):
        s.apply(CALL)


def test_fold_to_raise_returns_uncalled_chips():
    assert play(new(), R(50), FOLD).payoffs == (2, -2)


def test_all_in_preflop_runs_out_board():
    s = play(new(), R(400), CALL)
    assert s.is_terminal and s.showdown and s.board == DEAL.board
    assert s.payoffs == (400, -400)


def test_all_in_on_flop_runs_out():
    s = play(new(), CALL, CHECK, R(398), CALL)
    assert s.showdown and len(s.board) == 5
    assert s.payoffs == (400, -400)


def test_split_pot():
    assert play(new(deal=SPLIT), R(400), CALL).payoffs == (0, 0)


def test_short_stack_call_only_matches_what_it_has():
    s = play(new(stacks=(400, 50)), R(50))
    assert s.legal_actions().kinds == ["fold", "call"]
    assert play(s, CALL).payoffs == (50, -50)


def test_blind_bigger_than_stack_goes_straight_to_showdown():
    s = new(stacks=(1, 400), button=1)  # seat 0 is BB with 1 chip
    assert s.is_terminal and s.showdown
    assert s.contrib == (1, 1)
    assert sum(s.payoffs) == 0 and abs(s.payoffs[0]) <= 1


def test_history_records_street_and_seat():
    s = play(new(), CALL, CHECK, R(6))
    assert s.history == ((0, 0, CALL), (0, 1, CHECK), (1, 1, R(6)))


def test_payoffs_before_end_raise():
    with pytest.raises(ValueError):
        _ = new().payoffs
