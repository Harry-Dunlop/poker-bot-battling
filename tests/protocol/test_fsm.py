import pytest

from pbb.protocol.fsm import TABLE, Effect, Event, IllegalTransition, State, step


def test_happy_path():
    s = State.SPAWNED
    for event, expected in [
        (Event.SEND_MATCH_START, State.STARTING),
        (Event.READY, State.IDLE),
        (Event.SEND_REQUEST, State.THINKING),
        (Event.VALID_ACTION, State.IDLE),
        (Event.SEND_NOTICE, State.IDLE),
        (Event.SEND_MATCH_END, State.DONE),
    ]:
        s, _ = step(s, event)
        assert s is expected


@pytest.mark.parametrize("event", [Event.INVALID_REPLY, Event.TIMEOUT])
def test_bad_decision_folds_and_returns_to_idle(event):
    assert step(State.THINKING, event) == (State.IDLE, Effect.STOP_CLOCK_FOLD)


@pytest.mark.parametrize("state", [State.SPAWNED, State.STARTING, State.IDLE, State.THINKING])
def test_death_is_forfeit_everywhere(state):
    assert step(state, Event.DIED) == (State.FORFEIT, Effect.FORFEIT)


def test_terminal_states_accept_nothing():
    for (s, _), _ in TABLE.items():
        assert s not in (State.DONE, State.FORFEIT)


def test_engine_cannot_send_request_while_bot_thinks():
    with pytest.raises(IllegalTransition):
        step(State.THINKING, Event.SEND_REQUEST)


def test_only_idle_may_end_match():
    for s in State:
        if s is not State.IDLE:
            assert (s, Event.SEND_MATCH_END) not in TABLE
