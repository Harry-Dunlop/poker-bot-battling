"""Image smoke check. Runs INSIDE the sandbox image as if it were a bot.

Started by scripts/image_smoke.py with the production `docker run` flags.
Prints "SMOKE OK" and exits 0 only if every check passes. Stdlib + image libs only.
"""

import os
import socket
import sys

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def raises(fn, exc=OSError):
    try:
        fn()
    except exc:
        return True
    return False


def write(path):
    with open(path, "w") as f:
        f.write("x")


def status_field(name):
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith(name + ":"):
                return line.split()[1]
    return None


# Who and what
check("python 3.12", sys.version_info[:2] == (3, 12))
check("uid nobody", os.getuid() == 65534 and os.getgid() == 65534)
check("no capabilities", status_field("CapEff") == "0000000000000000")
check("no_new_privs", status_field("NoNewPrivs") == "1")
for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    check(f"{var}=1", os.environ.get(var) == "1")

# Filesystem
check("root fs read-only", raises(lambda: write("/pbb-smoke")))
check("bot dir read-only", raises(lambda: write("/bot/pbb-smoke")))
check("/tmp writable", not raises(lambda: write("/tmp/pbb-smoke")))


def exec_tmp():
    path = "/tmp/pbb-smoke.sh"
    with open(path, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(path, 0o755)
    os.execv(path, [path])  # only returns by raising


check("/tmp noexec", raises(exec_tmp))

# Network
check("no network", raises(lambda: socket.create_connection(("1.1.1.1", 53), timeout=2)))


# Libraries (the image is the allow-list)
def libs():
    import eval7
    import numba
    import numpy
    import scipy  # noqa: F401

    assert eval7.evaluate([eval7.Card(c) for c in ("Ah", "Kh", "Qh", "Jh", "Th")]) > 0
    assert numpy.ones(3).sum() == 3

    @numba.njit(cache=False)
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


check("libs import and run (eval7, numpy, scipy, numba)", not raises(libs, Exception))

if failures:
    print(f"SMOKE FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("SMOKE OK")
