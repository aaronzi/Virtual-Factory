"""Production-based PCF with synthetic power series (no servers): allocation, historian queries, loss
allocation and the CarbonFootprint breakdown of the workpiece AAS."""

from __future__ import annotations

import re

import pytest

from provisioner.build import BuildContext, load_assets
from sustainability.allocation import counter_difference, difference, integrate, run_start, value_at
from sustainability.carbon import EnergyIntensity, FootprintCalculator, LossAllocation, PartFootprint
from sustainability.footprint_aas import FootprintWriter
from sustainability.process_energy import ProcessEnergy, _ts, parse, power_tables
from sustainability.suppliers import BomLine, ComponentFootprint

T0 = parse("2026-10-03T10:00:00Z")


def test_step_integration_and_sharing():
    power = [(T0 - 5, 100.0), (T0 + 10, 200.0)]          # 100 W held from before t0, 200 W from t0+10
    assert integrate(power, T0, T0 + 20) == pytest.approx(100 * 10 + 200 * 10)
    parts = [(T0 - 1, 1.0), (T0 + 5, 2.0), (T0 + 15, 1.0)]  # a second part on the line during [5, 15)
    assert integrate(power, T0, T0 + 20, parts) == pytest.approx(500 + 250 + 500 + 1000)
    assert integrate([(T0 + 5, 10.0)], T0, T0 + 10) == pytest.approx(50)  # unknown before the first sample
    assert value_at(power, T0) == 100.0 and value_at(power, T0 - 10) is None


def test_counters_and_cycle_start():
    air = [(T0 - 3, 100.0), (T0 + 4, 105.0)]
    assert difference(air, T0, T0 + 10) == pytest.approx(5.0) and difference(air, T0 + 10, T0) == 0.0
    in_process = counter_difference([(T0, 3.0), (T0 + 2, 4.0)], [(T0 - 9, 1.0), (T0 + 8, 2.0)])
    assert in_process == [(T0 - 9, -1.0), (T0, 2.0), (T0 + 2, 3.0), (T0 + 8, 2.0)]
    releases = [(T0 - 40, 6.0), (T0 - 12, 7.0), (T0 - 5, 7.0), (T0, 8.0)]  # republished 7 at T0-5
    assert run_start(releases, T0, T0 - 600) == T0 - 12
    assert run_start(releases, T0, T0 - 10) == T0 - 10


class _Influx:
    """Answers the two query shapes of ProcessEnergy from synthetic series {(table, column): Series}."""

    def __init__(self, data: dict):
        self.data, self.queries = data, 0

    def query(self, sql: str) -> list[dict]:
        self.queries += 1
        if "max(time)" in sql:
            latest = max(t for t, _ in self.data[("plc01", "sorted_count")])
            return [{"t": _ts(latest).strip("'")}]
        table, column = re.search(r'FROM "(\w+)"', sql)[1], re.search(r'"(\w+)" AS v', sql)[1]
        t0, t1 = (parse(x) for x in re.findall(r"time >= '([^']+)' AND time <= '([^']+)'", sql)[0])
        series = self.data.get((table, column), [])
        before = [p for p in series if p[0] < t0][-1:]
        rows = before + [p for p in series if t0 <= p[0] <= t1]
        return [{"time": _ts(t).strip("'").rstrip("Z"), "v": v} for t, v in rows]


def _line(hold_s: float = 0.0) -> dict:
    """AC01 at 300 W idle / 1500 W while assembling; CV01 at 100 W; one part released at T0, sorted at
    T0 + 20 + hold_s; a second part on the line during [T0+5, T0+15)."""
    return {("ac01", "release_count"): [(T0 - 600, 0.0), (T0 - 12, 1.0), (T0, 2.0)],
            ("ac01", "power"): [(T0 - 12, 1500.0)],
            ("ac01", "air_consumption"): [(T0 - 12, 5.0), (T0, 10.0)],
            ("plc01", "sorted_count"): [(T0 - 600, 0.0), (T0 + 5, 1.0), (T0 + 20 + hold_s, 2.0)],
            ("cv01", "power"): [(T0 - 600, 100.0)]}


