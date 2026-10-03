"""The workpiece's CarbonFootprint submodel (IDTA 02023, owned by the sustainability service): built from the
CarbonFootprint section of the workpiece blueprint (aas/data/blueprints/workpiece_instance.yaml) with the
part's values, strictly validated together with the product type, uploaded with its concept descriptions and
referenced from the workpiece AAS (which the MES creates and owns). Entries: total A1-A3, A1 purchased
components, A3 manufacturing with the energy details; data quality (PACT primary data share, share of
supplier-specific batch data in A1) as extra properties of entries 1 and 2 (ADR-0028)."""

from __future__ import annotations

import copy
import logging
from datetime import datetime

from provisioner.build import REPO, BuildContext, load_assets, load_yaml
from vf_common import ids
from vf_common.basyx import BasyxClient

from .carbon import PartFootprint

log = logging.getLogger("sustainability.aas")
BLUEPRINT_SERIAL = "PC3280-2026-000123"
REJECT_NOTE = {"en": "Footprint of this rejected unit (production loss, A1-A3): components and energy. It "
                     "is allocated to the good units of the session (their ProductionLossCO2eq) - do not "
                     "count it again.",
               "de": "Fußabdruck dieser Ausschuss-Einheit (Produktionsverlust, A1-A3): Bauteile und Energie. "
                     "Er wird den Gut-Einheiten der Sitzung zugeordnet (deren ProductionLossCO2eq) - nicht "
                     "nochmals zählen."}


def tag_of(serial: str) -> str:
    return "WP_" + serial.replace("-", "_")


def footprint_spec(blueprint: dict, serial: str, fp: PartFootprint, published: str) -> dict:
    """Asset spec of the workpiece holding only its CarbonFootprint submodel with the part's values."""
    spec = _replace_serial(copy.deepcopy(blueprint), serial)
    spec["submodels"] = [s for s in spec["submodels"] if s["template"].startswith("CarbonFootprint")]
    values = spec["submodels"][0]["values"]
    total, material, manufacturing = values["ProductCarbonFootprints"]
    for entry, value in ((total, fp.total), (material, fp.material), (manufacturing, fp.manufacturing)):
        entry["PcfCO2eq"] = round(value, 4)
        entry["PublicationDate"] = published
    for key, value in (("ElectricalEnergy", fp.electricity_kwh), ("CompressedAirEnergy", fp.air_kwh),
                       ("ProductionLossCO2eq", fp.loss_share), ("LineResidenceTime", fp.residence_s)):
        manufacturing["+" + key]["value"] = round(value, 6)
    total["+PrimaryDataShare"]["value"] = round(fp.primary_share, 1)
    material["+PrimaryDataShare"]["value"] = round(fp.material_primary_share, 1)
    material["+SupplierSpecificDataShare"]["value"] = round(fp.supplier_specific_share, 1)
    if fp.rejected:
        total["_description"] = REJECT_NOTE
    return spec


class FootprintWriter:
    """Writes the CarbonFootprint submodel of a workpiece AAS (PUT submodel, reference from the shell)."""

    def __init__(self, aas: BasyxClient, ctx: BuildContext | None = None):
        self.aas, self.ctx = aas, ctx or BuildContext()
        self.blueprint = load_yaml(REPO / "aas" / "data" / "blueprints" / "workpiece_instance.yaml")
        self.type_spec = load_assets(self.ctx.repo / "aas" / "data", {"PC3280_TYPE"})[0]
        self._published_cds: set[str] = set()

    def build(self, serial: str, fp: PartFootprint, sorted_at: str) -> tuple[dict, list[dict]]:
        """(CarbonFootprint submodel, concept descriptions) of the part."""
        published = _parse(sorted_at).isoformat(timespec="seconds")
        spec = footprint_spec(self.blueprint, serial, fp, published)
        env = self.ctx.build([self.type_spec, spec], validate=True).environment
        sm_id = ids.submodel_id(tag_of(serial), "CarbonFootprint", "1")
        submodel = next(s for s in env["submodels"] if s["id"] == sm_id)
        return submodel, env.get("conceptDescriptions", [])

    def write(self, serial: str, fp: PartFootprint, sorted_at: str) -> str:
        """Uploads the submodel; returns its id. The workpiece AAS must exist (created by the MES)."""
        aas_id = ids.aas_id(tag_of(serial))
        shell = self.aas.get_shell(aas_id)
        if shell is None:
            raise LookupError(f"workpiece AAS {aas_id} not found (MES has not written it yet)")
        submodel, cds = self.build(serial, fp, sorted_at)
        for cd in cds:
            if cd["id"] not in self._published_cds:
                self.aas.put_concept_description(cd)
                self._published_cds.add(cd["id"])
        self.aas.put_submodel(submodel)
        if submodel["id"] not in {r["keys"][0]["value"] for r in shell.get("submodels") or []}:
            self.aas.add_submodel_ref(aas_id, submodel["id"])
        log.debug("CarbonFootprint of %s: %.4f kg CO2e", serial, fp.total)
        return submodel["id"]


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


def _parse(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
