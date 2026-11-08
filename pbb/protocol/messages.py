"""Build engine->bot messages and strictly parse bot->engine lines.

Everything a bot sends is hostile until parsed here (design-doc §4.3).
Parsers raise ``ProtocolError`` and nothing else, whatever bytes they're given.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pbb.engine.rules import Action  # one Action type shared by engine and protocol

PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 4096  # longest line a bot may send, newline included
ACTIONS = ("fold", "check", "call", "raise")


class ProtocolError(Exception):
    """A bot line that is not a well-formed protocol message."""


@dataclass(frozen=True, slots=True)
class Reply:
    seq: int
    action: Action


# --- engine -> bot -----------------------------------------------------------


def encode(msg: dict[str, Any]) -> bytes:
    """One compact JSON line, newline-terminated."""
    return json.dumps(msg, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def match_start(
    *,
    match_id: str,
    seat: int,
    hands: int,
    cpu_budget_ms: int,
    startup_ms: int,
    ladder: str = "standard",
    mode: str = "rapid",
) -> dict[str, Any]:
    return {
        "type": "match_start",
        "v": PROTOCOL_VERSION,
        "match_id": match_id,
        "ladder": ladder,
        "mode": mode,
        "hands": hands,
        "cpu_budget_ms": cpu_budget_ms,
        "startup_ms": startup_ms,
        "seat": seat,
    }


def action_request(
    *,
    seq: int,
    hand_id: int,
    street: str,
    hole: list[str],
    board: list[str],
    pot: int,
    to_call: int,
    stack: int,
    opp_stack: int,
    legal: list[str],
    min_raise: int | None,
    max_raise: int | None,
    time_bank_ms: int,
) -> dict[str, Any]:
    return {
        "type": "action_request",
        "seq": seq,
        "hand_id": hand_id,
        "street": street,
        "hole": hole,
        "board": board,
        "pot": pot,
        "to_call": to_call,
        "stack": stack,
        "opp_stack": opp_stack,
        "legal": legal,
        "min_raise": min_raise,
        "max_raise": max_raise,
        "time_bank_ms": time_bank_ms,
    }


def hand_result(
    *,
    hand_id: int,
    deltas: list[int],
    board: list[str],
    showdown: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "hand_result",
        "hand_id": hand_id,
        "deltas": deltas,
        "showdown": showdown or {},
        "board": board,
    }


def match_end(*, result: str, hands: int, cpu_used_ms: int) -> dict[str, Any]:
    return {"type": "match_end", "result": result, "hands": hands, "cpu_used_ms": cpu_used_ms}


# --- bot -> engine -----------------------------------------------------------


def _reject_constant(name: str) -> Any:
    raise ProtocolError(f"non-finite number {name}")


def parse_line(raw: bytes) -> dict[str, Any]:
    """Decode one line from a bot into a JSON object. Raises ProtocolError only."""
    if len(raw) > MAX_LINE_BYTES:
        raise ProtocolError("line too long")
    try:
        text = raw.decode("utf-8")
        obj = json.loads(text, parse_constant=_reject_constant)
    except ProtocolError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        raise ProtocolError(f"not JSON: {type(e).__name__}") from None
    if not isinstance(obj, dict):
        raise ProtocolError("not a JSON object")
    return obj


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def parse_ready(obj: dict[str, Any]) -> None:
    if obj.get("ready") is not True:
        raise ProtocolError('expected {"ready":true}')


def parse_reply(obj: dict[str, Any]) -> Reply:
    """Shape check only. Legality against the request is checked by ``check_legal``."""
    seq = obj.get("seq")
    if not _is_int(seq):
        raise ProtocolError("missing or non-integer seq")
    kind = obj.get("action")
    if kind not in ACTIONS:
        raise ProtocolError("unknown action")
    amount = obj.get("amount")
    if kind == "raise":
        if not _is_int(amount):
            raise ProtocolError("raise needs an integer amount")
    elif amount is not None:
        raise ProtocolError("amount only allowed on raise")
    return Reply(seq=seq, action=Action(kind, amount))


def check_legal(action: Action, request: dict[str, Any]) -> None:
    """Check an action against what the request offered. The engine re-validates anyway."""
    if action.kind not in request["legal"]:
        raise ProtocolError(f"{action.kind} not legal here")
    if action.kind == "raise":
        lo, hi = request["min_raise"], request["max_raise"]
        if lo is None or hi is None or not (lo <= action.amount <= hi):
            raise ProtocolError("raise amount out of range")
