"""Example bot: random legal action, random raise size. Stdlib only."""

import json
import random
import sys

rng = random.Random()


def reply(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    msg = json.loads(line)
    kind = msg.get("type")
    if kind == "match_start":
        rng.seed(msg["match_id"] + str(msg["seat"]))
        reply({"ready": True})
    elif kind == "action_request":
        action = rng.choice(msg["legal"])
        out = {"seq": msg["seq"], "action": action}
        if action == "raise":
            out["amount"] = rng.randint(msg["min_raise"], msg["max_raise"])
        reply(out)
    elif kind == "match_end":
        break
