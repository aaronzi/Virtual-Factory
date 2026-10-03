"""Health index and remaining useful life (RUL) of one component - pure functions, no I/O.

Model (explainable on purpose): abrasive wear grows linearly with the operating cycles (Archard), so the
degradation indicator x (e.g. finger wear in m) is fitted against the cycle counter c since the last part
change by ordinary least squares, x = a + b c. With the limit L:

    health index  HI   = 1 - x_now / L                      (clipped to 0..1)
    RUL (median)  RUL  = (L - x_fit(c_now)) / b             cycles
    lower bound   RUL- = (L - x_fit(c_now)) / (b + z s_b)   one-sided 90 % (z = 1.2816, s_b = std. error of b)
    hours         RUL / throughput,  throughput = cycles per hour over the latest samples
                  (measurement time base)
    confidence    R^2 x min(1, n / (2 n_min))

The trend is used only if it is significant (n >= n_min and t = b / s_b >= 3). Otherwise - new parts, or the
indicator noise hides the slow design wear - the design rate L / useful life is used (useful life from the
Reliability submodel; lower bound with the B10 life) with a low confidence (method DesignRate).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Z90 = 1.2816       # one-sided 90 % quantile of the normal distribution
T_SIGNIFICANT = 3.0
DESIGN_CONFIDENCE = 0.2


@dataclass(frozen=True)
class Sample:
    t: float        # measurement time, Unix seconds (UNS timestamp base)
    cycles: int
    value: float    # degradation indicator


@dataclass(frozen=True)
class Design:
    useful_life: float      # cycles until the limit (median)
    b10: float = 0.0        # cycles until 10 % have reached the limit (0 = unknown)


@dataclass(frozen=True)
class Fit:
    intercept: float
    slope: float
    slope_se: float
    r2: float
    n: int

    @property
    def t_stat(self) -> float:
        return self.slope / self.slope_se if self.slope_se > 0 else (math.inf if self.slope > 0 else 0.0)


@dataclass(frozen=True)
class Prognosis:
    health_index: float
    value: float
    cycles: int
    rul_cycles: float
    rul_cycles_low: float
    rul_hours: float | None        # None: no throughput (line not producing)
    rul_hours_low: float | None
    failure_time: float | None     # Unix seconds of reaching the limit (lower bound), None without throughput
    confidence: float
    method: str                    # TrendFit | DesignRate
    points: int
    throughput: float              # cycles per hour
    rate: float                    # indicator per cycle used for the prognosis
    time: float = 0.0              # measurement time of the latest sample (Unix seconds)

    def to_dict(self) -> dict:
        return {"healthIndex": round(self.health_index, 4), "value": self.value, "cycles": self.cycles,
                "rulCycles": _round(self.rul_cycles), "rulCyclesLow": _round(self.rul_cycles_low),
                "rulHours": _round(self.rul_hours), "rulHoursLow": _round(self.rul_hours_low),
                "failureTime": self.failure_time, "confidence": round(self.confidence, 3),
                "method": self.method, "points": self.points, "throughput": round(self.throughput, 1),
                "rate": self.rate, "time": self.time}


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def since_last_change(samples: list[Sample]) -> list[Sample]:
    """Samples (oldest first) after the last part change: the cycle counter restarts (drops)."""
    start = 0
    for i in range(1, len(samples)):
        if samples[i].cycles < samples[i - 1].cycles:
            start = i
    return samples[start:]


def linear_fit(xs: list[float], ys: list[float]) -> Fit | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    sse = sum((y - intercept - slope * x) ** 2 for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    se = math.sqrt(sse / (n - 2) / sxx) if n > 2 else math.inf
    r2 = 1.0 - sse / syy if syy > 0 else 0.0
    return Fit(intercept, slope, se, max(0.0, r2), n)


def throughput(samples: list[Sample], points: int = 20) -> float:
    """Cycles per hour over the latest `points` samples."""
    recent = samples[-points:]
    if len(recent) < 2 or recent[-1].t <= recent[0].t:
        return 0.0
    return max(0.0, (recent[-1].cycles - recent[0].cycles) / (recent[-1].t - recent[0].t) * 3600.0)


def estimate(samples: list[Sample], limit: float, design: Design, min_points: int = 6,
             throughput_points: int = 20) -> Prognosis | None:
    """Prognosis from the samples since the last part change (oldest first); None without samples."""
    samples = since_last_change(samples)
    if not samples or limit <= 0:
        return None
    now = samples[-1]
    hi = min(1.0, max(0.0, 1.0 - now.value / limit))
    fit = linear_fit([s.cycles for s in samples], [s.value for s in samples]) \
        if len(samples) >= min_points else None
    if fit is not None and fit.slope > 0 and fit.t_stat >= T_SIGNIFICANT:
        remaining = max(0.0, limit - (fit.intercept + fit.slope * now.cycles))
        rul, rul_low = remaining / fit.slope, remaining / (fit.slope + Z90 * fit.slope_se)
        confidence, method, rate = fit.r2 * min(1.0, fit.n / (2 * min_points)), "TrendFit", fit.slope
    else:
        rate = limit / design.useful_life if design.useful_life > 0 else 0.0
        rate_low = limit / design.b10 if design.b10 > 0 else rate
        remaining = max(0.0, limit - now.value)
        rul = remaining / rate if rate > 0 else math.inf
        rul_low = remaining / rate_low if rate_low > 0 else rul
        confidence, method = DESIGN_CONFIDENCE, "DesignRate"
    per_hour = throughput(samples, throughput_points)
    hours = rul / per_hour if per_hour > 0 else None
    hours_low = rul_low / per_hour if per_hour > 0 else None
    failure = now.t + hours_low * 3600.0 if hours_low is not None and math.isfinite(hours_low) else None
    return Prognosis(hi, now.value, now.cycles, rul, rul_low, hours, hours_low, failure, confidence, method,
                     len(samples), per_hour, rate, now.t)
