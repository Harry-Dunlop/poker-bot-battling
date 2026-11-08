"""End-to-end walkie-talkie tests against our own harmless fixture bot (tests/fixtures)."""

import pytest

from pbb.protocol import messages as m
from pbb.protocol.connection import Forfeit
from pbb.protocol.fsm import State
from tests.conftest import PREFLOP

END = m.match_end(result="complete", hands=1, cpu_used_ms=0)


def test_good_bot_full_cycle(connect):
    c = connect("good")
    assert c.state is State.IDLE
    d = c.request(**PREFLOP)
    assert (d.outcome, d.action) == ("ok", m.Action("call"))
    c.notify(m.hand_result(hand_id=1, deltas=[1, -1], board=[]))
    d = c.request(**PREFLOP)
    assert d.outcome == "ok"
    c.finish(END)
    assert c.state is State.DONE
    assert c.proc.poll() is not None
    assert not c.flags


@pytest.mark.parametrize(
    "mode",
    ["bad_action", "illegal_raise", "no_seq", "future_seq", "oversized"],
)
def test_invalid_reply_folds_and_match_continues(connect, mode):
    c = connect(mode)
    d = c.request(**PREFLOP)
    assert d.action is None and d.outcome == "invalid"
    assert c.state is State.IDLE
    c.finish(END)
    assert c.state is State.DONE


def test_non_json_is_stray_then_times_out(connect):
    c = connect("bad_json", decision_wall_ms=300)
    d = c.request(**PREFLOP)
    assert d.outcome == "timeout" and d.action is None
    assert c.flags["stray_line"] == 1


def test_debug_print_is_ignored(connect):
    c = connect("debug_print")
    assert c.request(**PREFLOP).outcome == "ok"
    assert c.flags["stray_line"] == 1


def test_stale_reply_skipped(connect):
    c = connect("stale_then_good")
    assert c.request(**PREFLOP).outcome == "ok"
    assert c.flags["stale_reply"] == 1


def test_extra_reply_flagged_not_used(connect):
    c = connect("double_reply")
    assert c.request(**PREFLOP).outcome == "ok"
    assert c.request(**PREFLOP).outcome == "ok"  # the duplicate isn't read as this answer
    assert c.flags["stale_reply"] >= 1


def test_late_reply_after_timeout_is_discarded(connect):
    # Bot sleeps 1.0 s (wall) on request 1. Request 1 times out at 0.7 s; during request 2
    # the bot wakes, sends its answer to seq 1 (stale, discarded), then answers seq 2.
    c = connect("slow_first", decision_wall_ms=700)
    first = c.request(**PREFLOP)
    assert first.outcome == "timeout"
    second = c.request(**PREFLOP)
    assert second.outcome == "ok"
    assert c.flags["stale_reply"] == 1


def test_crash_is_forfeit(connect):
    c = connect("crash")
    with pytest.raises(Forfeit):
        c.request(**PREFLOP)
    assert c.state is State.FORFEIT


def test_never_ready_is_forfeit(connect):
    c = connect("never_ready", start=False, startup_ms=300)
    with pytest.raises(Forfeit, match="ready"):
        c.start(m.match_start(match_id="t", seat=0, hands=1, cpu_budget_ms=1, startup_ms=300))
    assert c.state is State.FORFEIT


def test_no_flush_is_forfeit(connect):
    c = connect("no_flush", start=False, startup_ms=500)
    with pytest.raises(Forfeit):
        c.start(m.match_start(match_id="t", seat=0, hands=1, cpu_budget_ms=1, startup_ms=500))


def test_chatty_startup_is_fine(connect):
    c = connect("chatty_startup")
    assert c.state is State.IDLE
    assert c.flags["stray_line"] == 1


def test_spin_hits_cpu_budget_then_auto_folds(connect):
    c = connect("spin", cpu_budget_ms=300, decision_wall_ms=10_000)
    d = c.request(**PREFLOP)
    assert d.outcome == "timeout"
    assert d.cpu_ms >= 250
    d = c.request(**PREFLOP)
    assert d.outcome == "budget" and d.action is None


def test_stderr_flood_neither_blocks_nor_grows(connect):
    c = connect("stderr_flood", stderr_cap_bytes=1000)
    assert c.request(**PREFLOP).outcome == "ok"
    assert len(c.stderr_text) <= 1000


def test_cpu_is_charged_only_while_thinking(connect):
    c = connect("good")
    assert c.cpu_used_us == 0
    c.request(**PREFLOP)
    assert c.cpu_used_ms < 1000


def test_time_bank_in_request_is_remaining_budget(connect):
    c = connect("good", cpu_budget_ms=5000)
    c.request(**PREFLOP)
    assert c.cpu_used_ms < 5000
