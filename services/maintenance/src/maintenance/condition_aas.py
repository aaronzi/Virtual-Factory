"""The maintenance service's submodels in the component AAS (ADR-0029, ownership after ADR-0025):

    ConditionMonitoring (custom template)   health, RUL, symptoms, recommendation, open order - every
                                            evaluation
                                            (only changed values); MaintenanceRecords - after each order
    Reliability (IDTA 1.0)                  the observed field data sets Conditions<set>Observed /
                                            Characteristics<set>Observed (achieved cycles per part change,
                                            B10)
    MaintenanceInstructions (IDTA 1.0)      read only (task, steps, spare parts of the manufacturer)

Submodels are located via discovery and registry (ADR-0023); new elements are instantiated from the templates
(vf_common TemplateLibrary), so they carry the template's semantic ids.
"""

from __future__ import annotations

import logging
import math

from vf_common import ids
from vf_common.aas.instantiate import instantiate
from vf_common.aas.templates import TemplateLibrary
from vf_common.registry_aas import RegistryAas

from .advice import iso
from .monitor import ComponentState
from .prognosis import Design
from .tasks import MaintenanceTask, from_submodel

log = logging.getLogger("maintenance.aas")
WEIBULL_SHAPE = 3.0  # wear-out failures; B10 = eta (-ln 0.9)^(1/beta), eta = mean / Gamma(1 + 1/beta)


def b10_from_mean(mean_life: float, shape: float = WEIBULL_SHAPE) -> float:
    eta = mean_life / math.gamma(1.0 + 1.0 / shape)
    return eta * (-math.log(0.9)) ** (1.0 / shape)


def _no_ref(key: str) -> dict:
    raise LookupError(f"no reference expected ({key})")


