"""The batch AAS of a delivered lot in the supplier environment (ADR-0028): asset spec from the blueprint
aas/data/supplier/blueprints/batch_instance.yaml filled with the batch record, built together with the product
type (derivedFrom, ProductType reference), strictly validated and uploaded with its material certificate (PDF
attachment). Publishing is idempotent: an existing batch AAS is left unchanged (the supplier published it at
despatch; its data do not change afterwards)."""

from __future__ import annotations

import copy
import logging
import threading
from pathlib import PurePosixPath

from provisioner.build import BuildContext, load_yaml
from vf_common.aas.files import file_elements
from vf_common.basyx import BasyxClient

from .articles import SUPPLIER_DATA
from .batches import BatchRecord
from .certificate import generate

log = logging.getLogger("supplier.aas")
CUSTOMER = "VF Pneumatics GmbH"
BLUEPRINT = SUPPLIER_DATA / "blueprints" / "batch_instance.yaml"


def batch_spec(blueprint: dict, record: BatchRecord) -> dict:
    """Asset spec of the batch AAS (blueprint structure, values of this batch)."""
    article, lot = record.article, record.lot
    spec = copy.deepcopy(blueprint)
    name = article.name
    spec.update(tag=record.tag, idShort="Batch_" + lot.replace("-", "_"), idBase=article.id_base,
                derivedFrom=article.tag, globalAssetId=record.asset_id,
                specificAssetIds={"manufacturerPartId": article.part_id, "batchId": lot,
                                  "customerPartId": article.customer_part_id})
    spec["displayName"] = {"en": f"Batch {lot} of {name['en']}", "de": f"Charge {lot} von {name['de']}"}
    spec["description"] = {
        "en": f"Production batch {lot} ({record.quantity} pieces, produced {record.produced}) delivered to "
              f"{CUSTOMER} with despatch advice {record.despatch_advice}; batch-specific carbon footprint, "
              "recycled content and material certificate EN 10204 3.1.",
        "de": f"Fertigungscharge {lot} ({record.quantity} Stück, gefertigt am {record.produced}), an die "
              f"{CUSTOMER} geliefert mit Lieferavis {record.despatch_advice}; chargenspezifischer "
              "CO2-Fußabdruck, Rezyklatanteil und Werkstoffzeugnis EN 10204 3.1."}
    _batch_information(_values(spec, "BatchInformation"), record)
    _footprint(_values(spec, "CarbonFootprint"), record)
    _composition(spec, record)
    _certificate(_values(spec, "HandoverDocumentation"), record)
    return spec


def certificate_path(record: BatchRecord) -> str:
    return f"aas/files/supplier/{record.certificate}.pdf"


def _values(spec: dict, template: str) -> dict:
    return next(s for s in spec["submodels"] if s["template"].startswith(template))["values"]


def _batch_information(values: dict, record: BatchRecord) -> None:
    article = record.article
    values.update(BatchId=record.lot, ManufacturerPartId=article.part_id,
                  CustomerPartId=article.customer_part_id, ProductType={"ref": f"aas:{article.tag}"},
                  Quantity=record.quantity, DateOfManufacture=record.produced.isoformat(),
                  ProductionSite=article.profile["site"], Customer=CUSTOMER,
                  DespatchAdviceNumber=record.despatch_advice, DespatchDate=record.despatched.isoformat(),
                  MaterialCertificate=record.certificate, MeanMassPerPiece=record.mean_mass)
    if record.recycled:
        values["RecycledContent"] = {"RecycledMaterial": article.profile["recycled"]["material"],
                                     "PreConsumerShare": record.recycled[0],
                                     "PostConsumerShare": record.recycled[1]}
    else:
        values.pop("RecycledContent", None)


def _footprint(values: dict, record: BatchRecord) -> None:
    entry = values["ProductCarbonFootprints"][0]
    entry["PcfCO2eq"] = round(record.pcf, 4)
    entry["PublicationDate"] = f"{record.despatched.isoformat()}T00:00:00+00:00"
    entry["+PrimaryDataShare"]["value"] = record.primary_share
    entry["+BatchId"]["value"] = record.lot


def _composition(spec: dict, record: BatchRecord) -> None:
    """Material composition of the type, scaled to the measured mass, with the batch id per material."""
    type_values = _values(record.article.spec, "ProductMaterialComposition")
    values = copy.deepcopy(type_values)
    scale = record.mean_mass / float(type_values["TotalMass"])
    values["TotalMass"] = record.mean_mass
    for material in values["Materials"]:
        material["MaterialLocation"] = {**material["MaterialLocation"], "BatchId": record.lot}
        material["MaterialMass"] = round(float(material["MaterialMass"]) * scale, 5)
    values["DeclarationDate"] = record.despatched.isoformat()
    next(s for s in spec["submodels"] if s["template"].startswith("ProductMaterialComposition"))["values"] = \
        values


def _certificate(values: dict, record: BatchRecord) -> None:
    company = record.article.company
    document = values["Documents"][0]
    document["DocumentIds"][0].update(DocumentDomainId=company.domain_id,
                                      DocumentIdentifier=record.certificate)
    version = document["DocumentVersions"][0]
    version["Title"] = {"en": f"Inspection certificate 3.1 (EN 10204) batch {record.lot}",
                        "de": f"Abnahmeprüfzeugnis 3.1 (EN 10204) Charge {record.lot}"}
    version.update(StatusSetDate=record.despatched.isoformat(), OrganizationShortName=company.short_name,
                   OrganizationOfficialName=company.name)
    version["DigitalFiles"] = [{"value": "repo:" + certificate_path(record)}]


class BatchPublisher:
    """Creates batch AAS in the supplier's own repository (registered by its registry integration)."""

    def __init__(self, aas: BasyxClient, ctx: BuildContext | None = None):
        self.aas = aas
        self.ctx = ctx or BuildContext(data_dir=SUPPLIER_DATA)
        self.blueprint = load_yaml(BLUEPRINT)
        self._published_cds: set[str] = set()
        self._lock = threading.Lock()

    def publish(self, record: BatchRecord) -> bool:
        """Uploads the batch AAS unless it exists; True if it was created now."""
        with self._lock:
            if self.aas.get_shell(record.aas_id) is not None:
                return False
            spec = batch_spec(self.blueprint, record)
            result = self.ctx.build([record.article.spec, spec], validate=True)
            env = result.environment
            shell = next(s for s in env["assetAdministrationShells"] if s["id"] == record.aas_id)
            own = {r["keys"][0]["value"] for r in shell["submodels"]}
            for cd in env.get("conceptDescriptions", []):
                if cd["id"] not in self._published_cds:
                    self.aas.put_concept_description(cd)
                    self._published_cds.add(cd["id"])
            pdf = generate(record)
            for submodel in (s for s in env["submodels"] if s["id"] in own):
                self.aas.put_submodel(submodel)
                self._upload_files(submodel, result.builder.files, pdf)
            self.aas.put_shell(shell)
            log.info("published batch AAS %s (%s, PCF %.4f kg)", record.lot, record.article.part_id,
                     record.pcf)
            return True

    def _upload_files(self, submodel: dict, files: dict[str, str], pdf: bytes) -> None:
        for path, element in file_elements(submodel.get("submodelElements", [])):
            rel = files.get(element.get("value", ""))
            if rel is not None:
                self.aas.put_attachment(submodel["id"], path, pdf, PurePosixPath(rel).name, "application/pdf")
