"""What the connection needs from a running bot, whatever is hosting it."""

from __future__ import annotations

from typing import IO, Protocol


class BotProcess(Protocol):
    """A started bot. ``local.py`` (dev, own bots) and ``docker.py`` (gVisor) implement this."""

    stdin: IO[bytes]
    stdout: IO[bytes]
    stderr: IO[bytes]

    def freeze(self) -> None:
        """Stop the bot using any CPU. Must not return until it is actually stopped."""

    def thaw(self) -> None: ...

    def cpu_usage_us(self) -> int:
        """Cumulative CPU time (user + system) used by the bot, in microseconds."""

    def poll(self) -> int | None:
        """Exit code, or None if still running."""

    def kill(self) -> None:
        """Hard stop. Safe to call more than once."""

    def wait(self, timeout: float) -> int | None:
        """Exit code, or None if still running after ``timeout`` seconds."""
