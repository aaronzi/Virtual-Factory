"""Reads FMI 3.0 model descriptions (the single source of device interfaces)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

VAR_TAGS = ("Float64", "Int32", "UInt64", "Boolean", "String")
JSON_TYPES = {"Float64": "number", "Int32": "integer", "UInt64": "integer", "Boolean": "boolean", "String": "string"}
XSD_TYPES = {"Float64": "xs:double", "Int32": "xs:int", "UInt64": "xs:unsignedLong", "Boolean": "xs:boolean",
             "String": "xs:string"}


@dataclass(frozen=True)
class FmiVariable:
    name: str
    type: str
    causality: str
    variability: str
    unit: str
    description: str
    start: str
    min: str
    max: str

    @property
    def json_type(self) -> str:
        return JSON_TYPES[self.type]

    @property
    def xsd_type(self) -> str:
        return XSD_TYPES[self.type]


@dataclass(frozen=True)
class ModelDescription:
    model_name: str
    description: str
    version: str
    variables: tuple[FmiVariable, ...]

    def by_causality(self, causality: str) -> list[FmiVariable]:
        return [v for v in self.variables if v.causality == causality]

    def variable(self, name: str) -> FmiVariable:
        return next(v for v in self.variables if v.name == name)


def read_model_description(path: Path) -> ModelDescription:
    root = ET.parse(path).getroot()
    variables = []
    for el in root.find("ModelVariables"):
        if el.tag not in VAR_TAGS:
            continue
        start = el.get("start")
        if start is None and el.find("Start") is not None:
            start = el.find("Start").get("value")
        variables.append(FmiVariable(
            name=el.get("name"), type=el.tag, causality=el.get("causality", "local"),
            variability=el.get("variability", ""), unit=el.get("unit", ""),
            description=el.get("description", ""), start=start or "", min=el.get("min", ""), max=el.get("max", "")))
    return ModelDescription(root.get("modelName"), root.get("description", ""), root.get("version", "1.0.0"),
                            tuple(variables))
