"""BotConnection: the engine's side of the walkie-talkie.

One per bot per match. It owns the bot's three pipes and enforces:
- engine speaks first; one reply per request, matched by ``seq``
- line cap, strict JSON, legal-action check (invalid -> engine folds)
- wall-clock cap and CPU budget per decision (timeout -> engine folds)
- startup phase measured but not charged
- the bot is frozen whenever it isn't THINKING (no pondering)
- crash / EOF / stops reading stdin -> forfeit
- stderr drained into a capped buffer so a chatty bot can't block or fill memory

The bot never decides anything: the engine re-validates every action it gets back.
"""

from __future__ import annotations

import contextlib
import queue
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from pbb.protocol import messages as m
from pbb.protocol.fsm import Effect, Event, State, step
from pbb.runner.base import BotProcess

POLL_S = 0.005  # how often to check the CPU meter while waiting for a reply

# Reader-thread events
_LINE, _OVERSIZED, _EOF = "line", "oversized", "eof"


@dataclass(frozen=True)
class Limits:
    cpu_budget_ms: int  # whole match, chess-clock style
    startup_ms: int  # uncharged init window (wall clock)
    decision_wall_ms: int = 10_000  # backstop for bots that sleep/block
    stderr_cap_bytes: int = 64 * 1024
    unread_stdin_cap_bytes: int = 64 * 1024  # bot not reading its input -> dead


@dataclass(frozen=True)
class Decision:
    action: m.Action | None  # None -> the engine folds for the bot
    outcome: str  # "ok" | "invalid" | "timeout" | "budget"
    cpu_ms: float
    detail: str = ""


