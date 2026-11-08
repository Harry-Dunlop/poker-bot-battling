"""Test bot with one deliberate misbehaviour per mode. Harmless by design: safe to run locally.

Hostile bots (fork bomb, OOM, network, filesystem writes) live in tests/nasty_bots and are
vm_only: they run in the sandbox VM in M4, never on a personal machine.

usage: python -u behave.py MODE
"""

import json
import sys
import time

mode = sys.argv[1]
out = sys.stdout
if mode == "no_flush":
    out = open(sys.stdout.fileno(), "w", buffering=1 << 16, closefd=False)  # noqa: SIM115


def send(text):
    out.write(text + "\n")
    if mode != "no_flush":
        out.flush()


def answer(msg):
    legal = msg["legal"]
    action = "check" if "check" in legal else "call" if "call" in legal else "fold"
    return json.dumps({"seq": msg["seq"], "action": action})


requests = 0
for line in sys.stdin:
    msg = json.loads(line)
    t = msg["type"]
    if t == "match_start":
        if mode == "never_ready":
            continue
        if mode == "chatty_startup":
            send("loading tables...")
        send('{"ready":true}')
        continue
    if t == "match_end":
        break
    if t != "action_request":
        continue
    requests += 1

    if mode == "crash":
        sys.exit(3)
    elif mode == "bad_json":
        send("{this is not json")
    elif mode == "bad_action":
        send(json.dumps({"seq": msg["seq"], "action": "dance"}))
    elif mode == "illegal_raise":
        send(json.dumps({"seq": msg["seq"], "action": "raise", "amount": 10**9}))
    elif mode == "no_seq":
        send('{"action":"fold"}')
    elif mode == "future_seq":
        send(json.dumps({"seq": msg["seq"] + 5, "action": "fold"}))
    elif mode == "stale_then_good":
        send(json.dumps({"seq": msg["seq"] - 1, "action": "fold"}))
        send(answer(msg))
    elif mode == "debug_print":
        send("thinking about it")
        send(answer(msg))
    elif mode == "double_reply":
        send(answer(msg))
        send(answer(msg))
    elif mode == "oversized":
        send(json.dumps({"seq": msg["seq"], "action": "fold", "pad": "x" * 10_000}))
    elif mode == "slow_first":
        if requests == 1:
            time.sleep(1.0)
        send(answer(msg))
    elif mode == "spin":
        end = time.time() + 30
        while time.time() < end:
            pass
        send(answer(msg))
    elif mode == "stderr_flood":
        sys.stderr.write("e" * 1_000_000)
        sys.stderr.flush()
        send(answer(msg))
    else:  # "good", "no_flush", "chatty_startup"
        send(answer(msg))
