"""Plain-subprocess backend. DEV ONLY, YOUR OWN BOTS ONLY.

There is no sandbox here: the bot runs as you, with your files and network.
Uploaded or untrusted bots run through ``docker.py`` inside the sandbox VM, never this.
CPU accounting is approximate (psutil) and freezing doesn't cover child processes.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
from pathlib import Path

import psutil


def bot_python() -> str:
    """The real interpreter, not the venv/uv launcher.

    On Windows a venv's python.exe is a trampoline that spawns the interpreter as a child,
    so the bot would be a grandchild we can't reliably suspend or meter. The base
    interpreter also keeps the dev venv's packages out of the bot's reach, closer to the
    sandbox (bots get stdlib only locally).
    """
    return getattr(sys, "_base_executable", None) or sys.executable


class LocalProcess:
    def __init__(self, argv: list[str], cwd: Path | None = None) -> None:
        self._popen = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.stdin = self._popen.stdin
        self.stdout = self._popen.stdout
        self.stderr = self._popen.stderr
        self._ps = psutil.Process(self._popen.pid)
        self._last_cpu_us = 0

    @classmethod
    def for_bot_dir(cls, bot_dir: str | Path) -> LocalProcess:
        bot_dir = Path(bot_dir).resolve()
        main = bot_dir / "main.py"
        if not main.is_file():
            raise FileNotFoundError(f"{main} not found")
        return cls([bot_python(), "-u", str(main)], cwd=bot_dir)

    def freeze(self) -> None:
        with contextlib.suppress(psutil.Error):  # dead: the reader will see EOF
            self._ps.suspend()

    def thaw(self) -> None:
        with contextlib.suppress(psutil.Error):
            self._ps.resume()

    def cpu_usage_us(self) -> int:
        with contextlib.suppress(psutil.Error):  # gone: keep the last reading
            t = self._ps.cpu_times()
            self._last_cpu_us = int((t.user + t.system) * 1_000_000)
        return self._last_cpu_us

    def poll(self) -> int | None:
        return self._popen.poll()

    def kill(self) -> None:
        if self._popen.poll() is None:
            self.thaw()
            self._popen.kill()

    def wait(self, timeout: float) -> int | None:
        try:
            return self._popen.wait(timeout)
        except subprocess.TimeoutExpired:
            return None
