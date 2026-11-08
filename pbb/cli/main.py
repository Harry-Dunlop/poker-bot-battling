"""pbb command line. For now: `pbb check BOT_DIR` (protocol conformance, design-doc §3.1).

`pbb check` runs the bot as a plain local process: YOUR OWN BOTS ONLY.
`pbb match` arrives with the engine (M1/M2).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pbb.protocol import messages as m
from pbb.protocol.connection import BotConnection, Forfeit, Limits
from pbb.runner.local import LocalProcess

# One scripted hand: preflop (bot is button/SB, facing the big blind), then the flop.
SCRIPT = [
    dict(
        hand_id=1, street="preflop", hole=["Ah", "Kd"], board=[], pot=3, to_call=1,
        stack=399, opp_stack=398, legal=["fold", "call", "raise"], min_raise=4, max_raise=400,
    ),
    dict(
        hand_id=1, street="flop", hole=["Ah", "Kd"], board=["7c", "2h", "Ks"], pot=4,
        to_call=0, stack=398, opp_stack=398, legal=["check", "raise"], min_raise=2,
        max_raise=398,
    ),
]  # fmt: skip


def check(bot_dir: Path, startup_ms: int, wall_ms: int) -> int:
    limits = Limits(cpu_budget_ms=30_000, startup_ms=startup_ms, decision_wall_ms=wall_ms)
    conn = BotConnection(LocalProcess.for_bot_dir(bot_dir), limits)
    ok = True
    with conn:
        try:
            conn.start(
                m.match_start(
                    match_id="check",
                    seat=0,
                    hands=1,
                    cpu_budget_ms=limits.cpu_budget_ms,
                    startup_ms=startup_ms,
                )
            )
            print(f"ok    ready (startup cpu {conn.startup_cpu_us / 1000:.1f} ms)")
            for req in SCRIPT:
                d = conn.request(**req)
                mark = "ok  " if d.outcome == "ok" else "FAIL"
                ok &= d.outcome == "ok"
                print(f"{mark}  {req['street']}: {d.outcome} {d.action} {d.detail}".rstrip())
            conn.notify(
                m.hand_result(hand_id=1, deltas=[2, -2], board=["7c", "2h", "Ks", "4d", "9h"])
            )
            conn.finish(m.match_end(result="complete", hands=1, cpu_used_ms=0))
            print("ok    match_end")
        except Forfeit as e:
            ok = False
            print(f"FAIL  forfeit: {e.reason}")
    if conn.flags:
        print("warn  " + ", ".join(f"{k}={v}" for k, v in sorted(conn.flags.items())))
    if conn.stderr_text.strip():
        print("--- bot stderr (capped) ---")
        print(conn.stderr_text.rstrip())
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pbb")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="protocol conformance check (runs the bot locally)")
    c.add_argument("bot_dir", type=Path)
    c.add_argument("--startup-ms", type=int, default=15_000)
    c.add_argument("--wall-ms", type=int, default=10_000)
    args = p.parse_args(argv)
    if args.cmd == "check":
        return check(args.bot_dir, args.startup_ms, args.wall_ms)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
