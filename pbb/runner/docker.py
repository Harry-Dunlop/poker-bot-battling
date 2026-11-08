"""gVisor sandbox backend (design-doc §4.1). Runs on the runner box / throwaway VM only.

Linux + cgroup v2 + Docker with the ``runsc`` runtime required. Untested until M4:
the cgroup path below is an unverified assumption (claude-context "Unverified assumptions").
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# Must be one path segment of safe chars: these end up in a container name and a mount.
_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMBA_NUM_THREADS": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}


@dataclass(frozen=True)
class SandboxSpec:
    image: str = "bot-python-standard:3.12"
    memory: str = "512m"
    cpus: str = "1"
    pids_limit: int = 64
    tmpfs_size: str = "16m"
    runtime: str = "runsc"


STANDARD = SandboxSpec()
OPEN = SandboxSpec(image="bot-python-open:3.12", memory="2g")


def docker_run_args(
    *, match_id: str, seat: int, bot_id: str, bots_root: Path, spec: SandboxSpec, cidfile: Path
) -> list[str]:
    """The exact `docker run` from design-doc §4.1. Pure function so it can be unit-tested."""
    for name, value in (("match_id", match_id), ("bot_id", bot_id)):
        if not _SAFE.match(value):
            raise ValueError(f"unsafe {name}: {value!r}")
    if seat not in (0, 1):
        raise ValueError("seat must be 0 or 1")
    env = [arg for k, v in THREAD_ENV.items() for arg in ("-e", f"{k}={v}")]
    return [
        "docker", "run", "-i", "--rm",
        "--name", f"bot-{match_id}-{seat}",
        "--cidfile", str(cidfile),
        f"--runtime={spec.runtime}",
        "--network=none",
        "--read-only",
        "--tmpfs", f"/tmp:size={spec.tmpfs_size},noexec,nosuid,nodev",
        f"--memory={spec.memory}", f"--memory-swap={spec.memory}",
        f"--cpus={spec.cpus}", f"--pids-limit={spec.pids_limit}",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--user", "65534:65534",
        "-v", f"{bots_root / bot_id}:/bot:ro",
        "-w", "/bot",
        *env,
        spec.image,
        "python", "-u", "/bot/main.py",
    ]  # fmt: skip


class DockerProcess:
    """One sandboxed bot. Freezes via cgroup.freeze (never `docker pause`); CPU from cpu.stat."""

    CGROUP_ROOT = Path("/sys/fs/cgroup/system.slice")  # UNVERIFIED: find the real one in M4

    def __init__(
        self,
        *,
        match_id: str,
        seat: int,
        bot_id: str,
        bots_root: Path,
        spec: SandboxSpec = STANDARD,
        cgroup_root: Path | None = None,
        cid_timeout_s: float = 10.0,
    ) -> None:
        assert_linux()
        self._name = f"bot-{match_id}-{seat}"
        tmpdir = Path(tempfile.mkdtemp(prefix="pbb-cid-"))
        cidfile = tmpdir / "cid"  # docker refuses to overwrite an existing cidfile
        argv = docker_run_args(
            match_id=match_id,
            seat=seat,
            bot_id=bot_id,
            bots_root=bots_root,
            spec=spec,
            cidfile=cidfile,
        )
        self._popen = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.stdin = self._popen.stdin
        self.stdout = self._popen.stdout
        self.stderr = self._popen.stderr
        self._last_cpu_us = 0
        try:
            cid = self._wait_for_cid(cidfile, cid_timeout_s)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        self._cgroup = (cgroup_root or self.CGROUP_ROOT) / f"docker-{cid}.scope"

    def _wait_for_cid(self, cidfile: Path, timeout_s: float) -> str:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if cidfile.exists() and (cid := cidfile.read_text().strip()):
                return cid
            if self._popen.poll() is not None:
                break
            time.sleep(0.01)
        self.kill()
        raise RuntimeError("container did not start")

    def _write(self, name: str, value: str) -> None:
        (self._cgroup / name).write_text(value)

    def freeze(self) -> None:
        try:
            self._write("cgroup.freeze", "1")
            # Freezing is asynchronous; wait until the kernel says it's done.
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                if "frozen 1" in (self._cgroup / "cgroup.events").read_text():
                    return
                time.sleep(0.0005)
        except OSError:
            pass  # container gone; the reader will see EOF

    def thaw(self) -> None:
        with contextlib.suppress(OSError):
            self._write("cgroup.freeze", "0")

    def cpu_usage_us(self) -> int:
        try:
            for line in (self._cgroup / "cpu.stat").read_text().splitlines():
                key, _, val = line.partition(" ")
                if key == "usage_usec":
                    self._last_cpu_us = int(val)
                    break
        except OSError:
            pass
        return self._last_cpu_us

    def poll(self) -> int | None:
        return self._popen.poll()

    def kill(self) -> None:
        if self._popen.poll() is None:
            self.thaw()  # a frozen container can't be killed cleanly
            subprocess.run(
                ["docker", "kill", self._name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            self._popen.kill()

    def wait(self, timeout: float) -> int | None:
        try:
            return self._popen.wait(timeout)
        except subprocess.TimeoutExpired:
            return None


def assert_linux() -> None:
    if os.name != "posix" or not Path("/sys/fs/cgroup/cgroup.controllers").exists():
        raise RuntimeError("DockerProcess needs Linux with cgroup v2 (the runner VM)")
