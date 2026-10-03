"""Publishes workpiece instance AAS on the AAS server: builds the stage spec together with the product type
(for references into its recipe), uploads concept descriptions once, replaces changed submodels, keeps a
rolling window of instances (retention) and removes everything of a previous session."""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict

from provisioner.build import BuildContext, load_assets
from vf_common import ids
from vf_common.basyx import BasyxClient

log = logging.getLogger("mes.store")
WORKPIECE_PREFIX = ids.aas_id("WP_")


class WorkpieceStore:
    def __init__(self, ctx: BuildContext, aas: BasyxClient, retention: int = 500):
        self.ctx, self.aas, self.retention = ctx, aas, retention
        self.type_spec = load_assets(ctx.repo / "aas" / "data", {"PC3280_TYPE"})[0]
        self._published_cds: set[str] = set()
        self._instances: OrderedDict[str, list[str]] = OrderedDict()  # aas id -> submodel ids
        self._lock = threading.Lock()

    def publish(self, spec: dict) -> dict:
        """Builds and uploads one workpiece stage; returns its shell."""
        env = self.ctx.build([self.type_spec, spec], validate=True).environment
        shell = next(s for s in env["assetAdministrationShells"] if s["id"] == ids.aas_id(spec["tag"]))
        sm_ids = [r["keys"][0]["value"] for r in shell.get("submodels", [])]
        for cd in env.get("conceptDescriptions", []):
            if cd["id"] not in self._published_cds:
                self.aas.put_concept_description(cd)
                self._published_cds.add(cd["id"])
        for sm in env["submodels"]:
            if sm["id"] in sm_ids:
                self.aas.put_submodel(sm)
        self.aas.put_shell(shell)
        with self._lock:
            self._instances[shell["id"]] = sm_ids
            self._instances.move_to_end(shell["id"])
            expired = [k for k in list(self._instances)[:-self.retention]] if self.retention else []
        for aas_id in expired:
            self._delete(aas_id)
        return shell

    def count(self) -> int:
        return len(self._instances)

    def clear_session(self) -> int:
        """Deletes every workpiece AAS (also ones from before an MES restart); returns the number removed."""
        removed = 0
        for shell in self.aas.list_shells():
            if shell["id"].startswith(WORKPIECE_PREFIX):
                self._delete(shell["id"], [r["keys"][0]["value"] for r in shell.get("submodels", [])])
                removed += 1
        with self._lock:
            self._instances.clear()
        return removed

    def _delete(self, aas_id: str, sm_ids: list[str] | None = None) -> None:
        with self._lock:
            known = self._instances.pop(aas_id, None)
        for sm_id in sm_ids or known or []:
            self.aas.delete_submodel(sm_id)
        self.aas.delete_shell(aas_id)
        log.debug("deleted %s", aas_id)
