"""Energy allocation on recorded series (pure functions, no I/O).

UNS telemetry is published on change, so a recorded series is a step function (sample and hold). A `Series` is
a time-sorted list of (Unix seconds, value); its first point may lie before the integration interval and then
gives the value at the interval start."""

from __future__ import annotations

Series = list[tuple[float, float]]


def value_at(series: Series, t: float) -> float | None:
    """Value held at time t (last sample at or before t); None before the first sample."""
    value = None
    for ts, v in series:
        if ts > t:
            break
        value = v
    return value


def integrate(series: Series, t0: float, t1: float, divisor: Series | None = None) -> float:
    """Integral of series(t) / max(1, divisor(t)) over [t0, t1] in value x seconds (W -> J). Without a sample
    before t0 the series counts as 0 until its first sample."""
    if t1 <= t0:
        return 0.0
    points = {t0, t1} | {t for t, _ in series if t0 < t < t1}
    if divisor:
        points |= {t for t, _ in divisor if t0 < t < t1}
    edges = sorted(points)
    total = 0.0
    for a, b in zip(edges, edges[1:]):
        share = max(1.0, value_at(divisor, a) or 1.0) if divisor else 1.0
        total += (value_at(series, a) or 0.0) * (b - a) / share
    return total


def difference(series: Series, t0: float, t1: float) -> float:
    """Increase of a counter (e.g. AirConsumed) over [t0, t1]; 0 if it is unknown or decreased (reset)."""
    v0, v1 = value_at(series, t0), value_at(series, t1)
    if v0 is None or v1 is None or v1 < v0:
        return 0.0
    return v1 - v0


def counter_difference(minuend: Series, subtrahend: Series) -> Series:
    """Step function minuend(t) - subtrahend(t), e.g. parts in process = released - sorted."""
    out: Series = []
    for t in sorted({t for t, _ in minuend} | {t for t, _ in subtrahend}):
        out.append((t, (value_at(minuend, t) or 0.0) - (value_at(subtrahend, t) or 0.0)))
    return out


def run_start(series: Series, t: float, floor: float) -> float:
    """Start of the run of equal values that ends just before t (e.g. the previous release of a cell: the time
    its release counter took the value held before t); repeated samples with the same value (republished
    state) do not start a new run. Never earlier than `floor`."""
    before = [(ts, v) for ts, v in series if ts < t]
    if not before:
        return floor
    start, held = before[-1]
    for ts, v in reversed(before):
        if v != held:
            break
        start = ts
    return max(start, floor)
