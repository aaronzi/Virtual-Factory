"""Publishes workpiece instance AAS on the AAS server: builds the stage spec together with the product type
(for references into its recipe), uploads concept descriptions once, replaces changed submodels, uploads the
files of File elements as attachments (embedded repository files such as the type documents, and generated
files such as the inspection certificate; BaSyx deduplicates identical content).

Retention (DataRetentionPolicies of LINE01, aas-model.md §6b): passports of shipped units (packed good parts,
dppStatus Active) are kept across sessions, up to `passport_limit` (0 = unlimited; the oldest are removed
first). Everything else - units in production, rejects, lost units - is session data: a rolling window of
`retention` instances, and removed when a new session starts. Submodels written by other services
(CarbonFootprint: sustainability) stay referenced when the MES replaces the shell and are deleted with it."""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import PurePosixPath

from provisioner.build import BuildContext, load_assets
from vf_common import ids
from vf_common.aas.files import file_elements
from vf_common.basyx import BasyxClient

log = logging.getLogger("mes.store")
WORKPIECE_PREFIX = ids.aas_id("WP_")
DPP_METADATA = "https://admin-shell.io/idta/cds/dppMetadata/1"  # ModelReference, key type Submodel
FOREIGN = ("/CarbonFootprint/",)  # submodel ids owned by other services (sustainability)


class WorkpieceStore:
    def __init__(self, ctx: BuildContext, aas: BasyxClient, retention: int = 500, passport_limit: int = 0):
        self.ctx, self.aas, self.retention, self.passport_limit = ctx, aas, retention, passport_limit
        self.type_spec = load_assets(ctx.repo / "aas" / "data", {"PC3280_TYPE"})[0]
        self._published_cds: set[str] = set()
        self._file_cache: dict[str, bytes] = {}
        self._instances: OrderedDict[str, list[str]] = OrderedDict()  # session data: aas id -> submodel ids
        self._shipped: OrderedDict[str, list[str]] = OrderedDict()    # passports of shipped units
        self._lock = threading.Lock()

    def publish(self, spec: dict, generated: dict[str, bytes] | None = None) -> dict:
        """Builds and uploads one workpiece stage; returns its shell. generated: content of File values by
        repository path (instead of the file in the repository, e.g. the certificate of this part)."""
        result = self.ctx.build([self.type_spec, spec], validate=True)
        env = result.environment
        shell = next(s for s in env["assetAdministrationShells"] if s["id"] == ids.aas_id(spec["tag"]))
        if shell["id"] in self._shipped and not is_shipped(env, shell):
            # a serial must never be reused: the passport of a shipped unit is not overwritten
            raise RuntimeError(f"{shell['id']} is the passport of a shipped unit of an earlier session "
                               "(serial number reused) - not overwritten")
        sm_ids = [r["keys"][0]["value"] for r in shell.get("submodels", [])]
        for cd in env.get("conceptDescriptions", []):
            if cd["id"] not in self._published_cds:
                self.aas.put_concept_description(cd)
                self._published_cds.add(cd["id"])
        for sm in env["submodels"]:
            if sm["id"] in sm_ids:
                self.aas.put_submodel(sm)
                self._upload_files(sm, result.builder.files, generated or {})
        shell["submodels"] = shell.get("submodels", []) + self._foreign_refs(shell["id"], sm_ids)
        self.aas.put_shell(shell)
        for aas_id in self._track(shell["id"], sm_ids, is_shipped(env, shell)):
            self._delete(aas_id)
        return shell

    def _foreign_refs(self, aas_id: str, own: list[str]) -> list[dict]:
        """References of the existing shell to submodels of other services (kept on replace)."""
        known = aas_id in self._instances or aas_id in self._shipped
        existing = self.aas.get_shell(aas_id) if known else None
        return [r for r in (existing or {}).get("submodels", [])
                if r["keys"][0]["value"] not in own and any(f in r["keys"][0]["value"] for f in FOREIGN)]

    def _track(self, aas_id: str, sm_ids: list[str], shipped: bool) -> list[str]:
        """Records the instance; returns the expired ones (rolling window / passport limit)."""
        with self._lock:
            self._instances.pop(aas_id, None)
            self._shipped.pop(aas_id, None)
            target = self._shipped if shipped else self._instances
            target[aas_id] = sm_ids
            expired = list(self._instances)[:-self.retention] if self.retention else []
            if self.passport_limit:
                expired += list(self._shipped)[:-self.passport_limit]
        return expired

    def _upload_files(self, sm: dict, files: dict[str, str], generated: dict[str, bytes]) -> None:
        for path, element in file_elements(sm.get("submodelElements", [])):
            rel = files.get(element.get("value", ""))
            if rel is None:
                continue
            data = generated.get(rel)
            if data is None:
                data = self._repo_file(rel)
            self.aas.put_attachment(sm["id"], path, data, PurePosixPath(rel).name,
                                    element.get("contentType", "application/octet-stream"))

    def _repo_file(self, rel: str) -> bytes:
        if rel not in self._file_cache:
            self._file_cache[rel] = (self.ctx.repo / rel).read_bytes()
        return self._file_cache[rel]

    def count(self) -> int:
        return len(self._instances) + len(self._shipped)

    def clear_session(self) -> tuple[int, int]:
        """New session: deletes the workpiece AAS that are session data (also ones from before an MES restart)
        and keeps the passports of shipped units. Returns (removed, kept)."""
        shipped = self.shipped_ids()
        removed = kept = 0
        with self._lock:
            self._instances.clear()
        for shell in self.aas.list_shells():
            if not shell["id"].startswith(WORKPIECE_PREFIX):
                continue
            refs = [r["keys"][0]["value"] for r in shell.get("submodels", [])]
            if shell["id"] in shipped:
                with self._lock:
                    self._shipped.setdefault(shell["id"], refs)
                kept += 1
                continue
            self._delete(shell["id"], refs)
            removed += 1
        return removed, kept

    def shipped_ids(self) -> set[str]:
        """AAS ids of the workpieces whose passport is Active (one query over all DppMetadata submodels)."""
        active = set()
        for sm in self.aas.list_submodels(semantic_id=DPP_METADATA, semantic_key_type="Submodel"):
            if "/sm/WP_" not in sm["id"]:
                continue
            status = next((e.get("value") for e in sm.get("submodelElements", [])
                           if e.get("idShort") == "dppStatus"), None)
            if status == "Active":
                active.add(ids.aas_id(sm["id"].split("/")[5]))
        return active

    def _delete(self, aas_id: str, sm_ids: list[str] | None = None) -> None:
        with self._lock:
            known = self._instances.pop(aas_id, None) or self._shipped.pop(aas_id, None) or []
        if sm_ids is None:
            shell = self.aas.get_shell(aas_id)
            sm_ids = [r["keys"][0]["value"] for r in (shell or {}).get("submodels", [])]
        for sm_id in dict.fromkeys([*sm_ids, *known]):
            self.aas.delete_submodel(sm_id)
        self.aas.delete_shell(aas_id)
        log.debug("deleted %s", aas_id)


def is_shipped(env: dict, shell: dict) -> bool:
    """True if the built stage is a shipped unit (DppMetadata.dppStatus Active)."""
    own = {r["keys"][0]["value"] for r in shell.get("submodels", [])}
    for sm in env["submodels"]:
        if sm["id"] in own and sm.get("idShort") == "DppMetadata":
            return any(e.get("idShort") == "dppStatus" and e.get("value") == "Active"
                       for e in sm.get("submodelElements", []))
    return False
