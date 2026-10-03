"""Configuration of the condition monitoring (`infra/maintenance.json`): monitored components and the order
policy. Thresholds of the order policy can be changed at runtime (REST /api/settings)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def default_path() -> Path:
    return Path(os.environ.get("VF_REPO", Path(__file__).resolve().parents[4])) / "infra" / "maintenance.json"


@dataclass(frozen=True)
class Component:
    tag: str                    # component AAS (e.g. GR01)
    device: str                 # FMI instance / historian table that measures it (e.g. RB01)
    name_en: str
    name_de: str
    indicator: str              # degradation indicator (FMI output)
    unit: str
    limit: float                # indicator value at the end of the useful life
    cycles: str                 # operating cycle counter since the last part change (FMI output)
    fault: str = ""             # device output: failure caused by the degradation
    symptoms: dict[str, str] = field(default_factory=dict)  # ConditionMonitoring Symptoms idShort -> output
    reliability_set: str = ""   # suffix of the Reliability sets (Conditions<x>, Characteristics<x>)
    maintenance_task: str = ""  # idShort of the task in MaintenanceInstructions
    reset_parameter: str = ""   # parameter of the skill Maintain that confirms the part change
    alarm: int = 0              # advisory alarm code (infra/alarms.json, source MAINTENANCE)

    @property
    def variables(self) -> list[str]:
        """Outputs read from the historian / UNS (indicator, cycles, fault, symptoms)."""
        names = [self.cycles, self.indicator, *self.symptoms.values()]
        if self.fault:
            names.append(self.fault)
        return list(dict.fromkeys(names))


@dataclass
class Policy:
    rul_hours_threshold: float = 8.0
    health_index_gate: float = 0.85
    health_index_order: float = 0.25

    def to_dict(self) -> dict:
        return {"rulHoursThreshold": self.rul_hours_threshold, "healthIndexGate": self.health_index_gate,
                "healthIndexOrder": self.health_index_order}

    def update(self, body: dict) -> None:
        if "rulHoursThreshold" in body:
            self.rul_hours_threshold = max(0.0, float(body["rulHoursThreshold"]))
        if "healthIndexGate" in body:
            self.health_index_gate = min(1.0, max(0.0, float(body["healthIndexGate"])))
        if "healthIndexOrder" in body:
            self.health_index_order = min(1.0, max(0.0, float(body["healthIndexOrder"])))


@dataclass(frozen=True)
class Config:
    components: list[Component]
    policy: Policy
    interval_s: float = 10.0
    max_points: int = 200
    min_points: int = 6
    throughput_points: int = 20

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        data = json.loads((path or default_path()).read_text(encoding="utf-8"))
        history, order = data.get("history", {}), data.get("order", {})
        return cls([Component(**c) for c in data["components"]],
                   Policy(float(order.get("rul_hours_threshold", 8.0)),
                          float(order.get("health_index_gate", 0.85)),
                          float(order.get("health_index_order", 0.25))),
                   float(data.get("evaluation_interval_s", 10)), int(history.get("max_points", 200)),
                   int(history.get("min_points", 6)), int(history.get("throughput_points", 20)))

    def component(self, tag: str) -> Component | None:
        return next((c for c in self.components if c.tag.upper() == tag.upper()), None)
