"""Health index and remaining useful life (pure prognosis): trend fit with lower bound, design-rate fallback,
part changes, throughput."""

from __future__ import annotations

import math
import random

import pytest

from maintenance.condition_aas import b10_from_mean
from maintenance.prognosis import Design, Sample, estimate, linear_fit, since_last_change, throughput

LIMIT = 1e-3
DESIGN = Design(useful_life=2_500_000, b10=2_000_000)


def _wear(n: int, rate: float, noise: float = 3e-6, takt_s: float = 12.0, seed: int = 1) -> list[Sample]:
    rng = random.Random(seed)
    return [Sample(1_000.0 + i * takt_s, i, max(0.0, rate * i + rng.gauss(0.0, noise)))
            for i in range(1, n + 1)]


def test_linear_wear_gives_a_trend_prognosis_with_a_conservative_lower_bound():
    p = estimate(_wear(8, 4.5e-5), LIMIT, DESIGN)
    assert p.method == "TrendFit" and p.points == 8
    assert p.health_index == pytest.approx(1 - 8 * 4.5e-5 / LIMIT, abs=0.01)
    assert p.rul_cycles == pytest.approx(LIMIT / 4.5e-5 - 8, abs=1.0)  # 22.2 - 8 grips
    assert p.rul_cycles_low < p.rul_cycles
    assert p.throughput == pytest.approx(300.0)  # one grip every 12 s
    assert p.rul_hours_low == pytest.approx(p.rul_cycles_low / 300.0)
    assert p.failure_time == pytest.approx(1_096.0 + p.rul_hours_low * 3600)
    assert 0.6 < p.confidence <= 1.0


def test_design_wear_hidden_in_the_noise_falls_back_to_the_design_rate():
    p = estimate(_wear(60, 4e-10), LIMIT, DESIGN)
    assert p.method == "DesignRate" and p.confidence == 0.2
    assert p.rul_cycles == pytest.approx(2_500_000, rel=0.02)
    assert p.rul_cycles_low == pytest.approx(2_000_000, rel=0.02), "B10 life"
    assert p.rul_hours > 6000, "no maintenance order in normal operation"


def test_too_few_points_and_no_data():
    assert estimate([], LIMIT, DESIGN) is None
    assert estimate(_wear(4, 4.5e-5), LIMIT, DESIGN).method == "DesignRate"


def test_samples_before_the_last_part_change_are_ignored():
    old = _wear(10, 8e-5)
    new = [Sample(2_000.0 + i, i, 1e-6 * i) for i in range(0, 3)]
    assert since_last_change(old + new) == new
    p = estimate(old + new, LIMIT, DESIGN)
    assert p.points == 3 and p.health_index > 0.99


def test_health_index_is_clipped_and_worn_parts_have_no_life_left():
    p = estimate(_wear(10, 1.3e-4, noise=0.0), LIMIT, DESIGN)
    assert p.health_index == 0.0 and p.rul_cycles == 0.0 and p.rul_cycles_low == 0.0


def test_fit_and_throughput_helpers():
    fit = linear_fit([1, 2, 3, 4], [2.0, 4.0, 6.0, 8.0])
    assert fit.slope == pytest.approx(2.0) and fit.r2 == pytest.approx(1.0) and math.isinf(fit.t_stat)
    assert linear_fit([1, 1, 1], [1.0, 2.0, 3.0]) is None
    assert throughput([Sample(0, 0, 0), Sample(3600, 250, 0)]) == 250.0
    assert throughput([Sample(0, 0, 0)]) == 0.0


def test_b10_from_the_mean_life_with_a_wear_out_weibull_model():
    assert b10_from_mean(1000.0) == pytest.approx(529.0, abs=1.0)