def _v(hold_s: float = 0.0, container: int = 1) -> dict:
    return {"serial": "PC3280-2026-000002", "session": "S-1", "container": container,
            "releasedAt": _ts(T0).strip("'"), "sortedAt": _ts(T0 + 20 + hold_s).strip("'")}


def test_power_tables_from_the_asset_data():
    tables = power_tables(load_assets(BuildContext().repo / "aas" / "data"))
    assert tables == ["cv01", "lb01", "lb02", "qs01", "rb01", "sl01"]  # no PLC01/KLT (no power), no AC01


def test_process_energy_from_the_historian():
    energy = ProcessEnergy(_Influx(_line()), ["cv01"]).for_part(_v())
    assert energy.cycle_s == pytest.approx(12) and energy.residence_s == pytest.approx(20)
    assert energy.cell_kwh == pytest.approx(1500 * 12 / 3.6e6)
    assert energy.air_nl == pytest.approx(5.0)
    # parts in process: 1 (released 2 - sorted 1) ... the previous part counted until T0+5
    assert energy.line_kwh == pytest.approx((100 * 5 / 2 + 100 * 15) / 3.6e6)


class _Static:
    """Supplier source with one declared PCF per component (batch ignored)."""

    def footprint(self, line, batch):
        return ComponentFootprint(3.9, "test")


class _Calculator(FootprintCalculator):
    def __init__(self, aas_url, energy, intensity):
        super().__init__(aas_url, energy, intensity, _Static())

    def static(self):
        return [BomLine("Barrel", 1.0, "x")], 0.363, 0.12


def test_footprint_grows_with_residence_time_and_carries_losses():
    def calc(hold):
        return _Calculator("x", ProcessEnergy(_Influx(_line(hold)), ["cv01"]), EnergyIntensity())

    normal, held = calc(0).part(_v()), calc(120).part(_v(120))
    assert normal.method == held.method == "historian"
    assert normal.air_kwh == pytest.approx(5 * 0.12 / 1000)
    cell_kwh = 1500 * 12 / 3.6e6 - normal.air_kwh
    assert normal.electricity_kwh == pytest.approx(cell_kwh + (250 + 1500) / 3.6e6)
    assert held.total - normal.total == pytest.approx(100 * 120 / 3.6e6 * 0.363)
    losses = LossAllocation()
    reject = losses.allocate("S-1", PartFootprint(3.9, 0.02, 0.001, 0.363, rejected=True))
    good = [losses.allocate("S-1", PartFootprint(3.9, 0.02, 0.001, 0.363)) for _ in range(2)]
    assert reject.loss_share == 0 and good[0].loss_share == pytest.approx(reject.own)
    assert good[1].loss_share == pytest.approx(reject.own / 2)
    assert losses.allocate("S-2", PartFootprint(3.9, 0.02, 0.0, 0.363)).loss_share == 0.0


def test_fallback_without_historian():
    class _Down:
        def for_part(self, v):
            from vf_common.historian import InfluxError
            raise InfluxError("connection refused", transient=True)

    fp = _Calculator("x", _Down(), EnergyIntensity(fallback_kwh=0.004)).part(_v())
    assert fp.method == "fallback" and fp.electricity_kwh == 0.004
    assert fp.total == pytest.approx(3.9 + 0.004 * 0.363)


def test_carbon_footprint_submodel_of_the_sustainability_service():
    writer = FootprintWriter(aas=None, ctx=BuildContext())
    fp = PartFootprint(3.9004, 0.021, 0.0006, 0.363, rejected=True, residence_s=19.0)
    sm, cds = writer.build("PC3280-2026-000777", fp, "2026-10-03T10:00:19.000Z")
    assert sm["id"].endswith("/sm/WP_PC3280_2026_000777/CarbonFootprint/1") and cds
    entries = sm["submodelElements"][0]["value"]
    values = [{e["idShort"]: e.get("value") for e in entry["value"]} for entry in entries]
    assert [float(x["PcfCO2eq"]) for x in values] == [round(fp.total, 4), 3.9004, round(fp.manufacturing, 4)]
    assert values[2]["ElectricalEnergy"] == "0.021" and values[2]["LineResidenceTime"] == "19.0"
    assert values[0]["PublicationDate"] == "2026-10-03T10:00:19+00:00"
    assert "rejected unit" in entries[0]["description"][0]["text"]
