"""Write policy for AAS sink elements (risk R5): discrete values are written at once when they change, numbers
at most every `min_interval` seconds and only outside a deadband; the latest pending value is flushed
later."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

Writer = Callable[[str, str, object], None]  # (submodel id, element path, value)


@dataclass
class _Sink:
    written: object = None
    written_at: float = -math.inf
    pending: object = None
    has_pending: bool = False


@dataclass
class SinkWriter:
    write: Writer
    min_interval: float = 1.0
    rel_deadband: float = 0.002   # 0.2 % of the last written value ...
    abs_deadband: float = 1e-6    # ... but at least this absolute change
    writes: int = 0
    errors: int = 0
    _sinks: dict[tuple[str, str], _Sink] = field(default_factory=dict)

    def offer(self, submodel: str, path: str, value: object, now: float) -> None:
        sink = self._sinks.setdefault((submodel, path), _Sink())
        if not self._significant(sink.written, value):
            sink.has_pending = False
            return
        if not isinstance(value, float) or now - sink.written_at >= self.min_interval:
            self._write(submodel, path, sink, value, now)
        else:
            sink.pending, sink.has_pending = value, True

    def flush(self, now: float) -> None:
        """Writes pending numeric values whose interval has elapsed."""
        for (submodel, path), sink in self._sinks.items():
            if sink.has_pending and now - sink.written_at >= self.min_interval:
                self._write(submodel, path, sink, sink.pending, now)

    def _significant(self, old: object, new: object) -> bool:
        if old is None or type(old) is not type(new):
            return True
        if isinstance(new, float):
            return abs(new - old) > max(self.abs_deadband, self.rel_deadband * abs(old))
        return new != old

    def _write(self, submodel: str, path: str, sink: _Sink, value: object, now: float) -> None:
        sink.has_pending = False
        try:
            self.write(submodel, path, value)
        except Exception:  # noqa: BLE001 - keep bridging other values; the next change retries
            self.errors += 1
            return
        sink.written, sink.written_at = value, now
        self.writes += 1