class Forfeit(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class _Stderr:
    cap: int
    data: bytearray = field(default_factory=bytearray)
    dropped: int = 0


class BotConnection:
    def __init__(self, proc: BotProcess, limits: Limits) -> None:
        self.proc = proc
        self.limits = limits
        self.state = State.SPAWNED
        self.cpu_used_us = 0  # charged
        self.startup_cpu_us = 0  # measured, not charged
        self.flags: Counter[str] = Counter()  # protocol misbehaviour, for the bot author
        self.forfeit_reason: str | None = None
        self._seq = 0

        self._inbox: queue.Queue[tuple[str, bytes]] = queue.Queue(maxsize=256)
        self._outbox: queue.Queue[bytes | None] = queue.Queue()
        self._unwritten = 0
        self._unwritten_lock = threading.Lock()
        self._write_failed = threading.Event()
        self._stderr = _Stderr(limits.stderr_cap_bytes)

        self._threads = [
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._write_stdin, daemon=True),
            threading.Thread(target=self._drain_stderr, daemon=True),
        ]
        for t in self._threads:
            t.start()

    # --- public API ---------------------------------------------------------

    @property
    def cpu_used_ms(self) -> float:
        return self.cpu_used_us / 1000

    @property
    def stderr_text(self) -> str:
        return self._stderr.data.decode("utf-8", "replace")

    def start(self, match_start: dict[str, Any]) -> None:
        """Send match_start and wait for {"ready":true}. Raises Forfeit."""
        self._fire(Event.SEND_MATCH_START)
        self._send(match_start)
        cpu0 = self.proc.cpu_usage_us()
        self.proc.thaw()
        deadline = time.monotonic() + self.limits.startup_ms / 1000
        while True:
            kind, raw = self._next(deadline, cpu0=None, cpu_allow_us=None)
            if kind == _EOF:
                self._die("exited or closed stdout during startup")
            if kind == "timeout":
                self._fire(Event.STARTUP_TIMEOUT)
                self._forfeit("no ready before startup_ms")
            if kind == _LINE:
                try:
                    m.parse_ready(m.parse_line(raw))
                except m.ProtocolError:
                    self._fire(Event.STRAY_LINE)
                    self.flags["stray_line"] += 1
                    continue
                self._fire(Event.READY)
                self.proc.freeze()
                self.startup_cpu_us = self.proc.cpu_usage_us() - cpu0
                return
            # oversized during startup: just noise
            self._fire(Event.STRAY_LINE)
            self.flags["oversized"] += 1

    def request(self, **fields: Any) -> Decision:
        """Ask for one action. Fields are ``messages.action_request`` minus seq/time_bank_ms.

        Returns a Decision; ``action is None`` means the engine must fold. Raises Forfeit.
        """
        remaining_us = self.limits.cpu_budget_ms * 1000 - self.cpu_used_us
        if remaining_us <= 0:
            return Decision(None, "budget", 0.0, "CPU budget used up")

        self._drain_idle_lines()
        self._seq += 1
        req = m.action_request(seq=self._seq, time_bank_ms=remaining_us // 1000, **fields)

        self._fire(Event.SEND_REQUEST)
        self._send(req)
        cpu0 = self.proc.cpu_usage_us()
        self.proc.thaw()
        deadline = time.monotonic() + self.limits.decision_wall_ms / 1000

        while True:
            kind, raw = self._next(deadline, cpu0=cpu0, cpu_allow_us=remaining_us)
            if kind == _EOF:
                self._die("exited or closed stdout mid-decision")
            if kind == "timeout":
                self._fire(Event.TIMEOUT)
                return self._stop_clock(cpu0, None, "timeout", raw.decode())
            if kind == _OVERSIZED:
                self._fire(Event.INVALID_REPLY)
                return self._stop_clock(cpu0, None, "invalid", "line too long")
            try:
                obj = m.parse_line(raw)
            except m.ProtocolError:
                # Not JSON: treat as a stray debug print, keep waiting.
                self._fire(Event.STRAY_LINE)
                self.flags["stray_line"] += 1
                continue
            try:
                reply = m.parse_reply(obj)
            except m.ProtocolError as e:
                self._fire(Event.INVALID_REPLY)
                return self._stop_clock(cpu0, None, "invalid", str(e))
            if reply.seq < self._seq:
                self._fire(Event.STALE_REPLY)
                self.flags["stale_reply"] += 1
                continue
            if reply.seq > self._seq:
                self._fire(Event.INVALID_REPLY)
                return self._stop_clock(cpu0, None, "invalid", "seq from the future")
            try:
                m.check_legal(reply.action, req)
            except m.ProtocolError as e:
                self._fire(Event.INVALID_REPLY)
                return self._stop_clock(cpu0, None, "invalid", str(e))
            self._fire(Event.VALID_ACTION)
            return self._stop_clock(cpu0, reply.action, "ok")

    def notify(self, msg: dict[str, Any]) -> None:
        """Send an informational message (hand_result) while the bot is IDLE."""
        self._drain_idle_lines()
        self._fire(Event.SEND_NOTICE)
        self._send(msg)

    def finish(self, match_end: dict[str, Any], grace_s: float = 1.0) -> None:
        """Send match_end, let the bot exit, then make sure it's gone."""
        if self.state is not State.IDLE:
            self.close()
            return
        self._drain_idle_lines()
        self._fire(Event.SEND_MATCH_END)
        self._send(match_end)
        self._outbox.put(None)  # writer closes stdin after flushing
        self.proc.thaw()
        if self.proc.wait(grace_s) is None:
            self.proc.kill()
            self.proc.wait(grace_s)
        self._join()

    def close(self) -> None:
        """Hard stop, for cleanup paths. Safe to call any time."""
        self.proc.kill()
        self.proc.wait(1.0)
        self._outbox.put(None)
        self._join()

    def __enter__(self) -> BotConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        if self.proc.poll() is None:
            self.close()

    # --- internals ----------------------------------------------------------

    def _fire(self, event: Event) -> Effect:
        self.state, effect = step(self.state, event)
        return effect

    def _send(self, msg: dict[str, Any]) -> None:
        data = m.encode(msg)
        with self._unwritten_lock:
            self._unwritten += len(data)
            backlog = self._unwritten
        if backlog > self.limits.unread_stdin_cap_bytes:
            self._die("not reading stdin")
        self._outbox.put(data)

    def _stop_clock(
        self, cpu0: int, action: m.Action | None, outcome: str, detail: str = ""
    ) -> Decision:
        self.proc.freeze()
        used = max(0, self.proc.cpu_usage_us() - cpu0)
        self.cpu_used_us += used
        if outcome != "ok":
            self.flags[outcome] += 1
        return Decision(action, outcome, used / 1000, detail)

    def _next(
        self, deadline: float, cpu0: int | None, cpu_allow_us: int | None
    ) -> tuple[str, bytes]:
        """Next line/EOF from the bot, or ("timeout", reason) on wall clock or CPU budget."""
        while True:
            if self._write_failed.is_set():
                return _EOF, b""
            left = deadline - time.monotonic()
            if left <= 0:
                return "timeout", b"wall clock"
            try:
                return self._inbox.get(timeout=min(left, POLL_S))
            except queue.Empty:
                pass
            if (
                cpu0 is not None
                and cpu_allow_us is not None
                and self.proc.cpu_usage_us() - cpu0 > cpu_allow_us
            ):
                return "timeout", b"cpu budget"

    def _drain_idle_lines(self) -> None:
        """Lines that arrived while IDLE: late replies are stale, anything else is stray."""
        while True:
            try:
                kind, raw = self._inbox.get_nowait()
            except queue.Empty:
                return
            if kind == _EOF:
                self._die("exited or closed stdout")
            event, flag = Event.STRAY_LINE, "stray_line"
            if kind == _LINE:
                with contextlib.suppress(m.ProtocolError):
                    if m.parse_reply(m.parse_line(raw)).seq <= self._seq:
                        event, flag = Event.STALE_REPLY, "stale_reply"
            self._fire(event)
            self.flags[flag] += 1

    def _die(self, reason: str) -> None:
        if self.state not in (State.DONE, State.FORFEIT):
            self._fire(Event.DIED)
        self._forfeit(reason)

    def _forfeit(self, reason: str) -> None:
        self.forfeit_reason = reason
        self.proc.kill()
        self.proc.wait(1.0)
        self._outbox.put(None)
        raise Forfeit(reason)

    def _join(self) -> None:
        for t in self._threads:
            t.join(timeout=1.0)

    # --- pipe threads -------------------------------------------------------

    def _read_stdout(self) -> None:
        out = self.proc.stdout
        cap = m.MAX_LINE_BYTES
        try:
            while True:
                line = out.readline(cap)
                if not line:
                    break
                if line.endswith(b"\n"):
                    self._inbox.put((_LINE, line.rstrip(b"\r\n")))
                    continue
                if len(line) < cap:  # EOF in the middle of a line
                    self._inbox.put((_LINE, line))
                    continue
                # Too long: report once, skip to the end of the line.
                self._inbox.put((_OVERSIZED, b""))
                while True:
                    chunk = out.readline(cap)
                    if not chunk or chunk.endswith(b"\n"):
                        break
                if not chunk:
                    break
        except (OSError, ValueError):
            pass
        self._inbox.put((_EOF, b""))

    def _write_stdin(self) -> None:
        pipe = self.proc.stdin
        while True:
            data = self._outbox.get()
            if data is None:
                with contextlib.suppress(OSError, ValueError):
                    pipe.close()
                return
            try:
                pipe.write(data)
                pipe.flush()
            except (OSError, ValueError):
                self._write_failed.set()
                return
            with self._unwritten_lock:
                self._unwritten -= len(data)

    def _drain_stderr(self) -> None:
        err, buf = self.proc.stderr, self._stderr
        try:
            while chunk := err.read1(4096):
                room = buf.cap - len(buf.data)
                buf.data += chunk[:room]
                buf.dropped += max(0, len(chunk) - room)
        except (OSError, ValueError):
            pass
