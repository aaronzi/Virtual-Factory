"""Batching writer: samples of the same table, session and timestamp are merged into one line; a batch is
sent every `interval_s` or as soon as `max_lines` lines are pending. Robust against InfluxDB outages:
transient errors keep the lines and retry with exponential backoff (1 s ... 30 s); the buffer is bounded
(`max_buffer`, the oldest lines are dropped first). Rejected lines (HTTP 4xx) are dropped and counted."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

from vf_common.historian import InfluxError

from .lineprotocol import line

log = logging.getLogger("historian.batch")
Sender = Callable[[list[str]], None]


@dataclass
class Stats:
    samples: int = 0
    lines: int = 0
    batches: int = 0
    dropped: int = 0
    rejected: int = 0
    failures: int = 0


@dataclass
class BatchWriter:
    send: Sender
    interval_s: float = 0.5
    max_lines: int = 1000
    max_buffer: int = 200_000
    clock: Callable[[], float] = time.monotonic
    stats: Stats = field(default_factory=Stats)
    _buffer: OrderedDict = field(default_factory=OrderedDict)  # (table, session, ts) -> {field: value}
    _next_send: float = 0.0
    _backoff: float = 0.0

    def add(self, table: str, session: str, name: str, value: str, ts_ms: int) -> None:
        self.stats.samples += 1
        self._buffer.setdefault((table, session, ts_ms), {})[name] = value
        while len(self._buffer) > self.max_buffer:
            self._buffer.popitem(last=False)
            self.stats.dropped += 1

    @property
    def pending(self) -> int:
        return len(self._buffer)

    def due(self) -> bool:
        """A batch is due when the interval (or the retry backoff) has elapsed, or `max_lines` are pending."""
        if not self._buffer:
            return False
        if self.clock() >= self._next_send:
            return True
        return not self._backoff and len(self._buffer) >= self.max_lines

    def flush(self, force: bool = False) -> int:
        """Sends pending lines in chunks of `max_lines`; returns the number of lines written."""
        written = 0
        while self._buffer and (force or self.due()):
            keys = list(self._buffer)[:self.max_lines]
            lines = [line(t, {"session": s}, self._buffer[(t, s, ts)], ts) for t, s, ts in keys]
            if not self._send(lines):
                break
            for k in keys:
                del self._buffer[k]
            written += len(lines)
            self._next_send = self.clock() + self.interval_s
        return written

    def _send(self, lines: list[str]) -> bool:
        try:
            self.send(lines)
        except InfluxError as exc:
            if exc.transient:
                self.stats.failures += 1
                self._backoff = min(30.0, max(1.0, self._backoff * 2))
                self._next_send = self.clock() + self._backoff
                log.warning("InfluxDB unavailable (%s), %d lines buffered, retry in %.0f s", exc,
                            len(self._buffer), self._backoff)
                return False
            self.stats.rejected += len(lines)
            log.warning("InfluxDB rejected a batch of %d lines: %s", len(lines), exc)
            return True
        self._backoff = 0.0
        self.stats.lines += len(lines)
        self.stats.batches += 1
        return True
