"""Run images/smoke/main.py inside a built sandbox image with the production flags.

CI only (Linux + Docker). Usage:
    docker build -t bot-python-standard:3.12 images/standard
    uv run python scripts/image_smoke.py [--runtime runc|runsc]

Uses our own check script, never an uploaded bot. GitHub's runners have no gVisor,
so CI swaps the runtime to runc; every other flag is the real one.
"""

from __future__ import annotations

import argparse
import dataclasses
import subprocess
import sys
import tempfile
from pathlib import Path

from pbb.runner.docker import STANDARD, docker_run_args

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", default="runc")
    ap.add_argument("--image", default=STANDARD.image)
    opts = ap.parse_args()
    spec = dataclasses.replace(STANDARD, runtime=opts.runtime, image=opts.image)
    with tempfile.TemporaryDirectory() as tmp:
        argv = docker_run_args(
            match_id="smoke",
            seat=0,
            bot_id="smoke",
            bots_root=ROOT / "images",
            spec=spec,
            cidfile=Path(tmp) / "cid",
        )
        proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    ok = proc.returncode == 0 and proc.stdout.rstrip().endswith("SMOKE OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
