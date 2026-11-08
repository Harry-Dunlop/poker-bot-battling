import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pbb.protocol import messages as m
from tests.conftest import PREFLOP


def test_encode_is_one_compact_line():
    data = m.encode(m.match_start(match_id="x", seat=1, hands=1000, cpu_budget_ms=1, startup_ms=1))
    assert data.endswith(b"\n") and data.count(b"\n") == 1
    assert b" " not in data
    assert json.loads(data)["v"] == m.PROTOCOL_VERSION


def test_encode_rejects_nan():
    with pytest.raises(ValueError):
        m.encode({"x": float("nan")})


@given(st.binary(max_size=m.MAX_LINE_BYTES + 10))
def test_parse_line_only_raises_protocol_error(raw):
    try:
        obj = m.parse_line(raw)
    except m.ProtocolError:
        return
    assert isinstance(obj, dict)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"[]",
        b"42",
        b'"hi"',
        b"\xff\xfe",
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b"[" * 100_000,
        b"{" + b'"a":1,' * 1000,
    ],
)
def test_parse_line_rejects(raw):
    with pytest.raises(m.ProtocolError):
        m.parse_line(raw)


def test_parse_line_rejects_oversized():
    with pytest.raises(m.ProtocolError, match="too long"):
        m.parse_line(b'{"a":"' + b"x" * m.MAX_LINE_BYTES + b'"}')


def test_parse_ready():
    m.parse_ready({"ready": True})
    for bad in ({}, {"ready": 1}, {"ready": "true"}):
        with pytest.raises(m.ProtocolError):
            m.parse_ready(bad)


@pytest.mark.parametrize(
    "obj, expected",
    [
        ({"seq": 1, "action": "fold"}, m.Action("fold")),
        ({"seq": 1, "action": "raise", "amount": 10}, m.Action("raise", 10)),
    ],
)
def test_parse_reply_ok(obj, expected):
    assert m.parse_reply(obj) == m.Reply(1, expected)


@pytest.mark.parametrize(
    "obj",
    [
        {"action": "fold"},
        {"seq": True, "action": "fold"},
        {"seq": 1.0, "action": "fold"},
        {"seq": 1, "action": "allin"},
        {"seq": 1, "action": "raise"},
        {"seq": 1, "action": "raise", "amount": 10.5},
        {"seq": 1, "action": "raise", "amount": True},
        {"seq": 1, "action": "call", "amount": 5},
    ],
)
def test_parse_reply_rejects(obj):
    with pytest.raises(m.ProtocolError):
        m.parse_reply(obj)


def test_check_legal():
    req = m.action_request(seq=1, time_bank_ms=1, **PREFLOP)
    m.check_legal(m.Action("call"), req)
    m.check_legal(m.Action("raise", 4), req)
    m.check_legal(m.Action("raise", 400), req)
    for bad in (m.Action("check"), m.Action("raise", 3), m.Action("raise", 401)):
        with pytest.raises(m.ProtocolError):
            m.check_legal(bad, req)
