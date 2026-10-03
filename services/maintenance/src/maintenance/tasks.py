"""Maintenance task of a component from its MaintenanceInstructions submodel (IDTA 1.0, provisioned from the
manufacturer data): id, name, steps, spare parts and working time - shown in the user tasks of the
MaintenanceOrder process and in the recommendation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MaintenanceTask:
    maintenance_id: str
    name_en: str
    name_de: str
    steps: list[str] = field(default_factory=list)       # "10 Secure the robot cell: ..." (en)
    spare_parts: list[str] = field(default_factory=list)  # "FS-PG85-V50 Finger set ..."
    working_time: str = ""
    element: str = ""                                     # idShort of the task (reference target)

    def instructions(self) -> str:
        lines = [*self.steps]
        if self.spare_parts:
            lines.append("Spare parts: " + "; ".join(self.spare_parts))
        if self.working_time:
            lines.append("Estimated working time: " + self.working_time)
        return "\n".join(lines)


def fallback(component_name: str) -> MaintenanceTask:
    return MaintenanceTask("", f"Maintain {component_name}", f"{component_name} instand setzen")


def _children(element: dict) -> list[dict]:
    value = element.get("value")
    return value if isinstance(value, list) else []


def _child(elements: list[dict], id_short: str) -> dict:
    return next((e for e in elements if e.get("idShort") == id_short), {})


def _text(element: dict, lang: str = "en") -> str:
    value = element.get("value")
    if isinstance(value, list):  # MultiLanguageProperty
        texts = {v.get("language"): v.get("text", "") for v in value if isinstance(v, dict)}
        return texts.get(lang) or next(iter(texts.values()), "")
    return "" if value is None else str(value)


def from_submodel(submodel: dict, task_id_short: str) -> MaintenanceTask | None:
    """Reads one task (MaintenanceInstructionsForSpecificInterval element) and the spare part list."""
    elements = submodel.get("submodelElements") or []
    task = _child(elements, task_id_short)
    if not task:
        return None
    basic = _children(_child(_children(task), "BasicMaintenanceInformation"))
    steps = []
    for step in _step_elements(task):
        values = _children(step)
        steps.append(f"{_text(_child(values, 'MaintenanceStepID'))} "
                     f"{_text(_child(values, 'MaintenanceStepName'))}: "
                     f"{_text(_child(values, 'InstructionMaintenanceStep'))}")
    parts = [f"{_text(_child(_children(p), 'SparePartID'))} {_text(_child(_children(p), 'SparePartName'))}"
             for p in _children(_child(elements, "MaintenanceSparePartList"))]
    name = _child(basic, "NameOfMaintenance")
    return MaintenanceTask(_text(_child(basic, "MaintenanceID")), _text(name, "en"), _text(name, "de"),
                           steps, parts, _working_time(task), task_id_short)


def _step_elements(task: dict) -> list[dict]:
    steps = _child(_children(task), "ListMaintenanceSteps")
    return [s for s in _children(steps) if s.get("modelType") == "SubmodelElementCollection"]


def _working_time(task: dict) -> str:
    technicians = _children(_child(_children(task), "MaintenanceTechnicians"))
    total = _children(_child(technicians, "EstimatedTotalWorkingTime"))
    value = _text(_child(total, "ValueTotalEstimatedWorkingTime"))
    unit = _text(_child(total, "UnitValueTotalEstimatedWorkingTime"))
    return f"{value} {unit}".strip()