class ConditionAas:
    def __init__(self, aas: RegistryAas, templates: TemplateLibrary):
        self.aas, self.templates = aas, templates
        self._ids: dict[tuple[str, str], str] = {}
        self._written: dict[tuple[str, str], object] = {}

    def submodel_id(self, tag: str, id_short: str) -> str:
        key = (tag, id_short)
        if key not in self._ids:
            self._ids[key] = self.aas.resolver.submodel_of_asset(ids.asset_id(tag), id_short).id
        return self._ids[key]

    # -- read (manufacturer data) --------------------------------------------------------------------

    def task(self, tag: str, task_id_short: str) -> MaintenanceTask | None:
        submodel = self.aas.get_submodel(self.submodel_id(tag, "MaintenanceInstructions"))
        return from_submodel(submodel or {}, task_id_short)

    def design(self, tag: str, set_name: str) -> Design:
        values = self.aas.get_value(self.submodel_id(tag, "Reliability"))
        conditions, characteristics = values.get(f"Conditions{set_name}", {}), \
            values.get(f"Characteristics{set_name}", {})
        return Design(float(conditions.get("UsefulLifeInNumberOfOperations") or 0),
                      float(characteristics.get("B10") or 0))

    # -- ConditionMonitoring -------------------------------------------------------------------------

    def update(self, state: ComponentState, recommendation: dict[str, str], threshold: float) -> None:
        tag, p = state.component.tag, state.prognosis
        sm_id = self.submodel_id(tag, "ConditionMonitoring")
        values: dict[str, object] = {"HealthState": state.health, "OpenMaintenanceOrder": state.order,
                                     "HealthIndicator.IndicatorName":
                                         f"{state.component.device}.{state.component.indicator}",
                                     "HealthIndicator.LimitValue": state.component.limit,
                                     "HealthIndicator.IndicatorUnit": state.component.unit,
                                     "RemainingUsefulLife.OrderThreshold": threshold}
        for name, variable in state.component.symptoms.items():
            if state.value(variable) is not None:
                values[f"Symptoms.{name}"] = state.value(variable)
        if p is not None:
            values |= _prognosis_values(p)
        changed = {k: v for k, v in values.items() if self._written.get((sm_id, k)) != v}
        for path, value in changed.items():
            self.aas.set_value(sm_id, path, value)
            self._written[(sm_id, path)] = value
        if self._written.get((sm_id, "Recommendation")) != recommendation:
            element = self.aas.get_element(sm_id, "Recommendation")
            element["value"] = [{"language": k, "text": v} for k, v in recommendation.items()]
            self.aas.put_element(sm_id, "Recommendation", element)
            self._written[(sm_id, "Recommendation")] = recommendation
        if changed:
            self.aas.set_value(sm_id, "LastUpdate", iso(state.evaluated))

    def add_record(self, tag: str, record: dict) -> list[dict]:
        """Appends a MaintenanceRecord; returns all records as {idShort: value}."""
        sm_id = self.submodel_id(tag, "ConditionMonitoring")
        built = instantiate(self.templates.get("ConditionMonitoring-1.0"), {"MaintenanceRecords": [record]},
                            sm_id, _no_ref).submodel
        new = next(e for e in built["submodelElements"] if e["idShort"] == "MaintenanceRecords")
        current = self.aas.get_element(sm_id, "MaintenanceRecords")
        current["value"] = (current.get("value") or []) + new["value"]
        self.aas.put_element(sm_id, "MaintenanceRecords", current)
        return [{p["idShort"]: p.get("value") for p in item.get("value") or []} for item in current["value"]]

    # -- Reliability (observed field data) -----------------------------------------------------------

    def update_reliability(self, tag: str, set_name: str, lives: list[float]) -> None:
        if not lives:
            return
        sm_id = self.submodel_id(tag, "Reliability")
        repo = self.aas.resolver.repository(self.aas.resolver.submodel(sm_id))
        submodel = repo.get_submodel(sm_id)
        mean = sum(lives) / len(lives)
        observed = instantiate(self.templates.get("Reliability-1.0"), {
            "NumberOfReliabilitySets": 0,
            "OperatingConditionsOfReliabilityCharacteristics": [{
                "_idShort": f"Conditions{set_name}Observed", "UsefulLifeInNumberOfOperations": round(mean, 1),
                "OtherOperatingConditions": f"Field data LINE01 (maintenance service): {len(lives)} part "
                                            f"change(s), mean {mean:.0f} cycles until the change; B10 from a "
                                            f"Weibull wear-out model with assumed shape {WEIBULL_SHAPE:g}"}],
            "ReliabilityCharacteristics": [{"_idShort": f"Characteristics{set_name}Observed",
                                            "B10": int(round(b10_from_mean(mean)))}]},
            sm_id, _no_ref).submodel["submodelElements"][1:]
        names = {e["idShort"] for e in observed}
        elements = [e for e in submodel["submodelElements"] if e["idShort"] not in names] + observed
        sets = sum(1 for e in elements if e["idShort"].startswith("Conditions"))
        for e in elements:
            if e["idShort"] == "NumberOfReliabilitySets":
                e["value"] = str(sets)
        submodel["submodelElements"] = elements
        repo.put_submodel(submodel)
        log.info("%s Reliability: observed set %sObserved (%d lives, mean %.0f cycles)", tag, set_name,
                 len(lives), mean)


def _prognosis_values(p) -> dict[str, object]:
    out: dict[str, object] = {"HealthIndex": round(p.health_index, 4),
                              "HealthIndicator.CurrentValue": p.value,
                              "RemainingUsefulLife.RulCycles": _finite(p.rul_cycles),
                              "RemainingUsefulLife.RulCyclesLowerBound": _finite(p.rul_cycles_low),
                              "RemainingUsefulLife.Confidence": round(p.confidence, 3),
                              "RemainingUsefulLife.Method": p.method,
                              "RemainingUsefulLife.DataPoints": p.points,
                              "RemainingUsefulLife.Throughput": round(p.throughput, 1)}
    if p.rul_hours is not None:
        out["RemainingUsefulLife.RulHours"] = _finite(p.rul_hours)
        out["RemainingUsefulLife.RulHoursLowerBound"] = _finite(p.rul_hours_low)
    if p.failure_time is not None:
        out["RemainingUsefulLife.PredictedFailureDate"] = iso(p.failure_time)
    return {k: v for k, v in out.items() if v is not None}


def _finite(x: float | None) -> float | None:
    return round(x, 3) if x is not None and math.isfinite(x) else None
