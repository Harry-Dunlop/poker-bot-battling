"""Per-bot connection state machine as a lookup table (design-doc §3.0).

The table is the single source of truth: ``connection.py`` drives it and
``pbb check`` exercises it. Any (state, event) pair not in the table is a bug
in the engine, not the bot, so ``step`` raises.
"""

from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    SPAWNED = "SPAWNED"
    STARTING = "STARTING"
    IDLE = "IDLE"
    THINKING = "THINKING"
    DONE = "DONE"
    FORFEIT = "FORFEIT"


class Event(StrEnum):
    SEND_MATCH_START = "send_match_start"
    READY = "ready"
    STARTUP_TIMEOUT = "startup_timeout"
    SEND_REQUEST = "send_request"
    VALID_ACTION = "valid_action"
    INVALID_REPLY = "invalid_reply"  # bad JSON reply, illegal action, oversized line
    TIMEOUT = "timeout"  # wall-clock cap or CPU budget hit mid-decision
    STALE_REPLY = "stale_reply"  # reply echoing an old seq
    STRAY_LINE = "stray_line"  # non-JSON (debug print) or a line outside THINKING
    SEND_NOTICE = "send_notice"  # hand_result: informational, no reply expected
    SEND_MATCH_END = "send_match_end"
    DIED = "died"  # crash, EOF, OOM, stopped reading stdin


class Effect(StrEnum):
    START_STARTUP_CLOCK = "start_startup_clock"  # thaw; CPU measured but not charged
    END_STARTUP = "end_startup"  # freeze
    START_CLOCK = "start_clock"  # thaw; charge CPU from here
    STOP_CLOCK = "stop_clock"  # freeze; charge CPU; return the action
    STOP_CLOCK_FOLD = "stop_clock_fold"  # freeze; charge CPU; engine folds
    DISCARD = "discard"  # ignore, keep going
    DISCARD_FLAG = "discard_flag"  # ignore, count it against the bot
    NONE = "none"
    FINISH = "finish"  # thaw so it can exit, close stdin, reap
    FORFEIT = "forfeit"  # kill; bot loses the match


S, E, X = State, Event, Effect

TABLE: dict[tuple[State, Event], tuple[State, Effect]] = {
    (S.SPAWNED, E.SEND_MATCH_START): (S.STARTING, X.START_STARTUP_CLOCK),
    (S.STARTING, E.READY): (S.IDLE, X.END_STARTUP),
    (S.STARTING, E.STRAY_LINE): (S.STARTING, X.DISCARD_FLAG),
    (S.STARTING, E.STARTUP_TIMEOUT): (S.FORFEIT, X.FORFEIT),
    (S.IDLE, E.SEND_REQUEST): (S.THINKING, X.START_CLOCK),
    (S.IDLE, E.SEND_NOTICE): (S.IDLE, X.NONE),
    (S.IDLE, E.STRAY_LINE): (S.IDLE, X.DISCARD_FLAG),
    (S.IDLE, E.STALE_REPLY): (S.IDLE, X.DISCARD),
    (S.IDLE, E.SEND_MATCH_END): (S.DONE, X.FINISH),
    (S.THINKING, E.VALID_ACTION): (S.IDLE, X.STOP_CLOCK),
    (S.THINKING, E.INVALID_REPLY): (S.IDLE, X.STOP_CLOCK_FOLD),
    (S.THINKING, E.TIMEOUT): (S.IDLE, X.STOP_CLOCK_FOLD),
    (S.THINKING, E.STALE_REPLY): (S.THINKING, X.DISCARD),
    (S.THINKING, E.STRAY_LINE): (S.THINKING, X.DISCARD_FLAG),
}
# Dying is fatal from every live state.
for _s in (S.SPAWNED, S.STARTING, S.IDLE, S.THINKING):
    TABLE[(_s, E.DIED)] = (S.FORFEIT, X.FORFEIT)


class IllegalTransition(Exception):
    """Engine bug: an event fired in a state that doesn't allow it."""


def step(state: State, event: Event) -> tuple[State, Effect]:
    try:
        return TABLE[(state, event)]
    except KeyError:
        raise IllegalTransition(f"{event} in {state}") from None
