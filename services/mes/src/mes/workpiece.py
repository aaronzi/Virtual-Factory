"""Workpiece instance AAS from the blueprint (aas/data/blueprints/workpiece_instance.yaml) and the data
collected along the process; it is the item-level digital product passport of the part (ADR-0021,
passport.py). The AAS grows with the life cycle (stages):

    released   nameplate, DPP metadata, executed processes OP10-OP70 (assembly cell report incl. component
               lots), contacts, as-built BoM, material composition, circularity (recycled content per lot),
               location
    inspected  + OP75/OP80, QualityInspection, measurement values, as-built technical data
    packed     + OP90, run completed, handover documents (good parts: inspection certificate), location in
               the KLT; the CarbonFootprint submodel is added by the sustainability service (pcf-calculate)
    lost       run aborted (part did not reach the next station), passport inactive

DPP status (DppMetadata.dppStatus, EN 18223): Inactive while the unit is in production and for rejected or
lost units (never placed on the market), Active once a good unit is packed (shipped); Archived is reserved for
the end of the product's life and not reached in the simulation. Shipped passports survive new sessions
(store.py).
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from provisioner.build import REPO, load_yaml

from . import cell_data, passport
from .lots import lots_for
from .passport import values_of as _submodel
from .quality import Verdict

BLUEPRINT_SERIAL = "PC3280-2026-000123"
BLUEPRINT_RELEASE = "2026-10-01T06:24:48.090Z"  # end of OP70 in the blueprint = release from the cell
CELL_OPS = ["OP10", "OP20", "OP30", "OP40", "OP50", "OP60", "OP70"]
STAGES = ("released", "inspected", "packed", "lost")
RELEASED = {"Nameplate", "DppMetadata", "ExecutedProcesses", "ContactInformations", "HierarchicalStructures",
            "ProductMaterialComposition", "ProductCircularity"}
INSPECTED = {"QualityInspection", "MeasurementValue_LeakRate", "MeasurementValue_CapColour", "TechnicalData"}
# passport content provided by another service: listed in the DPP content of the stage, not written by the MES
PROVIDED = {"packed": {"CarbonFootprint"}}  # sustainability service, task pcf-calculate


def load_blueprint() -> dict:
    return load_yaml(REPO / "aas" / "data" / "blueprints" / "workpiece_instance.yaml")


def tag_of(serial: str) -> str:
    return "WP_" + serial.replace("-", "_")


class WorkpieceSpec:
    """Builds the asset spec of one workpiece at a stage from the process variables of its BPMN instance."""

    def __init__(self, blueprint: dict, positions: dict[str, list[float]], thumbnail: dict | str):
        self.blueprint, self.positions, self.thumbnail = blueprint, positions, thumbnail
        self.base_lots = passport.lots_of(blueprint)  # fallback lots for cells that report none

    def build(self, v: dict, stage: str, verdict: Verdict | None = None) -> dict:
        serial = v["serial"]
        spec = _replace_serial(copy.deepcopy(self.blueprint), serial)
        spec["thumbnail"] = self.thumbnail
        released = _parse(v["releasedAt"])
        spec["specificAssetIds"]["serialNumber"] = serial
        lots = lots_for(v, self.base_lots)
        self._nameplate(spec, serial, released)
        self._processes(spec, v, stage, verdict, lots)
        self._location(spec, v, stage)
        passport.apply_lots(spec, lots)
        keep = set(RELEASED)
        if stage in ("inspected", "packed") or (stage == "lost" and v.get("inspectedAt")):
            keep |= INSPECTED
            self._quality(spec, v, verdict)
            passport.apply_as_built(spec, v, verdict)
        if stage == "packed":
            keep.add("HandoverDocumentation")
            passport.apply_handover(spec, v, bool(verdict and verdict.passed))
        spec["submodels"] = [s for s in spec["submodels"]
                             if s.get("idShort", s["template"].split("-")[0]) in keep]
        self._dpp(spec, v, stage, verdict, keep | PROVIDED.get(stage, set()))
        spec["description"] = _description(serial, released, stage, verdict, v)
        return spec

    @staticmethod
    def certificate(spec: dict, v: dict, verdict: Verdict) -> dict[str, bytes]:
        """Generated files of a packed part: {file path: PDF} of the inspection certificate (good parts)."""
        return passport.certificate(spec, v, verdict)

    def _nameplate(self, spec: dict, serial: str, released: datetime) -> None:
        values = _submodel(spec, "Nameplate")
        values["SerialNumber"] = serial
        values["DateOfManufacture"] = released.date().isoformat()
        values["YearOfConstruction"] = str(released.year)

    @staticmethod
    def _dpp(spec: dict, v: dict, stage: str, verdict: Verdict | None, keep: set[str]) -> None:
        """Content list of the stage; Active only for a packed good unit (placed on the market)."""
        shipped = stage == "packed" and bool(verdict and verdict.passed)
        last = _iso(_parse(v.get("sortedAt") or v.get("inspectedAt") or v["releasedAt"]))
        passport.apply_metadata(spec, keep, "Active" if shipped else "Inactive", last)

    def _processes(self, spec: dict, v: dict, stage: str, verdict: Verdict | None,
                   lots: dict[str, str]) -> None:
        run = _submodel(spec, "ExecutedProcesses")["Run"][0]
        processes = {p["_idShort"]: p for p in run["Process"]}
        shift = _parse(v["releasedAt"]) - _parse(BLUEPRINT_RELEASE)
        rng = cell_data.rng(v["serial"])
        for op in CELL_OPS:
            _shift_times(processes[op], shift)
            cell_data.apply(processes[op], op, v, rng, lots)
        order = list(CELL_OPS)
        if v.get("inspectedAt"):
            inspected = _parse(v["inspectedAt"])
            _retime(processes["OP75"], _parse(v["releasedAt"]), inspected - timedelta(seconds=0.49))
            _retime(processes["OP80"], inspected - timedelta(seconds=0.49), inspected)
            cell_data.apply_inspection(processes["OP80"], v, verdict)
            order += ["OP75", "OP80"]
        if v.get("sortedAt") and stage == "packed":
            cell_data.apply_packing(processes["OP90"], v)
            _retime(processes["OP90"], _parse(v["inspectedAt"]), _parse(v["sortedAt"]))
            order.append("OP90")
        run["Process"] = [processes[op] for op in order]
        run["RunResult"] = {"packed": "Completed", "lost": "Aborted"}.get(stage, "InProgress")

    def _location(self, spec: dict, v: dict, stage: str) -> None:
        if stage == "packed":
            klt = "KLTA01" if int(v["container"]) == 1 else "KLTB01"
            spec["location"] = self.positions.get(klt)
            spec["locationDescription"] = {"en": f"{klt}, slot {int(v['slot']) + 1}",
                                           "de": f"{klt}, Fach {int(v['slot']) + 1}"}
            spec["locationTime"] = _iso(_parse(v["sortedAt"]))
        else:
            station = "QS01" if v.get("inspectedAt") else "CV01"
            spec["location"] = self.positions.get(station)
            spec["locationDescription"] = {"en": f"LINE01, at {station} (in process)",
                                           "de": f"LINE01, an {station} (in Bearbeitung)"}
            spec["locationTime"] = _iso(_parse(v.get("inspectedAt") or v["releasedAt"]))

    def _quality(self, spec: dict, v: dict, verdict: Verdict) -> None:
        values = _submodel(spec, "QualityInspection")
        verdict.apply(values, spec, v)


def _replace_serial(node, serial: str):
    """Replaces the blueprint serial in every string (also the tag and idShort forms with underscores)."""
    if isinstance(node, dict):
        return {k: _replace_serial(val, serial) for k, val in node.items()}
    if isinstance(node, list):
        return [_replace_serial(val, serial) for val in node]
    if isinstance(node, str):
        return node.replace(BLUEPRINT_SERIAL, serial).replace(
            BLUEPRINT_SERIAL.replace("-", "_"), serial.replace("-", "_"))
    return node


def _shift_times(process: dict, shift: timedelta) -> None:
    for key in ("ProcessStartTime", "ProcessEndTime"):
        process[key] = _iso(_parse(process[key]) + shift)
    for stage in (process.get("ProcessStages") or {}).get("ProcessStage", []):
        stage["StartTime"] = _iso(_parse(stage["StartTime"]) + shift)
        stage["EndTime"] = _iso(_parse(stage["EndTime"]) + shift)


def _retime(process: dict, start: datetime, end: datetime) -> None:
    """Maps the blueprint process interval (and its stages, linearly) onto [start, end]."""
    old_start, old_end = _parse(process["ProcessStartTime"]), _parse(process["ProcessEndTime"])
    scale = (end - start) / (old_end - old_start) if old_end > old_start else 1.0
    for stage in (process.get("ProcessStages") or {}).get("ProcessStage", []):
        stage["StartTime"] = _iso(start + (_parse(stage["StartTime"]) - old_start) * scale)
        stage["EndTime"] = _iso(start + (_parse(stage["EndTime"]) - old_start) * scale)
    process["ProcessStartTime"], process["ProcessEndTime"] = _iso(start), _iso(end)


def _description(serial: str, released: datetime, stage: str, verdict: Verdict | None, v: dict) -> dict:
    day = released.date().isoformat()
    if stage == "packed":
        klt = "KLT A01" if int(v["container"]) == 1 else "KLT B01"
        result = ("good part" if verdict and verdict.passed else "rejected part", "Gutteil" if verdict and
                  verdict.passed else "Ausschussteil")
        return {"en": f"Product instance {serial} produced on LINE01 on {day}; "
                      f"result: {result[0]}, packed in {klt}.",
                "de": f"Produktinstanz {serial}, am {day} auf LINE01 gefertigt; "
                      f"Ergebnis: {result[1]}, in {klt}."}
    if stage == "lost":
        return {"en": f"Product instance {serial} ({day}): tracking lost on LINE01, run aborted.",
                "de": f"Produktinstanz {serial} ({day}): Verfolgung auf LINE01 verloren, "
                      "Durchlauf abgebrochen."}
    return {"en": f"Product instance {serial} in production on LINE01 since {day}.",
            "de": f"Produktinstanz {serial}, seit {day} in Fertigung auf LINE01."}


def _parse(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
