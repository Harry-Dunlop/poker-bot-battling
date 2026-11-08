"""Minimal example bot: checks when it can, otherwise calls. Stdlib only.

Protocol: read one JSON line at a time from stdin; reply with exactly one line,
and flush, only when asked (match_start -> ready, action_request -> action).
"""

import json
import sys


def reply(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    msg = json.loads(line)
    kind = msg.get("type")
    if kind == "match_start":
        reply({"ready": True})
    elif kind == "action_request":
        legal = msg["legal"]
        action = "check" if "check" in legal else "call" if "call" in legal else "fold"
        reply({"seq": msg["seq"], "action": action})
    elif kind == "match_end":
        break
    # hand_result: nothing to do
