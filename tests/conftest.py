from pathlib import Path

import pytest

from pbb.protocol import messages as m
from pbb.protocol.connection import BotConnection, Limits
from pbb.runner.local import LocalProcess, bot_python

BEHAVE = Path(__file__).parent / "fixtures" / "behave.py"

PREFLOP = dict(
    hand_id=1,
    street="preflop",
    hole=["Ah", "Kd"],
    board=[],
    pot=3,
    to_call=1,
    stack=399,
    opp_stack=398,
    legal=["fold", "call", "raise"],
    min_raise=4,
    max_raise=400,
)


@pytest.fixture
def connect():
    """connect(mode, **limits) -> a started BotConnection running tests/fixtures/behave.py."""
    conns = []

    def make(mode, *, start=True, **kw):
        limits = Limits(
            cpu_budget_ms=kw.pop("cpu_budget_ms", 30_000),
            startup_ms=kw.pop("startup_ms", 5_000),
            decision_wall_ms=kw.pop("decision_wall_ms", 2_000),
            **kw,
        )
        conn = BotConnection(LocalProcess([bot_python(), "-u", str(BEHAVE), mode]), limits)
        conns.append(conn)
        if start:
            conn.start(
                m.match_start(
                    match_id="t",
                    seat=0,
                    hands=1,
                    cpu_budget_ms=limits.cpu_budget_ms,
                    startup_ms=limits.startup_ms,
                )
            )
        return conn

    yield make
    for c in conns:
        if c.proc.poll() is None:
            c.close()
